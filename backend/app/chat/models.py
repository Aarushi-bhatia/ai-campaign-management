from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin


class Chat(TimestampMixin, Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="New campaign")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", order_by="Message.id", cascade="all, delete-orphan"
    )


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), default="text")
    """text, question (a question card), note (a one-line status note) or plan (the plan was proposed or changed)."""
    content: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))
    chat: Mapped[Chat] = relationship(back_populates="messages")
