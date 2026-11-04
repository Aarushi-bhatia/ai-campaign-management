from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BrandSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    documents_total: int
    documents_done: int
    phase: str
    phase_done: int
    phase_total: int
    error: str | None
    reviewed: bool
    created_at: datetime
    read_finished_at: datetime | None


class DocumentOut(BaseModel):
    id: int
    path: str
    tokens: int
    sections: int
    facts: int
    basics: dict[str, Any] | None
    card: dict[str, Any] | None
    card_error: str | None
    card_call_id: int | None
    facts_error: str | None
    facts_call_id: int | None
    doc_type: str | None
    status: str | None
    status_reason: str | None
    replaced_by: str | None


class OtherFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str
    kind: str
    size_bytes: int


class ReadingCostOut(BaseModel):
    usd: float
    calls: int
    tokens_in: int
    tokens_out: int


class ConflictFactOut(BaseModel):
    id: int
    side: int
    path: str
    attribute: str
    value: str
    kind: str
    evidence: str


class ConflictOut(BaseModel):
    id: int
    subject: str
    point: str
    topic: str
    rule: str
    reason: str
    winner: str | None
    owners: list[str]
    sides: list[str]
    """The position each side takes, in order."""
    winning_side: int | None
    facts: list[ConflictFactOut]
    target: str
    """Name to use when correcting this conflict's winner."""
    decided_target: str | None = None
    """The name of the saved choice that applies, which can be older than `target` (a document joined since)."""
    call_id: int | None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: str
    short_forms: list[str]
    old_names: list[dict[str, str]]


class LinkOut(BaseModel):
    source: str
    target: str
    effect: str
    claim: str
    evidence: str


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    target: str
    value: str
    created_at: datetime


class ImageOut(BaseModel):
    id: int
    path: str
    url: str
    title: str
    description: str
    description_source: str
    image_type: str
    tags: list[str]
    width: int
    height: int
    transparent: bool
    record: dict[str, Any]
    notes: dict[str, Any] | None
    usable_override: str | None
    blocked: str | None
    """Why the image can't be used on any campaign channel, or None when some channel can use it."""
    channels: dict[str, str | None]
    """For each campaign channel's main image: why it is blocked there, or None when it can be used."""
    describe_call_id: int | None
    notes_call_id: int | None


class BrandOut(BrandSummary):
    documents: list[DocumentOut]
    other_files: list[OtherFileOut]
    reading_cost: ReadingCostOut
    conflicts: list[ConflictOut]
    entities: list[EntityOut]
    links: list[LinkOut]
    decisions: list[DecisionOut]
    excluded: list[str] = []
    """Folders and files left out of the last upload."""
    summary: str | None
    summary_edited: bool
    summary_stale: bool
    summary_call_id: int | None
    images: list[ImageOut]
    image_rules: dict[str, Any] | None
    image_rules_call_id: int | None


class CorrectionIn(BaseModel):
    kind: Literal["document_status", "document_kind", "conflict_winner", "image_usable"]
    target: str = Field(min_length=1)
    value: str = Field(min_length=1)


class SummaryIn(BaseModel):
    text: str = Field(min_length=1)


class PickIn(BaseModel):
    channel: Literal["email", "linkedin", "x", "blog", "landing_page"]
    asset_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    slot: Literal["main", "inline"] = "main"
    campaign_rules: str = ""
    exclude: list[str] = []


class ChoiceOut(BaseModel):
    path: str
    url: str
    why: str
    alt_text: str


class BlockedOut(BaseModel):
    path: str
    reason: str


class PickOut(BaseModel):
    choices: list[ChoiceOut]
    suggestion: str
    blocked: list[BlockedOut]
    call_id: int | None
