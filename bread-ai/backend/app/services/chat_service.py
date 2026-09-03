"""Assembling a chat turn: history, RAG context, prompt presets, persistence."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from ..config import Settings
from ..errors import NotFoundError
from ..models import Conversation, KnowledgeSpace, Message, utcnow
from ..schemas import ChatRequest
from .inference.base import ChatTurn, GenerationParams, InferenceBackend
from .prompts import compose_system_prompt
from .rag import ingest

TITLE_MAX_CHARS = 60


def resolve_conversation(session: Session, request: ChatRequest) -> Conversation:
    """Fetch the conversation named by the request, creating one when absent."""

    if request.conversation_id:
        conversation = session.get(Conversation, request.conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversation {request.conversation_id} does not exist.")
        return conversation

    conversation = Conversation(
        title=_derive_title(request.message),
        model_id=request.model_id,
        system_prompt=request.system_prompt,
        rag_enabled=bool(request.rag_enabled),
        knowledge_space_id=request.knowledge_space_id,
        temperature=request.temperature,
        top_p=request.top_p,
        max_new_tokens=request.max_new_tokens,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def _derive_title(message: str) -> str:
    cleaned = " ".join(message.split())
    if not cleaned:
        return "New chat"
    if len(cleaned) <= TITLE_MAX_CHARS:
        return cleaned
    return cleaned[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def stored_history(session: Session, conversation_id: str) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(session.exec(statement).all())


def resolve_generation_params(
    settings: Settings, conversation: Conversation, request: ChatRequest
) -> GenerationParams:
    """Request values win, then per-conversation values, then global settings."""

    def pick(request_value: Any, conversation_value: Any, default: Any) -> Any:
        for candidate in (request_value, conversation_value):
            if candidate is not None:
                return candidate
        return default

    return GenerationParams(
        temperature=float(pick(request.temperature, conversation.temperature, settings.temperature)),
        top_p=float(pick(request.top_p, conversation.top_p, settings.top_p)),
        max_new_tokens=int(
            pick(request.max_new_tokens, conversation.max_new_tokens, settings.max_new_tokens)
        ),
        repetition_penalty=float(request.repetition_penalty or settings.repetition_penalty),
    )


def retrieve_context(
    session: Session, settings: Settings, conversation: Conversation, request: ChatRequest
) -> list[dict[str, Any]]:
    """Run retrieval when RAG is on for this request or this conversation."""

    rag_on = request.rag_enabled if request.rag_enabled is not None else conversation.rag_enabled
    if not rag_on or not settings.rag_enabled:
        return []

    space_id = request.knowledge_space_id or conversation.knowledge_space_id
    if not space_id:
        first_space = session.exec(
            select(KnowledgeSpace).order_by(KnowledgeSpace.created_at)
        ).first()
        if first_space is None:
            return []
        space_id = first_space.id

    citations, _model_id, _reranked = ingest.search(
        session,
        settings,
        query=request.message,
        space_id=space_id,
        top_k=request.rag_top_k or settings.rag_top_k,
    )
    return citations


def build_turns(
    session: Session,
    settings: Settings,
    conversation: Conversation,
    request: ChatRequest,
    citations: list[dict[str, Any]],
    backend: InferenceBackend,
) -> list[ChatTurn]:
    """Build the full prompt: system message, history, retrieved context, question."""

    base_system = request.system_prompt or conversation.system_prompt or settings.system_prompt()
    system_prompt = compose_system_prompt(base_system, request.preset)

    turns: list[ChatTurn] = [ChatTurn(role="system", content=system_prompt)]

    if request.messages is not None:
        history = [ChatTurn(role=item.role, content=item.content) for item in request.messages]
        turns.extend(turn for turn in history if turn.role != "system")
    else:
        for message in stored_history(session, conversation.id):
            if message.role == "system" or message.error:
                continue
            turns.append(ChatTurn(role=message.role, content=message.content))

    user_content = request.message
    context_block = ingest.build_context_block(citations)
    if context_block:
        user_content = f"{context_block}\n\n---\n\nQuestion: {request.message}"

    turns.append(ChatTurn(role="user", content=user_content))
    return _trim_to_context(turns, backend, settings, request)


def _trim_to_context(
    turns: list[ChatTurn],
    backend: InferenceBackend,
    settings: Settings,
    request: ChatRequest,
) -> list[ChatTurn]:
    """Drop the oldest exchanges until the prompt fits the context window.

    The system message and the newest user message are always kept: without them
    the request stops meaning what the caller asked.
    """

    reserve = request.max_new_tokens or settings.max_new_tokens
    budget = max(settings.max_context_length - reserve, 512)

    def total(candidate: list[ChatTurn]) -> int:
        return sum(backend.count_tokens(turn.content) + 4 for turn in candidate)

    if total(turns) <= budget:
        return turns

    system_turn = turns[0]
    latest_turn = turns[-1]
    middle = turns[1:-1]

    while middle and total([system_turn, *middle, latest_turn]) > budget:
        middle.pop(0)

    return [system_turn, *middle, latest_turn]


def persist_user_message(session: Session, conversation: Conversation, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role="user", content=content)
    session.add(message)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()
    session.refresh(message)
    return message


def persist_assistant_message(
    session: Session,
    conversation: Conversation,
    *,
    content: str,
    model_id: str,
    citations: list[dict[str, Any]],
    latency_ms: int,
    token_count: int | None = None,
    stopped_early: bool = False,
    error: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        sources_json=json.dumps(citations) if citations else None,
        model_id=model_id,
        token_count=token_count,
        latency_ms=latency_ms,
        stopped_early=stopped_early,
        error=error,
    )
    session.add(message)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()
    session.refresh(message)
    return message


def message_sources(message: Message) -> list[dict[str, Any]]:
    if not message.sources_json:
        return []
    try:
        return json.loads(message.sources_json)
    except json.JSONDecodeError:
        return []
