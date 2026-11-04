from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin


class Campaign(TimestampMixin, Base):
    """One campaign, one chat. Moves through fixed stages; see `app.campaign.stages`."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), unique=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(20), default="brief")
    brief: Mapped[str] = mapped_column(Text, default="")
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """Questions for the user, asked one at a time, each with its answer once given."""
    brief_rules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """Points where the brief overrides the brand's documents, for this campaign only."""
    assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """{"summary": ..., "assets": [{"id", "type", "title", "audience", "main_message", "date", "image_idea", "notes"}]}"""
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    noted_conflicts: Mapped[list[int]] = mapped_column(JSONB, default=list)
    """Conflicts already mentioned in the chat, so each is noted once."""
    research: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """Web findings gathered while planning: {"id", "query", "asset_ids", "finding", "url", "title", "date",
    "quote", "removed"}. The ones not removed at approval are the approved research."""
    searches: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """Every web search already run for this campaign, so none runs twice."""
    memories_used: Mapped[list[int]] = mapped_column(JSONB, default=list)
    memory_checked_upto: Mapped[int] = mapped_column(Integer, default=0)
    """The last chat message already looked at for things worth remembering."""
    hand_fixes: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    """How often each "old -> new" wording change was made by hand, to offer "Remember this?"."""
    assets: Mapped[list["Asset"]] = relationship(order_by="Asset.position", cascade="all, delete-orphan")

    @property
    def live_assets(self) -> list["Asset"]:
        """The assets still in the campaign: removed ones are kept, with their history, so a removal can be undone."""
        return [a for a in self.assets if a.state != "removed"]


class Asset(TimestampMixin, Base):
    """One written asset of an approved plan. Its content is always the latest version."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="waiting")
    """waiting, writing, checking, done, failed or removed (taken out of the campaign by chat; can be undone)."""
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """The fields for its type; see `app.campaign.writer.FIELDS`."""
    image: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """{"path", "alt_text", "why"} for a chosen image, or {"suggestion"} when nothing fits."""
    looked_up: Mapped[list[str]] = mapped_column(JSONB, default=list)
    fixed: Mapped[list[str]] = mapped_column(JSONB, default=list)
    """What the automatic fix changed, after the latest check."""
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """Problems still there: {"check", "problem", "quote"}."""
    version: Mapped[int] = mapped_column(Integer, default=0)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))
    """The writing call, for "View prompt"."""
    error: Mapped[str | None] = mapped_column(Text)
    versions: Mapped[list["AssetVersion"]] = relationship(order_by="AssetVersion.number", cascade="all, delete-orphan")


class AssetVersion(TimestampMixin, Base):
    """Every write, fix, chat edit, hand edit and undo is a new version."""

    __tablename__ = "asset_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(40))
    """written, auto fix, chat edit, hand edit or undo."""
    based_on: Mapped[int | None] = mapped_column(Integer)
    """For an undo: the version it brought back."""
    note: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    image: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    call_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
