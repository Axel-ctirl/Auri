"""Conversation CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, delete, func, select

from ..audit import record_action
from ..db import get_session
from ..errors import NotFoundError
from ..models import Conversation, Message, utcnow
from ..schemas import (
    Citation,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    DeleteResponse,
    MessageOut,
)
from ..services.chat_service import message_sources

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _summary(session: Session, conversation: Conversation) -> ConversationOut:
    count = session.exec(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation.id)
    ).one()
    last = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(col(Message.created_at).desc())
        .limit(1)
    ).first()
    preview = None
    if last is not None:
        preview = " ".join(last.content.split())[:140]
    return ConversationOut(
        **conversation.model_dump(),
        message_count=int(count),
        last_message_preview=preview,
    )


@router.get("", response_model=list[ConversationOut], summary="List conversations")
def list_conversations(
    session: Session = Depends(get_session),
    search: str | None = Query(default=None, description="Case-insensitive title search"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[ConversationOut]:
    statement = select(Conversation)
    if not include_archived:
        statement = statement.where(col(Conversation.archived).is_(False))
    if search:
        statement = statement.where(col(Conversation.title).ilike(f"%{search}%"))
    statement = statement.order_by(
        col(Conversation.pinned).desc(), col(Conversation.updated_at).desc()
    ).limit(limit)
    return [_summary(session, conversation) for conversation in session.exec(statement).all()]


@router.post("", response_model=ConversationOut, summary="Create a conversation")
def create_conversation(
    payload: ConversationCreate, session: Session = Depends(get_session)
) -> ConversationOut:
    conversation = Conversation(
        title=payload.title or "New chat",
        model_id=payload.model_id,
        system_prompt=payload.system_prompt,
        rag_enabled=payload.rag_enabled,
        knowledge_space_id=payload.knowledge_space_id,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return _summary(session, conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Fetch one conversation with its messages",
)
def get_conversation(
    conversation_id: str, session: Session = Depends(get_session)
) -> ConversationDetail:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} does not exist.")

    messages = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(col(Message.created_at), col(Message.id))
    ).all()

    summary = _summary(session, conversation)
    return ConversationDetail(
        **summary.model_dump(),
        messages=[
            MessageOut(
                **message.model_dump(),
                sources=[Citation(**source) for source in message_sources(message)],
            )
            for message in messages
        ],
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationOut,
    summary="Rename or reconfigure",
)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    session: Session = Depends(get_session),
) -> ConversationOut:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} does not exist.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(conversation, field, value)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return _summary(session, conversation)


@router.delete("/{conversation_id}", response_model=DeleteResponse, summary="Delete a conversation")
def delete_conversation(
    conversation_id: str, session: Session = Depends(get_session)
) -> DeleteResponse:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} does not exist.")

    session.exec(delete(Message).where(col(Message.conversation_id) == conversation_id))
    session.delete(conversation)
    session.commit()
    record_action(
        session,
        "conversation.delete",
        target_type="conversation",
        target_id=conversation_id,
    )
    return DeleteResponse(deleted=True, id=conversation_id)


@router.post(
    "/{conversation_id}/messages/{message_id}/rollback",
    response_model=ConversationDetail,
    summary="Drop a message and everything after it, so a reply can be regenerated",
)
def rollback_conversation(
    conversation_id: str, message_id: str, session: Session = Depends(get_session)
) -> ConversationDetail:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} does not exist.")
    anchor = session.get(Message, message_id)
    if anchor is None or anchor.conversation_id != conversation_id:
        raise NotFoundError(f"Message {message_id} is not part of this conversation.")

    doomed = session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.created_at >= anchor.created_at)
    ).all()
    for message in doomed:
        session.delete(message)
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.commit()
    return get_conversation(conversation_id, session)
