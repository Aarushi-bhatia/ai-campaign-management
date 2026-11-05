from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    kind: str
    content: str
    data: dict[str, Any] | None
    ai_call_id: int | None
    created_at: datetime


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    stage: str
    brief: str
    brief_rules: list[str]
    assumptions: list[str]
    plan: dict[str, Any] | None
    plan_version: int
    approved_at: datetime | None
    research: list[dict[str, Any]]


class ChatSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime


class ChatOut(ChatSummary):
    messages: list[MessageOut]
    campaign: CampaignOut


class SendMessage(BaseModel):
    content: str = Field(min_length=1)


class AnswerIn(BaseModel):
    question_id: int
    answer: str = Field(min_length=1)


class PlanIn(BaseModel):
    assets: list[dict[str, Any]]
    base_version: int | None = None
    """The plan version the cards show. When the plan has moved on since, the change isn't saved."""
    image_exclusions: list[str] | None = None
    """The image types still kept off. The plan shows them so a wrong one can be removed; none can be added here."""
    brief_rules: list[str] | None = None
    """The campaign rules still kept (points where the brief beats the brand). One can be removed; none added."""


class AssetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    reason: str
    note: str
    content: dict[str, Any]
    image: dict[str, Any] | None
    warnings: list[dict[str, Any]]
    call_ids: list[int]
    cost_usd: float
    based_on: int | None
    created_at: datetime


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: str
    position: int
    type: str
    title: str
    state: str
    content: dict[str, Any] | None
    image: dict[str, Any] | None
    image_url: str | None = None
    looked_up: list[str]
    fixed: list[str]
    warnings: list[dict[str, Any]]
    version: int
    call_id: int | None
    prompt_call_id: int | None = None
    """The AI call that wrote the current version's text (an edit or fix, not only the first draft)."""
    hand_edited: bool = False
    """The current text was edited by hand after that call, so the prompt shows what it was based on."""
    error: str | None
    draft_for: str = ""
    """Set when the plan says this asset is only an optional draft for that person to post themselves."""


class AssetChange(BaseModel):
    asset: AssetOut
    messages: list[MessageOut]


class NewChatIn(BaseModel):
    brand_id: int | None = None


class HandEditIn(BaseModel):
    content: dict[str, Any]
    base_version: int | None = None
    """The version the typing started from. If the asset has a newer one, the edit is refused (409)."""
