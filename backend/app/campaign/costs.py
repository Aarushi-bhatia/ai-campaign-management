"""What a campaign cost, from the AI call log: per stage, per asset and per edit, with cache hit rates."""

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AiCall
from app.campaign.models import Campaign

STAGES = [
    ("Questions", ("Brief review",)),
    ("Plan", ("Campaign plan", "Plan edit")),
    ("Research", ("Research notes",)),
    ("Brand lookups", ("Brand search",)),
    ("Images", ("Image choice",)),
    ("Writing", ("Write asset",)),
    ("Checks", ("Check asset", "Fix asset")),
    ("Edits", ("Edit request", "Edit asset")),
    ("Memory", ("Memory", "Campaign record")),
]
_ASSET = re.compile(r"asset (\d+)")


def stage_of(step: str) -> str:
    for name, prefixes in STAGES:
        if step.startswith(prefixes):
            return name
    return "Other"


def _totals(calls: list[AiCall]) -> dict[str, Any]:
    tokens_in = sum(c.tokens_in for c in calls)
    cached = sum(c.tokens_cached for c in calls)
    return {
        "calls": len(calls), "cost_usd": round(sum(c.cost_usd or 0 for c in calls), 6), "tokens_in": tokens_in,
        "tokens_cached": cached, "tokens_out": sum(c.tokens_out for c in calls),
        "cache_hit_rate": round(cached / tokens_in, 3) if tokens_in else 0.0,
    }


def report(session: Session, campaign: Campaign) -> dict[str, Any]:
    calls = list(session.scalars(select(AiCall).where(AiCall.chat_id == campaign.chat_id).order_by(AiCall.id)))
    by_stage: dict[str, list[AiCall]] = {}
    by_asset: dict[int, list[AiCall]] = {}
    for call in calls:
        by_stage.setdefault(stage_of(call.step), []).append(call)
        match = _ASSET.search(call.step)
        if match:
            by_asset.setdefault(int(match.group(1)), []).append(call)
    titles = {a.id: a.title for a in campaign.assets}
    order = [name for name, _ in STAGES] + ["Other"]
    edits = [
        {"asset_id": a.id, "title": a.title, "version": v.number, "reason": v.reason, "note": v.note,
         "cost_usd": round(v.cost_usd, 6)}
        for a in campaign.assets for v in a.versions if v.reason in ("chat edit", "hand edit", "undo")
    ]
    return {
        "total": _totals(calls),
        "stages": [{"stage": name, **_totals(by_stage[name])} for name in order if name in by_stage],
        "assets": [{"asset_id": i, "title": titles.get(i, f"asset {i}"), **_totals(c)} for i, c in sorted(by_asset.items())],
        "edits": edits,
        "steps": [{"id": c.id, "step": c.step, "model": c.model, "cost_usd": c.cost_usd, "tokens_in": c.tokens_in,
                   "tokens_cached": c.tokens_cached, "cache_hit_rate": round(c.tokens_cached / c.tokens_in, 3)
                   if c.tokens_in else 0.0} for c in calls],
    }
