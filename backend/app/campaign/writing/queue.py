"""Writes an approved plan's assets in the background, a few at a time, in plan order."""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.ai.models import AiCall
from app.brand.models import Brand
from app.brand.reading import writing_rules
from app.campaign import stages
from app.campaign.models import Asset, Campaign
from app.campaign.runtime import Runtime
from app.campaign.writing.assets import AssetWork
from app.chat.models import Chat, Message
from app.memory.service import Memory

log = logging.getLogger(__name__)


def resume_interrupted(runtime: Runtime) -> None:
    """Writing that was cut off by a restart starts again for the assets not yet done. One whose draft was
    already saved (cut off while checking) is only checked, not written again."""
    with runtime.sessions() as session:
        stuck = list(session.scalars(select(Campaign).where(Campaign.stage == stages.WRITING)))
        for campaign in stuck:
            for asset in campaign.assets:
                if asset.state in ("writing", "checking"):
                    asset.state = "waiting"
        session.commit()
        ids = [c.id for c in stuck]
    for campaign_id in ids:
        log.info("Resuming the interrupted writing of campaign %s", campaign_id)
        runtime.jobs.submit(lambda campaign_id=campaign_id: write_campaign(runtime, campaign_id))


def write_campaign(runtime: Runtime, campaign_id: int) -> None:
    """Writes the campaign's unfinished assets. Whatever fails, the campaign ends at done, never stuck at
    writing: assets that weren't written are marked failed, so Write again can retry them."""
    try:
        _write_all(runtime, campaign_id)
    except Exception as error:
        log.exception("Writing campaign %s failed", campaign_id)
        _give_up(runtime, campaign_id, error)


def _give_up(runtime: Runtime, campaign_id: int, error: Exception) -> None:
    with runtime.sessions() as session:
        campaign = session.get_one(Campaign, campaign_id)
        unfinished = [a for a in campaign.live_assets if a.state != "done"]
        for asset in unfinished:
            asset.state, asset.error = "failed", str(error)
        campaign.stage = stages.DONE
        session.add(Message(chat_id=campaign.chat_id, role="assistant", kind="text", content=(
            f"Writing stopped: {error}. {len(unfinished)} asset{'s' if len(unfinished) != 1 else ''} not written; "
            "press Write again on an asset to retry.")))
        session.commit()


def _write_all(runtime: Runtime, campaign_id: int) -> None:
    with runtime.sessions() as session:
        campaign = session.get_one(Campaign, campaign_id)
        writing_rules.ensure(session, runtime.ai(session), session.get_one(Brand, campaign.brand_id))
        waiting = [a.id for a in campaign.live_assets if a.state != "done"]
    if not waiting:
        return _finish_in_new_session(runtime, campaign_id)
    # The first asset is written alone, so the prompt start every asset shares is in the cache
    # before the rest start together.
    _write_one(runtime, campaign_id, waiting[0])
    with ThreadPoolExecutor(max_workers=max(1, runtime.settings.writing_workers)) as pool:
        list(pool.map(lambda asset_id: _write_one(runtime, campaign_id, asset_id), waiting[1:]))
    _finish_in_new_session(runtime, campaign_id)


def _finish_in_new_session(runtime: Runtime, campaign_id: int) -> None:
    with runtime.sessions() as session:
        _finish(runtime, session, campaign_id)


def _write_one(runtime: Runtime, campaign_id: int, asset_id: int) -> None:
    with runtime.sessions() as session:
        campaign = session.get_one(Campaign, campaign_id)
        asset = session.get_one(Asset, asset_id)
        work = AssetWork(session, runtime.ai(session), session.get_one(Brand, campaign.brand_id), campaign)
        try:
            line = work.write(asset)
        except Exception as error:
            log.exception("Writing asset %s failed", asset_id)
            session.rollback()
            asset.state, asset.error = "failed", str(error)
            line = f"Couldn't write “{asset.title}”: {error}"
        session.add(Message(chat_id=campaign.chat_id, role="assistant", kind="note", content=line,
                            ai_call_id=asset.call_id))
        session.commit()


def _finish(runtime: Runtime, session, campaign_id: int) -> None:
    campaign = session.get_one(Campaign, campaign_id)
    chat = session.get_one(Chat, campaign.chat_id)
    campaign.stage = stages.DONE
    failed = [a for a in campaign.live_assets if a.state == "failed"]
    cost = session.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0)).where(AiCall.chat_id == chat.id))
    done = len(campaign.live_assets) - len(failed)
    text = (f"{done} of {len(campaign.live_assets)} assets written. Campaign cost so far: ${cost:.2f}. "
            "Ask for changes here, or type straight into an asset.")
    if failed:
        text += f" {len(failed)} failed; press Write again on the card to retry."
    chat.messages.append(Message(role="assistant", kind="text", content=text))
    session.commit()
    memory = Memory(session, runtime.ai(session))
    try:
        memory.record(chat, campaign)
        chat.messages.extend(memory_notes(memory, memory.suggest(chat, campaign)))
        session.commit()
    except Exception:
        log.exception("Memory after campaign %s failed", campaign_id)
        session.rollback()


def remembered_note(item) -> Message:
    """When memory was full, the note says which old item was dropped to make room, and keeps it whole for the
    Undo. When the item changes one already in memory, both are kept, and the note offers to replace the old one."""
    dropped = getattr(item, "dropped_items", None) or []
    changes = getattr(item, "changes", None)
    note = "".join(f" Memory was full, so the oldest unpinned item was dropped: “{d['text']}”." for d in dropped)
    if changes:
        note += f" This changes “{changes['text']}”, which is still in memory: replace it, or keep both."
    data = {"item_id": item.id, **({"dropped": dropped} if dropped else {}),
            **({"changes": changes} if changes else {})}
    return Message(role="assistant", kind="memory", content=f"Remembered: {item.text}{note}", data=data)


def full_note(texts: list[str]) -> Message:
    listed = "; ".join(f"“{text}”" for text in texts)
    return Message(role="assistant", kind="note", content=(
        f"Memory is full and every item is pinned, so I couldn't remember {listed}. Unpin or delete an item on "
        "the Memory page to make room."))


def memory_notes(memory: Memory, items) -> list[Message]:
    notes = [remembered_note(item) for item in items]
    return [*notes, full_note(memory.refused)] if memory.refused else notes
