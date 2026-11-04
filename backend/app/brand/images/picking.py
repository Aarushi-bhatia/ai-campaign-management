"""Picking images for an asset: block first with plain rules, then let the model rank what is left.

Blocking only uses fixed fields (the user's correction, the restriction fields, the channel's rules and
the file's own size and see-through pixels), so a banned image can never be ranked.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, strict_object

MAX_CHOICES = 3
SQUARE_TOLERANCE = 0.05

RANK_INSTRUCTIONS = """\
You choose images from a brand's library for one asset. Every image listed is already cleared for this \
channel; choose by fit.

Pick up to three images, best first, that suit the asset's message and audience and follow the \
channel's image notes and the campaign's own image rules. For each give:
- image_id
- why: one short line.
- alt_text: written to the brand's alt text rules; describe what the image shows, not what it means.

When the brand's rules say this kind of asset should have no image, return no choices, set \
nothing_fits, and say so in suggestion, citing the rule. When an image is wanted but nothing listed fits \
well, return no choices, set nothing_fits, and in suggestion describe the image that would fit, in one \
line, so someone can make or find it. A weak match is worse than none."""

RANK_SCHEMA = OutputSchema(
    name="image_choice",
    schema=strict_object(
        {
            "choices": array_of(strict_object({"image_id": {"type": "integer"}, "why": TEXT, "alt_text": TEXT})),
            "nothing_fits": {"type": "boolean"},
            "suggestion": TEXT,
        }
    ),
)


@dataclass(frozen=True)
class ImageView:
    id: int
    path: str
    title: str
    description: str
    image_type: str
    tags: tuple[str, ...]
    width: int
    height: int
    transparent: bool
    notes: dict[str, Any] | None
    usable_override: str | None = None
    """The user's correction: "yes" or "no", or None."""


@dataclass(frozen=True)
class Blocked:
    path: str
    reason: str


@dataclass(frozen=True)
class AssetSpec:
    channel: str
    asset_type: str
    message: str
    slot: str = "main"
    """main (the asset's lead image, where the channel's rules apply) or inline."""
    campaign_rules: str = ""
    exclude_paths: frozenset[str] = frozenset()
    used_paths: frozenset[str] = frozenset()
    """Images other assets of the campaign already use. Not blocked: the ranking prefers others when they fit as well."""
    recent_paths: frozenset[str] = frozenset()
    """Images the brand's recent campaigns used, treated the same way, so campaigns don't repeat each other."""
    memory: tuple[str, ...] = ()
    """What the marketer told the agent before (core memory), which can include image preferences."""


def blocked_reason(image: ImageView, spec: AssetSpec, rules: dict[str, Any]) -> str | None:
    """Why the image can't be used for this asset, or None when it can."""
    if image.usable_override == "no":
        return "You marked it not usable."
    if image.path in spec.exclude_paths:
        return "Left out by the campaign."
    # "Usable: yes" overrules the notes' verdict on the image (usable, retired, expired), not the channels the
    # notes limit it to, nor the channel's own rules below.
    reason = _channel_limit(image, spec.channel) if image.usable_override == "yes" else \
        _restriction_reason(image, spec.channel)
    if reason:
        return reason
    if spec.slot != "main":
        return None
    return _channel_reason(image, spec.channel, rules.get(spec.channel, {}))


def split(images: list[ImageView], spec: AssetSpec, rules: dict[str, Any]) -> tuple[list[ImageView], list[Blocked]]:
    usable: list[ImageView] = []
    blocked: list[Blocked] = []
    for image in images:
        reason = blocked_reason(image, spec, rules)
        if reason:
            blocked.append(Blocked(image.path, reason))
        else:
            usable.append(image)
    return usable, blocked


def _restriction_reason(image: ImageView, channel: str) -> str | None:
    notes = image.notes
    if notes is None:
        return "Its rights and restrictions haven't been checked yet (or couldn't be): use Read again."
    if not notes["usable"]:
        return notes["reason"]
    if notes["retired"]:
        return "It is retired."
    if notes["expired"]:
        return "It has expired."
    return _channel_limit(image, channel)


