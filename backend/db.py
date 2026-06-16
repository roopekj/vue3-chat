"""
SQLAlchemy 2.0 async models + small CRUD helpers.

Each helper manages its own short-lived session. This matters for streaming:
we never hold a DB session open across the (potentially long) generation.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "ui_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "ui_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ui_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    # tool steps, interrupted flag, etc. for re-rendering on reload
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


SYSTEM_PROMPT = """<|think|>
You are a helpful assistant. Only use your tools when necessary."""


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------- serialization helpers ----------


def _conv_dict(c: Conversation) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "extra": m.extra or {},
        "created_at": m.created_at.isoformat(),
    }


# ---------- CRUD ----------


async def create_conversation(title: str = "New chat") -> dict:
    async with SessionLocal() as s:
        c = Conversation(title=title)
        s.add(c)
        await s.commit()
        await s.refresh(c)
        return _conv_dict(c)


async def list_conversations() -> list[dict]:
    async with SessionLocal() as s:
        rows = (
            (
                await s.execute(
                    select(Conversation).order_by(Conversation.updated_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [_conv_dict(c) for c in rows]


async def conversation_exists(conv_id: str) -> bool:
    async with SessionLocal() as s:
        return (await s.get(Conversation, conv_id)) is not None


async def delete_conversation(conv_id: str) -> None:
    async with SessionLocal() as s:
        c = await s.get(Conversation, conv_id)
        if c:
            await s.delete(c)
            await s.commit()


async def rename_conversation(conv_id: str, title: str) -> None:
    async with SessionLocal() as s:
        c = await s.get(Conversation, conv_id)
        if c:
            c.title = title[:255]
            await s.commit()


async def get_messages(conv_id: str) -> list[dict]:
    async with SessionLocal() as s:
        rows = (
            (
                await s.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
            )
            .scalars()
            .all()
        )
        return [_msg_dict(m) for m in rows]


async def add_message(
    conv_id: str, role: str, content: str, extra: dict | None = None
) -> dict:
    async with SessionLocal() as s:
        m = Message(
            conversation_id=conv_id, role=role, content=content, extra=extra or {}
        )
        s.add(m)
        # bump conversation order
        c = await s.get(Conversation, conv_id)
        if c is not None:
            c.updated_at = func.now()
            # set a title from the first user message
            if role == "user" and (c.title in ("New chat", "")):
                c.title = content.strip()[:60] or "New chat"
        await s.commit()
        await s.refresh(m)
        return _msg_dict(m)


async def delete_trailing_assistant(conv_id: str) -> int:
    """Remove the most recent run of assistant messages at the tail (used by regenerate)."""
    async with SessionLocal() as s:
        rows = (
            (
                await s.execute(
                    select(Message)
                    .where(Message.conversation_id == conv_id)
                    .order_by(Message.created_at.desc(), Message.id.desc())
                )
            )
            .scalars()
            .all()
        )
        to_delete = []
        for m in rows:
            if m.role == "assistant":
                to_delete.append(m.id)
            else:
                break
        if to_delete:
            await s.execute(delete(Message).where(Message.id.in_(to_delete)))
            await s.commit()
        return len(to_delete)


async def get_lc_history(conv_id: str) -> list[dict]:
    rows = await get_messages(conv_id)
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in rows:
        if m["role"] == "user":
            msgs.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant" and m["content"].strip():
            msgs.append({"role": "assistant", "content": m["content"]})
    return msgs
