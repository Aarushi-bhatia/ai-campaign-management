"""Chat edits once assets are written: work out which asset and part the marketer means, then edit only that.
New assets can be asked for too; they are added to the plan and written, and the others stay as they are.
Assets can also be taken out of the campaign; they are hidden, not deleted, so the removal can be undone. An
image can be changed too: the picker runs again for that asset, and its text stays as it is.

The web is never searched here unless the marketer asks for research in so many words.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, OutputSchema, array_of, enum, strict_object
from app.campaign.checking import free
from app.campaign.models import Asset
from app.campaign.prompts import ASSET_TYPES, PLAN_CARD
from app.campaign.writing import writer

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
- image: a different image for one or more assets, or none, such as "use another photo on the landing page", \
"a photo without people for the email" or "no image on the X post". List each asset in targets, with field "". \
instruction is what the new image should be or show, "no image" to take it off, or "" when the message only asks \
for a different one. Never use edit for an image: the text stays as it is.
- ask: you can't tell what change is meant. Ask one short question with two to four options. When only the \
asset is unclear, ask which one in a short question naming the kind of asset and the change when the message \
gives them ("Which LinkedIn post should I shorten?"), give no options, and list in targets, with field "", every \
asset the message could mean: only the LinkedIn posts for "the LinkedIn post", all of them for "one of them". The \
app offers those assets by number and title, so none is left out or lumped with another.
- answer: a question or remark, not a change. Answer it in reply. Also use answer when every asset the message \
is about already does what it asks, such as a length limit each one is already within (each asset's sizes are \
below): say so in reply, and list nothing to edit. A message that also sets a rule for later ("from now on…") is \
remembered either way.

research_query: only when the marketer asks in so many words for web research, new sources or fresh \
data, a search to run; otherwise "". reply is one short sentence for the marketer. For edit, add, remove and \
image, say what you did in the past tense ("I shortened the email's subject line.", never "I'll shorten…"); \
the app lists what happened to each asset under it.

Assets:
{assets}

Message:
{message}"""

ROUTE_SCHEMA = OutputSchema(
    name="edit_request",
    schema=strict_object({
        "action": enum("edit", "add", "remove", "image", "ask", "answer"),
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
        lines.append(f"{number_of(asset)}. {writer.TYPE_LABELS[asset.type]} “{asset.title}” "
                     f"(fields: {fields}; sizes: {sizes_of(asset)}): {preview}")
    return "\n".join(lines)


def sizes_of(asset: Asset) -> str:
    """Each text field's length, so the model can tell a length request is already met: the preview is cut
    short, and models count characters badly. Sections are added up into one field."""
    texts: dict[str, list[str]] = {}
    for name, text in free.texts_of(asset.content or {}):
        if name not in free.LINK_FIELDS:
            texts.setdefault(name, []).append(text)
    return "; ".join(f"{name} {sum(len(t) for t in parts)} characters, {sum(len(t.split()) for t in parts)} words"
                     for name, parts in texts.items()) or "empty"


def route_from(raw: dict[str, Any], assets: list[Asset]) -> Route:
    """Only real asset numbers and fields; an edit with no valid target becomes a question."""
    reply = raw["reply"].strip()
    action = raw["action"]
    route = None
    if action == "add":
        route = _add_route(raw, reply)
    elif action == "ask":
        route = _ask_route(raw, reply, assets)
    elif action in ("edit", "remove", "image"):
        route = _targeted_route(raw, reply, _targets(raw["targets"], assets))
    if route is not None:
        return route
    if action in ("edit", "add", "remove", "image"):
        return _which_asset(assets, reply)
    return Route("answer", reply or "Noted.")


def _add_route(raw: dict[str, Any], reply: str) -> Route | None:
    cards = [c for c in raw["new_assets"] if c["type"] in ASSET_TYPES and c["title"].strip()][:MAX_NEW_ASSETS]
    return Route("add", reply, new_assets=cards) if cards else None


def _ask_route(raw: dict[str, Any], reply: str, assets: list[Asset]) -> Route | None:
    """A question with no options is about which asset: the assets the model says the message could mean are
    offered, by their number and title. With fewer than two of them, every asset is offered instead."""
    question = raw["ask"]["question"].strip()
    if not question:
        return None
    if not [o for o in raw["ask"]["options"] if o.strip()]:
        could_mean = [asset for asset, _ in _targets(raw["targets"], assets)]
        return _which_asset(could_mean if len(could_mean) > 1 else assets, reply, question)
    return Route("ask", reply, ask={"question": question, "options": raw["ask"]["options"]})


def _targets(raw_targets: list[dict[str, Any]], assets: list[Asset]) -> list[tuple[Asset, str]]:
    """The assets named by real numbers, each once, with the field when it is one of the asset's own."""
    by_number = {number_of(a): a for a in assets}
    targets: list[tuple[Asset, str]] = []
    for target in raw_targets:
        asset = by_number.get(target["asset"])
        if asset is None or any(asset.id == a.id for a, _ in targets):
            continue
        name = target["field"].strip()
        targets.append((asset, name if name in writer.FIELDS[asset.type] else ""))
    return targets


def _targeted_route(raw: dict[str, Any], reply: str, targets: list[tuple[Asset, str]]) -> Route | None:
    """Remove and image work on whole assets; an edit also needs an instruction."""
    if not targets:
        return None
    whole = [(asset, "") for asset, _ in targets]
    instruction = raw["instruction"].strip()
    if raw["action"] == "remove":
        return Route("remove", reply, whole)
    if raw["action"] == "image":
        return Route("image", reply, whole, instruction)
    return Route("edit", reply, targets, instruction, raw["research_query"].strip()) if instruction else None


def _which_asset(assets: list[Asset], reply: str, question: str = "Which asset should I change?") -> Route:
    """No usable target. A choice between assets only makes sense when there are two or more."""
    if len(assets) > 1:
        options = [f"{number_of(a)}. {writer.TYPE_LABELS[a.type]} “{a.title}”" for a in assets]
        return Route("ask", reply, ask={"question": question, "every_asset": True, "options": options})
    named = f" in “{assets[0].title}”" if assets else ""
    return Route("answer", f"I couldn't tell what to do. Say what to change{named}, or ask for new assets, "
                 "for example “add two more X posts”.")
