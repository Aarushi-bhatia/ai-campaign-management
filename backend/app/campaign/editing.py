"""Chat edits once assets are written: work out which asset and part the marketer means, then edit only that.
New assets can be asked for too; they are added to the plan and written, and the others stay as they are.
Assets can also be taken out of the campaign; they are hidden, not deleted, so the removal can be undone.

The web is never searched here unless the marketer asks for research in so many words.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, OutputSchema, array_of, enum, strict_object
from app.campaign import writer
from app.campaign.prompts import ASSET_TYPES, PLAN_CARD
from app.campaign.models import Asset

ROUTE_TASK = """\
The assets of this campaign are written. The marketer sent the message below. Decide what it asks for. \
Assets are numbered as the marketer sees them; the numbers can skip.

- edit: a change to one or more assets. List each asset to change, by its number, with the field to \
change when the message names or clearly means one (one of the asset's fields below), or "" for the \
whole asset. A change "everywhere" or "in all posts" lists every asset it touches. instruction is the \
change in one clear sentence, the same for every asset listed.
- add: new assets for this campaign, such as "two more X posts" or "add a blog post". List each new asset in \
new_assets as a plan card: its type, a short title of its own, and audience, main_message, date, image_idea and \
notes that follow the campaign above and take a different angle from the assets already written. Leave id and \
research_query "". Never use add to change an existing asset, and never use edit to make a new one.
- remove: take whole assets out of the campaign, such as "drop the second email" or "keep only one LinkedIn \
post". List each asset to remove in targets, by its number, with field "". Never use edit to remove or empty \
an asset.
- ask: you can't tell which asset or what change is meant. Ask one short question with two to four options.
- answer: a question or remark, not a change. Answer it in reply.

research_query: only when the marketer asks in so many words for web research, new sources or fresh \
data, a search to run; otherwise "". reply is one short sentence for the marketer.

Assets:
{assets}

Message:
{message}"""

ROUTE_SCHEMA = OutputSchema(
    name="edit_request",
    schema=strict_object({
        "action": enum("edit", "add", "remove", "ask", "answer"),
        "targets": array_of(strict_object({"asset": {"type": "integer"}, "field": TEXT})),
        "instruction": TEXT,
        "research_query": TEXT,
        "reply": TEXT,
        "ask": strict_object({"question": TEXT, "options": TEXT_LIST}),
        "new_assets": array_of(PLAN_CARD),
    }),
)

MAX_NEW_ASSETS = 5
"""At most this many assets are added by one message."""


@dataclass
class Route:
    action: str
    reply: str
    targets: list[tuple[Asset, str]] = field(default_factory=list)
    instruction: str = ""
    research_query: str = ""
    ask: dict[str, Any] | None = None
    new_assets: list[dict[str, Any]] = field(default_factory=list)


def number_of(asset: Asset) -> int:
    """An asset's number as its tab shows it: its place in the plan. Removed or unwritten assets keep their
    place, so the numbers can skip (1, 3, 4), and the model and the marketer use the same ones."""
    return asset.position + 1


def assets_text(assets: list[Asset]) -> str:
    lines = []
    for asset in assets:
        fields = ", ".join(writer.FIELDS[asset.type])
        preview = " ".join(json.dumps(asset.content or {}, ensure_ascii=False).split())[:240]
        lines.append(f"{number_of(asset)}. {writer.TYPE_LABELS[asset.type]} “{asset.title}” (fields: {fields}): {preview}")
    return "\n".join(lines)


def route_from(raw: dict[str, Any], assets: list[Asset]) -> Route:
    """Only real asset numbers and fields; an edit with no valid target becomes a question."""
    reply = raw["reply"].strip()
    if raw["action"] == "add":
        cards = [c for c in raw["new_assets"] if c["type"] in ASSET_TYPES and c["title"].strip()][:MAX_NEW_ASSETS]
        if cards:
            return Route("add", reply, new_assets=cards)
    if raw["action"] == "ask" and raw["ask"]["question"].strip():
        return Route("ask", reply, ask={"question": raw["ask"]["question"].strip(), "options": raw["ask"]["options"]})
    if raw["action"] in ("edit", "remove"):
        targets = []
        by_number = {number_of(a): a for a in assets}
        for target in raw["targets"]:
            if target["asset"] in by_number:
                asset = by_number[target["asset"]]
                name = target["field"].strip() if target["field"].strip() in writer.FIELDS[asset.type] else ""
                if all(asset.id != a.id for a, _ in targets):
                    targets.append((asset, name))
        if targets and raw["action"] == "remove":
            return Route("remove", reply, [(asset, "") for asset, _ in targets])
        if targets and raw["instruction"].strip():
            return Route("edit", reply, targets, raw["instruction"].strip(), raw["research_query"].strip())
    if raw["action"] in ("edit", "add", "remove"):
        # No usable target. A choice between assets only makes sense when there are two or more.
        if len(assets) > 1:
            return Route("ask", reply, ask={"question": "Which asset should I change?", "every_asset": True,
                                            "options": [f"{number_of(a)}. {a.title}" for a in assets]})
        named = f" in “{assets[0].title}”" if assets else ""
        return Route("answer", f"I couldn't tell what to do. Say what to change{named}, or ask for new assets, "
                     "for example “add two more X posts”.")
    return Route("answer", reply or "Noted.")
