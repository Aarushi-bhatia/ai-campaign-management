"""What the agent keeps between campaigns, per brand.

- Core memory: general corrections, preferences and decisions. Small (about 50 items) and always in the
  fixed prompt part, so every call follows it.
- Campaign history: one short record per finished campaign. Only the planning step reads it, so it can
  grow without making every call longer.

New items are suggested by the small model from the marketer's own messages and saved straight away,
with an Undo note in the chat.
"""

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.ai.service import AiService
from app.brand.evidence import normalize
from app.brand.models import Brand
from app.campaign.models import Campaign
from app.chat.models import Chat, Message
from app.config import ModelSize
from app.memory.models import CampaignRecord, MemoryItem

CORE_LIMIT = 50
_WORD = re.compile(r"[a-z0-9]+")
_FILLER = {"a", "an", "the", "it", "its", "to", "of", "for", "in", "on", "and", "or", "be", "is", "are", "should",
           "always", "all", "every", "our", "we", "you", "your", "with", "keep", "make", "please", "must", "do"}
_NEGATIONS = {"no", "not", "never", "don", "dont", "avoid", "without", "nor", "stop"}
_CHANNELS = {"email", "newsletter", "linkedin", "x", "twitter", "tweet", "blog", "landing", "website", "social"}


class MemoryChanged(Exception):
    """The item was changed after its "Remembered" note, so that note's Undo would reverse the later change."""


class MemoryFull(Exception):
    """Core memory is at its limit and every item is pinned, so nothing can make room."""
HISTORY_IN_PLANNING = 5
KINDS = ("correction", "preference", "decision")

SUGGEST_INSTRUCTIONS = """\
You keep the memory of a brand's campaign agent. From the marketer's new messages, pick only what is \
worth remembering for future campaigns:
- correction: a general rule they corrected the agent on ("never call it a platform").
- preference: how they like campaigns done: asset mix, tone, length, format.
- decision: how they settled a question that will come up again.

Don't keep: details of this campaign only (its dates, audience, offer, launch, images, approvals or \
asset mix), one-off edits to one asset, choices the marketer made for this campaign's brief, anything the \
brand summary below already says, or anything already in memory. Only keep what the marketer says would \
hold for every future campaign. When in doubt, keep nothing. Compare each new \
item with memory. When it says exactly what an item in memory says, only worded differently and with the \
same scope, give that item's id in same_as. When it changes an item in memory (contradicts it, updates a \
number, narrows or widens it to other channels or cases), give that item's id in changes. A rule for one \
channel, campaign or case is never the same as a broader one. Otherwise, or when unsure, give 0 for both: \
keeping two items is safer than losing one.

Each item is one short sentence, written as an instruction to the agent. Most messages hold nothing \
worth keeping; then return no items.

=== BRAND SUMMARY ===
{summary}"""

SUGGEST_SCHEMA = OutputSchema(
    name="memory_items",
    schema=strict_object({"items": array_of(strict_object({
        "text": TEXT, "kind": enum(*KINDS), "same_as": {"type": "integer"}, "changes": {"type": "integer"},
    }))}),
)

RECORD_INSTRUCTIONS = """\
Write a short record of a finished campaign, for planning later ones: name (a few words), goal, \
audience and main angle, one short line each."""

RECORD_SCHEMA = OutputSchema(
    name="campaign_record",
    schema=strict_object({"name": TEXT, "goal": TEXT, "audience": TEXT, "angle": TEXT}),
)


def core(session: Session, brand_id: int) -> list[MemoryItem]:
    return list(session.scalars(
        select(MemoryItem).where(MemoryItem.brand_id == brand_id).order_by(MemoryItem.pinned.desc(), MemoryItem.id)
    ))


def core_texts(session: Session, brand_id: int) -> list[str]:
    return [item.text for item in core(session, brand_id)]


def history(session: Session, brand_id: int, skip_campaign: int | None = None,
            limit: int | None = None) -> list[CampaignRecord]:
    """Newest first. The limit and the skip run in the database, so planning never loads every record."""
    query = select(CampaignRecord).where(CampaignRecord.brand_id == brand_id).order_by(CampaignRecord.id.desc())
    if skip_campaign is not None:
        query = query.where(or_(CampaignRecord.campaign_id.is_(None), CampaignRecord.campaign_id != skip_campaign))
    return list(session.scalars(query.limit(limit)))


