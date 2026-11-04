"""The Memory page: core memory and campaign history for a brand, which the marketer can change."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.deps import get_ai_service
from app.ai.service import AiService
from app.brand.models import Brand
from app.chat.models import Message
from app.db import get_session
from app.memory.models import CampaignRecord, MemoryItem
from app.memory.service import KINDS, Memory, MemoryChanged, MemoryFull, core, history, item_out, undo_remembered

router = APIRouter(prefix="/api", tags=["memory"])
SessionDep = Annotated[Session, Depends(get_session)]


class MemoryIn(BaseModel):
    text: str = Field(min_length=1)
    kind: str = "preference"


class RecordChange(BaseModel):
    name: str | None = None
    goal: str | None = None
    audience: str | None = None
    angle: str | None = None


class MemoryChange(BaseModel):
    text: str | None = None
    pinned: bool | None = None


def _record_out(record: CampaignRecord) -> dict:
    return {"id": record.id, "name": record.name, "goal": record.goal, "audience": record.audience,
            "angle": record.angle, "assets": record.assets, "images": record.images, "dates": record.dates,
            "chat_id": record.chat_id, "created_at": record.created_at.isoformat()}


@router.get("/brands/{brand_id}/memory")
def get_memory(brand_id: int, session: SessionDep):
    return {"core": [item_out(i) for i in core(session, brand_id)],
            "history": [_record_out(r) for r in history(session, brand_id)]}


@router.post("/brands/{brand_id}/memory", status_code=201)
def add_memory(brand_id: int, body: MemoryIn, session: SessionDep, ai: Annotated[AiService, Depends(get_ai_service)]):
    if body.kind not in KINDS:
        raise HTTPException(400, f"kind is one of {', '.join(KINDS)}")
    if session.get(Brand, brand_id) is None:
        raise HTTPException(404, "Brand not found")
    try:
        item = Memory(session, ai).add(brand_id, body.text, body.kind, None)
    except MemoryFull as full:
        raise HTTPException(409, str(full))
    if item is None:
        raise HTTPException(409, "That is already in memory.")
    previous = getattr(item, "previous", None)
    return {**item_out(item), "dropped": getattr(item, "dropped", None) or [],
            "replaced": previous["text"] if previous else None}


def _item(session: Session, item_id: int) -> MemoryItem:
    item = session.get(MemoryItem, item_id)
    if item is None:
        raise HTTPException(404, "No such memory item.")
    return item


@router.put("/memory/{item_id}")
def change_memory(item_id: int, body: MemoryChange, session: SessionDep):
    item = _item(session, item_id)
    if body.text is not None and body.text.strip():
        item.text = body.text.strip()
    if body.pinned is not None:
        item.pinned = body.pinned
    session.commit()
    return item_out(item)


@router.post("/memory/notes/{message_id}/undo", status_code=204)
def undo_remembered_note(message_id: int, session: SessionDep):
    """The Undo on a "Remembered" note in the chat: removes a new item, or brings back the text it replaced."""
    note = session.get(Message, message_id)
    if note is None or note.kind != "memory":
        raise HTTPException(404, "No such memory note.")
    try:
        undo_remembered(session, note)
    except (MemoryFull, MemoryChanged) as refused:
        raise HTTPException(409, str(refused))


@router.delete("/memory/{item_id}", status_code=204)
def delete_memory(item_id: int, session: SessionDep):
    """Deletes an item from the Memory page. Its "Remembered" notes in the chat are marked as undone."""
    item = _item(session, item_id)
    notes = select(Message).where(Message.kind == "memory", Message.data["item_id"].as_integer() == item_id)
    for note in session.scalars(notes):
        note.data = {**note.data, "undone": True}
    session.delete(item)
    session.commit()


@router.put("/campaign-records/{record_id}")
def change_record(record_id: int, body: RecordChange, session: SessionDep):
    """Corrects what the planner reads about a past campaign. Blank fields are left as they are. The fields
    corrected here are noted, so writing the record again later keeps them."""
    record = session.get(CampaignRecord, record_id)
    if record is None:
        raise HTTPException(404, "No such campaign record.")
    edited = set((record.extra or {}).get("edited", []))
    for name, value in body.model_dump(exclude_none=True).items():
        if value.strip():
            setattr(record, name, value.strip())
            edited.add(name)
    record.extra = {**(record.extra or {}), "edited": sorted(edited)}
    session.commit()
    return _record_out(record)


@router.delete("/campaign-records/{record_id}", status_code=204)
def delete_record(record_id: int, session: SessionDep):
    record = session.get(CampaignRecord, record_id)
    if record is None:
        raise HTTPException(404, "No such campaign record.")
    session.delete(record)
    session.commit()
