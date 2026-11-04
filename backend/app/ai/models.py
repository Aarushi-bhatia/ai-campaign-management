from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class AiCall(TimestampMixin, Base):
    """One request to OpenAI: what was sent, what came back, and what it cost."""

    __tablename__ = "ai_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    step: Mapped[str] = mapped_column(String(200))
    size: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    """The model that answered. The model asked for is in `request`."""
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_cached: Mapped[int] = mapped_column(Integer, default=0)
    tokens_cache_write: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
