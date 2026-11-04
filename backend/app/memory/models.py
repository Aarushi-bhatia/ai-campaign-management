from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utc_now


class MemoryItem(TimestampMixin, Base):
    """One thing the agent keeps between campaigns for a brand. Core memory is always in the prompt."""

    __tablename__ = "memory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    """correction, preference or decision."""
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    source_chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CampaignRecord(TimestampMixin, Base):
    """A short record of a finished campaign. Only the planning step looks these up."""

    __tablename__ = "campaign_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), unique=True)
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text)
    assets: Mapped[list[str]] = mapped_column(JSONB, default=list)
    images: Mapped[list[str]] = mapped_column(JSONB, default=list)
    dates: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