def recent_images(session: Session, brand_id: int, skip_campaign: int | None = None) -> frozenset[str]:
    """Images the brand's recent campaigns used, so a new campaign can avoid repeating them."""
    return frozenset(path for r in history(session, brand_id, skip_campaign, HISTORY_IN_PLANNING) for path in r.images)


def near_duplicate(a: str, b: str) -> bool:
    """True only for the same instruction in other words: the same words in any order, leaving out filler and
    trivial wording ("Keep emails short", "Emails should be short"). Any added, dropped or swapped word keeps
    them apart ("Use British spelling" and "... in emails"; "LinkedIn" and "X"), and so does a negation in a
    different place ("use A, not B" and "use B, not A"). Everything else is the model's call."""
    words_a, words_b = _words(a), _words(b)
    if not words_a or sorted(words_a) != sorted(words_b):
        return False
    return words_a == words_b or not set(words_a) & _NEGATIONS


def changes_meaning(a: str, b: str) -> bool:
    """A check on the model's "same": two items that differ in a negation, a number or a channel never say
    the same thing, whatever their wording."""
    words_a, words_b = set(_words(a)), set(_words(b))
    return any(words_a & kind != words_b & kind for kind in (_NEGATIONS, _CHANNELS)) or \
        {w for w in words_a if w.isdigit()} != {w for w in words_b if w.isdigit()}


def _words(text: str) -> list[str]:
    """The words that carry the instruction, in order. Plural endings are trimmed after the filler is left out,
    or "always" would stay as "alway"."""
    words = [w for w in _WORD.findall(text.lower()) if w not in _FILLER]
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]


def history_text(session: Session, brand_id: int, skip_campaign: int | None = None) -> str:
    records = history(session, brand_id, skip_campaign, HISTORY_IN_PLANNING)
    return "\n".join(
        f"- {r.name} ({r.dates or 'no dates'}): goal {r.goal}; audience {r.audience}; angle {r.angle}; "
        f"assets {', '.join(r.assets) or 'none'}; images {', '.join(r.images) or 'none'}"
        for r in records
    )


def _answers_to_questions(messages: list[Message]) -> set[int]:
    """The marketer's replies to the agent's question cards. They settle this campaign only, so they are never
    learned from: an answer like "hold the hero for Brand approval" is not a rule for every campaign."""
    answers, after_question = set(), False
    for message in messages:
        if message.role == "user":
            if after_question:
                answers.add(message.id)
            after_question = False
        elif message.kind == "question":
            after_question = True
    return answers


def undo_remembered(session: Session, note: Message) -> None:
    """The Undo on a "Remembered" note: a new item is deleted; a rewritten one gets its old text back. Items that
    were dropped to make room for it come back as they were (same id, so same place in memory), unless memory
    holds their wording again by now; the chat says which were left out.

    Undo never reverses a later change: when the item was edited, pinned or rewritten after the note, it is
    refused (MemoryChanged), as it is when the dropped items no longer fit (MemoryFull). Either way nothing
    changes."""
    data = note.data or {}
    if data.get("undone"):
        return
    item = session.get(MemoryItem, data.get("item_id"))
    if item is not None and note.created_at is not None and item.updated_at > note.created_at:
        raise MemoryChanged("This item was changed after it was remembered, so Undo would reverse that change too. "
                            "Edit or delete it on the Memory page instead.")
    previous, dropped = data.get("previous"), data.get("dropped", [])
    if item is not None and previous:
        item.text, item.kind, item.source_chat_id = previous["text"], previous["kind"], previous["source_chat_id"]
    elif item is not None:
        brand_id = item.brand_id
        session.delete(item)
        session.flush()
        held = {normalize(i.text) for i in core(session, brand_id)}
        gone = [d for d in dropped if session.get(MemoryItem, d["id"]) is None]
        back = [d for d in gone if normalize(d["text"]) not in held]
        if len(back) < len(gone) and note.chat_id is not None:
            listed = "; ".join(f"“{d['text']}”" for d in gone if d not in back)
            session.add(Message(chat_id=note.chat_id, role="assistant", kind="note",
                                content=f"Undone. Not brought back, as memory already holds it again: {listed}."))
        if back and len(core(session, brand_id)) + len(back) > CORE_LIMIT:
            session.rollback()
            raise MemoryFull(f"Memory has filled up again since, so the {len(back)} dropped item"
                             f"{'s' if len(back) > 1 else ''} can't come back. Unpin or delete an item to make room.")
        session.add_all(MemoryItem(id=d["id"], brand_id=brand_id, text=d["text"], kind=d["kind"], pinned=d["pinned"],
                                   source_chat_id=d["source_chat_id"], created_at=datetime.fromisoformat(d["created_at"]))
                        for d in back)
    note.data = {**data, "undone": True}
    session.commit()


