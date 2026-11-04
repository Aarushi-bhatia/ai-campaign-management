"""Read-only access to the AI call log, for "View prompt" and cost views."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AiCall
from app.db import get_session

router = APIRouter(prefix="/api/ai-calls", tags=["ai-calls"])


class AiCallSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step: str
    size: str
    model: str
    chat_id: int | None
    tokens_in: int
    tokens_cached: int
    tokens_cache_write: int
    tokens_out: int
    cost_usd: float | None
    duration_ms: int
    error: str | None
    created_at: datetime


class AiCallOut(AiCallSummary):
    request: dict[str, Any]
    response_text: str | None


SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[AiCallSummary])
def list_calls(session: SessionDep, chat_id: int | None = None):
    query = select(AiCall).order_by(AiCall.id)
    if chat_id is not None:
        query = query.where(AiCall.chat_id == chat_id)
    return list(session.scalars(query))


@router.get("/{call_id}", response_model=AiCallOut)
def get_call(call_id: int, session: SessionDep):
    call = session.get(AiCall, call_id)
    if call is None:
        raise HTTPException(404, "AI call not found")
    return call
