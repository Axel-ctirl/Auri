"""Chat endpoints: buffered, streaming and stop.

Streaming uses Server-Sent Events. Each event carries a JSON payload:

``meta``   one event up front with the conversation id, stream id and citations
``token``  many events, each a text delta
``done``   one event with timing and the persisted message id
``error``  one event when generation failed; the stream then closes
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..config import Settings, get_settings
from ..db import get_session, new_session
from ..errors import BreadError
from ..models import Conversation
from ..schemas import (
    ChatRequest,
    ChatResponse,
    ChatStopRequest,
    ChatStopResponse,
    Citation,
)
from ..services import chat_service
from ..services.inference import registry

router = APIRouter(tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Stops nginx and friends from buffering the stream into one big chunk.
    "X-Accel-Buffering": "no",
}


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/chat", response_model=ChatResponse, summary="Send a message, wait for the reply")
def chat(
    request: ChatRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    backend = registry.get_or_autoload(settings)
    conversation = chat_service.resolve_conversation(session, request)
    citations = chat_service.retrieve_context(session, settings, conversation, request)
    params = chat_service.resolve_generation_params(settings, conversation, request)
    turns = chat_service.build_turns(session, settings, conversation, request, citations, backend)

    if request.persist:
        chat_service.persist_user_message(session, conversation, request.message)

    stream_id, stop_signal = registry.register_stream(conversation.id)
    started = time.perf_counter()
    try:
        content = backend.generate(turns, params, stop_signal)
    finally:
        registry.release_stream(stream_id)

    latency_ms = int((time.perf_counter() - started) * 1000)
    status = backend.status()
    model_id = status.model_id or settings.model_id

    message_id = ""
    if request.persist:
        message = chat_service.persist_assistant_message(
            session,
            conversation,
            content=content,
            model_id=model_id,
            citations=citations,
            latency_ms=latency_ms,
            token_count=backend.count_tokens(content),
            stopped_early=stop_signal.stopped,
        )
        message_id = message.id

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=message_id,
        content=content,
        model_id=model_id,
        backend=status.backend,
        sources=[Citation(**citation) for citation in citations],
        prompt_tokens=sum(backend.count_tokens(turn.content) for turn in turns),
        completion_tokens=backend.count_tokens(content),
        latency_ms=latency_ms,
        stopped_early=stop_signal.stopped,
    )


@router.post("/chat/stream", summary="Send a message and stream the reply as SSE")
def chat_stream(
    request: ChatRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    backend = registry.get_or_autoload(settings)
    conversation = chat_service.resolve_conversation(session, request)
    citations = chat_service.retrieve_context(session, settings, conversation, request)
    params = chat_service.resolve_generation_params(settings, conversation, request)
    turns = chat_service.build_turns(session, settings, conversation, request, citations, backend)

    if request.persist:
        chat_service.persist_user_message(session, conversation, request.message)

    conversation_id = conversation.id
    stream_id, stop_signal = registry.register_stream(conversation_id)
    status = backend.status()
    model_id = status.model_id or settings.model_id
    persist = request.persist

    def event_source() -> Iterator[str]:
        yield _sse(
            "meta",
            {
                "conversation_id": conversation_id,
                "stream_id": stream_id,
                "model_id": model_id,
                "backend": status.backend,
                "sources": citations,
            },
        )

        collected: list[str] = []
        started = time.perf_counter()
        failure: str | None = None

        try:
            for delta in backend.stream(turns, params, stop_signal):
                collected.append(delta)
                yield _sse("token", {"delta": delta})
        except BreadError as exc:
            failure = exc.message
            yield _sse("error", {"code": exc.code, "message": exc.message, "hint": exc.hint})
        except Exception as exc:  # noqa: BLE001 - the client deserves the reason
            failure = str(exc)
            yield _sse(
                "error",
                {"code": "generation_failed", "message": f"{type(exc).__name__}: {exc}"},
            )
        finally:
            registry.release_stream(stream_id)

        latency_ms = int((time.perf_counter() - started) * 1000)
        content = "".join(collected)
        message_id = ""

        if persist and (content or failure):
            # A fresh session: the request-scoped one may have been closed by the
            # time the generator finishes streaming.
            with new_session() as writer:
                stored_conversation = writer.get(Conversation, conversation_id)
                if stored_conversation is not None:
                    message = chat_service.persist_assistant_message(
                        writer,
                        stored_conversation,
                        content=content,
                        model_id=model_id,
                        citations=citations,
                        latency_ms=latency_ms,
                        token_count=len(content) // 4,
                        stopped_early=stop_signal.stopped,
                        error=failure,
                    )
                    message_id = message.id

        yield _sse(
            "done",
            {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "latency_ms": latency_ms,
                "stopped_early": stop_signal.stopped,
                "characters": len(content),
                "error": failure,
            },
        )

    return StreamingResponse(
        event_source(), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/chat/stop", response_model=ChatStopResponse, summary="Cancel generation")
def chat_stop(payload: ChatStopRequest) -> ChatStopResponse:
    if payload.stream_id:
        stopped = registry.stop_stream(payload.stream_id)
        return ChatStopResponse(stopped=stopped, stream_ids=[payload.stream_id] if stopped else [])
    if payload.conversation_id:
        ids = registry.stop_conversation(payload.conversation_id)
        return ChatStopResponse(stopped=bool(ids), stream_ids=ids)
    ids = registry.stop_all()
    return ChatStopResponse(stopped=bool(ids), stream_ids=ids)