def replace_changed(session: Session, note: Message) -> None:
    """The "Replace it" on a "Remembered" note whose item changes an older one: the older one goes, kept whole in
    the note, so the note's Undo brings it back along with removing the new one."""
    data = note.data or {}
    changes = data.get("changes")
    if not changes or data.get("undone") or data.get("replaced"):
        raise MemoryChanged("There is nothing to replace on this note any more.")
    old = session.get(MemoryItem, changes["id"])
    if old is None:
        raise MemoryChanged("That older item is no longer in memory.")
    kept = {"id": old.id, "text": old.text, "kind": old.kind, "pinned": old.pinned, "source_chat_id": old.source_chat_id,
            "created_at": old.created_at.isoformat()}
    session.delete(old)
    note.data = {**data, "replaced": True, "dropped": [*data.get("dropped", []), kept]}
    session.commit()


class Memory:
    def __init__(self, session: Session, ai: AiService) -> None:
        self._session = session
        self._ai = ai
        self.refused: list[str] = []
        """Items `suggest` couldn't save because memory is full of pinned items."""

    def add(self, brand_id: int, text: str, kind: str, chat_id: int | None, same_as: int = 0,
            changes: int = 0) -> MemoryItem | None:
        """Saves an item. None when memory already holds it: the same words (`near_duplicate`), or the item the
        model gave as `same_as`, unless the two differ in meaning after all. That item stays as it was, with its
        own wording and source. An item that changes one in memory never overwrites it: both are kept, and the
        saved item's `changes` names the old one, so the note can offer to replace it. When memory is full, the
        oldest unpinned item makes room, and `dropped` says which; when every item is pinned, MemoryFull, and
        nothing changes."""
        text = text.strip()
        if not text:
            return None
        items = core(self._session, brand_id)
        if any(normalize(i.text) == normalize(text) or near_duplicate(i.text, text) for i in items):
            return None
        same = next((i for i in items if i.id == same_as), None)
        if same is not None and not changes_meaning(same.text, text):
            return None
        changed = next((i for i in items if i.id == changes), None) or same
        if len(items) >= CORE_LIMIT and all(i.pinned for i in items):
            raise MemoryFull(f"Memory is full: all {len(items)} items are pinned. Unpin or delete one to make room.")
        item = MemoryItem(brand_id=brand_id, text=text, kind=kind, source_chat_id=chat_id)
        self._session.add(item)
        self._session.flush()
        # For the note: the texts to show, and everything needed for its Undo to bring the items back.
        item.dropped_items = self._keep_small(brand_id, keep=item.id)
        item.dropped = [d["text"] for d in item.dropped_items]
        gone = {d["id"] for d in item.dropped_items}
        # The item it changes, for the note's "Replace it"; none when that one was just dropped to make room.
        item.changes = {"id": changed.id, "text": changed.text} if changed is not None and changed.id not in gone else None
        self._session.commit()
        return item

    def suggest(self, chat: Chat, campaign: Campaign) -> list[MemoryItem]:
        """Looks at the marketer's messages since the last look, and saves what is worth keeping."""
        new = [m for m in chat.messages if m.id > campaign.memory_checked_upto]
        if not new:
            return []
        campaign.memory_checked_upto = new[-1].id
        first_user = next((m.id for m in chat.messages if m.role == "user"), None)
        answers = _answers_to_questions(chat.messages)
        said = [m for m in new if m.role == "user" and m.id != first_user and m.id not in answers]
        if not said:
            self._session.commit()
            return []
        brand = self._session.get_one(Brand, campaign.brand_id)
        known = "\n".join(f"[{i.id}] {i.text}" for i in core(self._session, brand.id)) or "(empty)"
        messages = "\n".join(f"- {m.content}" for m in said)
        reply = self._ai.complete(
            step="Memory", size=ModelSize.SMALL, output_schema=SUGGEST_SCHEMA, chat_id=chat.id, brand_id=brand.id,
            prompt=Prompt(fixed=SUGGEST_INSTRUCTIONS.format(summary=brand.summary or "(none)"),
                          task=[Turn(role="user", content=f"=== MEMORY ===\n{known}\n\n=== NEW MESSAGES ===\n{messages}")]),
            cache_key=f"brand-{brand.id}",
        )
        saved = []
        for raw in json.loads(reply.text)["items"]:
            try:
                item = self.add(brand.id, raw["text"], raw["kind"], chat.id, raw["same_as"], raw["changes"])
            except MemoryFull:
                self.refused.append(raw["text"].strip())
                continue
            if item is not None:
                saved.append(item)
        self._session.commit()
        return saved

    def record(self, chat: Chat, campaign: Campaign) -> CampaignRecord:
        """The short history record of a finished campaign. Writing it again (after Write again, or assets added
        later) updates the same record, but leaves the fields the marketer corrected on the Memory page as
        they are: their wording beats the model's."""
        plan = campaign.plan or {"summary": "", "assets": []}
        reply = self._ai.complete(
            step="Campaign record", size=ModelSize.SMALL, output_schema=RECORD_SCHEMA, chat_id=chat.id,
            brand_id=campaign.brand_id,
            prompt=Prompt(fixed=RECORD_INSTRUCTIONS, task=[Turn(role="user", content=f"Brief:\n{campaign.brief}\n\n"
                                                                f"Plan: {plan['summary']}")]),
        )
        raw = json.loads(reply.text)
        dates = sorted({a["date"] for a in plan["assets"] if a.get("date") and a["date"] != "to be set"})
        record = self._session.scalars(select(CampaignRecord).where(CampaignRecord.campaign_id == campaign.id)).first()
        if record is None:
            record = CampaignRecord(brand_id=campaign.brand_id, campaign_id=campaign.id, chat_id=chat.id)
            self._session.add(record)
        written = {"name": raw["name"].strip() or chat.title, "goal": raw["goal"].strip(),
                   "audience": raw["audience"].strip(), "angle": raw["angle"].strip()}
        edited = set((record.extra or {}).get("edited", []))
        for name, value in written.items():
            if name not in edited:
                setattr(record, name, value)
        record.assets = [f"{a.type}: {a.title}" for a in campaign.live_assets]
        record.images = sorted({a.image["path"] for a in campaign.live_assets if a.image and a.image.get("path")})
        record.dates = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else "")
        self._session.commit()
        return record

    def _keep_small(self, brand_id: int, keep: int) -> list[dict[str, Any]]:
        """Drops the oldest unpinned items once core memory is over its limit, never the one just added.
        Returns them in full, so the marketer is told and an Undo can bring them back."""
        items = core(self._session, brand_id)
        extra = len(items) - CORE_LIMIT
        dropped = [i for i in items if not i.pinned and i.id != keep][:max(extra, 0)]
        for item in dropped:
            self._session.delete(item)
        return [{"id": i.id, "text": i.text, "kind": i.kind, "pinned": i.pinned, "source_chat_id": i.source_chat_id,
                 "created_at": i.created_at.isoformat()} for i in dropped]


def item_out(item: MemoryItem) -> dict[str, Any]:
    return {"id": item.id, "text": item.text, "kind": item.kind, "pinned": item.pinned,
            "source_chat_id": item.source_chat_id, "created_at": item.created_at.isoformat()}