def _channel_limit(image: ImageView, channel: str) -> str | None:
    """The channels the image's own notes limit it to or rule out."""
    notes = image.notes
    if notes is None:
        return None
    if notes["allowed_channels"] and channel not in notes["allowed_channels"]:
        return f"Only for {', '.join(notes['allowed_channels'])}."
    if channel in notes["blocked_channels"]:
        return f"Not for {channel}."
    return None


def _channel_reason(image: ImageView, channel: str, rule: dict[str, Any]) -> str | None:
    if rule.get("block_transparent") and image.transparent:
        return f"See-through images aren't used in {channel}."
    shape = _shape(image)
    wanted = rule.get("orientation", "any")
    if wanted != "any" and shape and shape != wanted:
        return f"{channel} needs a {wanted} image; this one is {shape}."
    if rule.get("allowed_types") and image.image_type not in rule["allowed_types"]:
        return f"{channel} uses only {', '.join(rule['allowed_types'])} here."
    if image.image_type in rule.get("blocked_types", []):
        return f"{image.image_type} images aren't used in {channel}."
    if rule.get("min_width") and image.width and image.width < rule["min_width"]:
        return f"Narrower than the {rule['min_width']}px {channel} needs."
    return None


def _shape(image: ImageView) -> str | None:
    if not image.width or not image.height:
        return None
    if abs(image.width - image.height) <= SQUARE_TOLERANCE * max(image.width, image.height):
        return "square"
    return "landscape" if image.width > image.height else "portrait"


@dataclass
class Choice:
    path: str
    why: str
    alt_text: str


@dataclass
class PickResult:
    choices: list[Choice] = field(default_factory=list)
    suggestion: str = ""
    blocked: list[Blocked] = field(default_factory=list)
    call_id: int | None = None


def library_text(candidates: list[ImageView]) -> str:
    """The cleared images, as the prompt lists them. Kept apart from the asset so it can be cached."""
    return "Cleared images:\n" + "\n".join(
        f"[{i.id}] {i.image_type} | {i.width}x{i.height} | {i.title or i.path} | {i.description} | "
        f"tags: {', '.join(i.tags) or 'none'}"
        + (f" | conditions: {'; '.join(i.notes['rules'])}" if i.notes and i.notes.get("rules") else "")
        + (" | must not be cropped" if i.notes and i.notes.get("no_crop") else "")
        for i in candidates
    )


def rank_prompt(spec: AssetSpec, candidates: list[ImageView], rules: dict[str, Any]) -> Prompt:
    channel_rule = rules["channels"].get(spec.channel, {})
    task = "\n".join(
        [
            f"Asset: {spec.asset_type} for {spec.channel}, {spec.slot} image.",
            f"Message: {spec.message}",
            f"Campaign image rules: {spec.campaign_rules or 'none'}",
            "Channel image notes: " + ("; ".join(channel_rule.get("notes", [])) or "none"),
            "General image rules: " + ("; ".join(rules.get("general_rules", [])) or "none"),
            "Alt text rules: " + ("; ".join(rules.get("alt_text_rules", [])) or "none"),
            "Already used by other assets of this campaign: " + (", ".join(sorted(spec.used_paths)) or "none")
            + ". Prefer a different image when one fits as well; reuse one only when the campaign's rules call for "
            "it or nothing else fits.",
            "Used by the brand's recent campaigns: " + (", ".join(sorted(spec.recent_paths)) or "none")
            + ". Prefer an image they didn't use, the same way.",
            "What the marketer told you before: " + ("; ".join(spec.memory) or "nothing")
            + ". Follow anything in it about images, unless the campaign's image rules say otherwise.",
        ]
    )
    return Prompt(fixed=RANK_INSTRUCTIONS, campaign=library_text(candidates), task=[Turn(role="user", content=task)],
                  cache=("fixed", "campaign"))


def checked_choice(raw_reply: str, candidates: list[ImageView]) -> tuple[list[Choice], str]:
    """Choices limited to cleared images, best first, and the suggestion when nothing fits."""
    reply = json.loads(raw_reply)
    by_id = {image.id: image for image in candidates}
    choices = [
        Choice(by_id[item["image_id"]].path, item["why"].strip(), item["alt_text"].strip())
        for item in reply["choices"]
        if item["image_id"] in by_id
    ][:MAX_CHOICES]
    suggestion = reply["suggestion"].strip() if not choices else ""
    return choices, suggestion or ("" if choices else "No cleared image fits this asset.")
