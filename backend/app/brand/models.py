from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.ai.transport import EMBEDDING_SIZE
from app.db import Base, TimestampMixin


class Brand(TimestampMixin, Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(500))
    """The settings folder the brand was preloaded from. Empty for uploads."""
    status: Mapped[str] = mapped_column(String(20), default="reading")
    """reading, ready or failed."""
    documents_total: Mapped[int] = mapped_column(Integer, default=0)
    documents_done: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    """False until the user has opened the Brand page once after the first read."""
    read_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    phase: Mapped[str] = mapped_column(String(40), default="")
    """The reading step in progress, for the progress bar: cards, names, links, facts, conflicts or summary."""
    phase_done: Mapped[int] = mapped_column(Integer, default=0)
    phase_total: Mapped[int] = mapped_column(Integer, default=0)

    names_hash: Mapped[str | None] = mapped_column(String(64))
    links_hash: Mapped[str | None] = mapped_column(String(64))
    """What the names and document links were last worked out from, so unchanged input is not sent again."""
    checked_groups: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    """Subjects already checked for conflicts, with the hash of their facts at the time."""

    summary: Mapped[str | None] = mapped_column(Text)
    """The brand summary sent with every campaign request."""
    summary_source_hash: Mapped[str | None] = mapped_column(String(64))
    summary_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    """True once the user has edited the summary. An edited summary is never rebuilt on its own."""
    summary_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    """True when corrections changed the winning facts since the summary was built."""
    summary_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))

    image_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Per-channel image rules taken from the brand's documents."""
    image_rules_hash: Mapped[str | None] = mapped_column(String(64))
    image_rules_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))
    writing_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Rules the free checks apply to copy: banned words, length limits. See `app.brand.reading.writing_rules`."""
    writing_rules_hash: Mapped[str | None] = mapped_column(String(64))
    writing_rules_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))

    files: Mapped[list["BrandFile"]] = relationship(
        back_populates="brand", order_by="BrandFile.path", cascade="all, delete-orphan"
    )


class BrandFile(TimestampMixin, Base):
    """One file from the brand folder. Documents carry their text, basic facts and card."""

    __tablename__ = "brand_files"
    __table_args__ = (UniqueConstraint("brand_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20))
    """document, image, data or other."""
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    text: Mapped[str | None] = mapped_column(Text)
    basics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Facts found without AI: headings, labels at the top of the file, file-name hints, size."""
    sections_sha256: Mapped[str | None] = mapped_column(String(64))
    """The file content the current sections and search vectors were made from."""
    card: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    card_sha256: Mapped[str | None] = mapped_column(String(64))
    card_version: Mapped[int | None] = mapped_column(Integer)
    card_error: Mapped[str | None] = mapped_column(Text)
    card_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))

    facts_sha256: Mapped[str | None] = mapped_column(String(64))
    facts_version: Mapped[int | None] = mapped_column(Integer)
    facts_error: Mapped[str | None] = mapped_column(Text)
    facts_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))

    status: Mapped[str | None] = mapped_column(String(20))
    """Final status after comparing all documents: current, replaced, draft, archived or unclear."""
    status_reason: Mapped[str | None] = mapped_column(Text)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("brand_files.id", ondelete="SET NULL"))

    doc_type: Mapped[str | None] = mapped_column(String(30))
    """The document's type in use: from its card, or from the user's correction."""

    brand: Mapped[Brand] = relationship(back_populates="files")


class Entity(Base):
    """A product, company or customer, with the other names it goes by."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30))
    short_forms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    old_names: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    """Former names, each with the sentence that links it to the current name and the file it is in."""


class DocLink(Base):
    """Something one document says about another: that it replaces it, that it is out of date, and so on."""

    __tablename__ = "doc_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("brand_files.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("brand_files.id", ondelete="CASCADE"))
    effect: Mapped[str] = mapped_column(String(30))
    """replaces, outdated, current, higher_authority or lower_authority."""
    claim: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)


class Fact(Base):
    """One fact or rule from a document, with the sentence it came from."""

    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("brand_files.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    subject_key: Mapped[str] = mapped_column(String(300), index=True)
    """The subject's current name, lower case, after old names and short forms are mapped."""
    attribute: Mapped[str] = mapped_column(String(300))
    value: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    """must, must_not, may or fact."""
    scope: Mapped[str] = mapped_column(String(300))
    evidence: Mapped[str] = mapped_column(Text)


class Conflict(TimestampMixin, Base):
    """Facts from different documents that disagree on one point, and which one wins."""

    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    subject_key: Mapped[str] = mapped_column(String(300), index=True)
    group_hash: Mapped[str] = mapped_column(String(64))
    """What the subject's facts looked like when this conflict was found."""
    point: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(300))
    fact_ids: Mapped[list[int]] = mapped_column(JSONB)
    sides: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """The positions taken: [{"position": ..., "fact_ids": [...]}]. Facts on one side agree."""
    owner_file_ids: Mapped[list[int]] = mapped_column(JSONB)
    """Documents in charge of the conflict's topic."""
    winner_file_id: Mapped[int | None] = mapped_column(ForeignKey("brand_files.id", ondelete="SET NULL"))
    rule: Mapped[str] = mapped_column(String(30))
    """Which rule picked the winner: replaces, owner, approved, newer, live, you or needs_human; only_side_left
    or not_counting when a document's type changed so that at most one side still carries facts."""
    reason: Mapped[str] = mapped_column(Text)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))


class BrandDecision(TimestampMixin, Base):
    """A correction the user made on the Brand page. Corrections always beat what the app worked out."""

    __tablename__ = "brand_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    """document_status, document_kind or conflict_winner."""
    target: Mapped[str] = mapped_column(String(1000))
    """A document path, or for a conflict its subject and document paths."""
    value: Mapped[str] = mapped_column(String(500))


class Section(Base):
    """A piece of a document, split at its headings, with a search vector."""

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("brand_files.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(1000))
    """The heading trail, such as "Pricing > Enterprise"."""
    text: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_SIZE))


class ImageInfo(Base):
    """What the app knows about one image: from the brand's image info file, from the file itself, and from AI."""

    __tablename__ = "image_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("brand_files.id", ondelete="CASCADE"), unique=True)
    record: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    """The image's row from the brand's image info file, as given. Empty when there is none."""
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_source: Mapped[str] = mapped_column(String(20), default="")
    """file (from the image info file), ai (written by the vision model) or name (from the file name only)."""
    image_type: Mapped[str] = mapped_column(String(40), default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    transparent: Mapped[bool] = mapped_column(Boolean, default=False)
    """True when some pixels are see-through."""
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    """The file and record the description was made from."""
    describe_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))
    notes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Restrictions turned into clear fields: usable, retired, expired, channels and so on."""
    notes_hash: Mapped[str | None] = mapped_column(String(64))
    notes_call_id: Mapped[int | None] = mapped_column(ForeignKey("ai_calls.id", ondelete="SET NULL"))
