"""Per-channel image rules, taken from the brand's own documents.

Rules that can be checked on the file (see-through pixels, shape, image type, width) become fields the
picker enforces without AI. Everything else is kept as notes for the model that ranks images.
"""

import hashlib
import json
import re
from typing import Any

from app.ai.prompt import TEXT_LIST, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.brand.images.notes import ASSET_CHANNELS, IMAGE_TYPES

RULES_VERSION = 1
MAX_FACTS = 400

ABOUT_IMAGES = re.compile(
    r"\b(image|images|photo|photos|photograph\w*|picture|visual|visuals|illustration\w*|logo\w*|icon\w*|hero|"
    r"header image|thumbnail|banner|screenshot\w*|alt text|png|jpe?g|svg|transparent|crop\w*|graphic\w*)\b",
    re.IGNORECASE,
)

INSTRUCTIONS = f"""\
You turn a brand's rules about images into settings for each channel: {", ".join(ASSET_CHANNELS)}.

For each channel give:
- block_transparent: true when images with see-through backgrounds must not be used there.
- orientation: the shape required for the channel's main image: any, landscape, portrait or square.
- allowed_types: when the rules allow only some image types for the channel's main image, those types; \
otherwise empty. Types: {", ".join(IMAGE_TYPES)}.
- blocked_types: image types the rules rule out for the channel.
- min_width: the smallest source width in pixels the rules allow, or 0.
- image_optional: true when the rules say an image is often better left out.
- notes: the channel's other image rules, as short plain sentences, for the person choosing images.

Also give alt_text_rules and general_rules that apply to every channel.

Only use the rules given. A channel the rules say nothing about gets the defaults: false, any, empty, 0."""

SCHEMA = OutputSchema(
    name="channel_image_rules",
    schema=strict_object(
        {
            "channels": array_of(
                strict_object(
                    {
                        "channel": enum(*ASSET_CHANNELS),
                        "block_transparent": {"type": "boolean"},
                        "orientation": enum("any", "landscape", "portrait", "square"),
                        "allowed_types": array_of(enum(*IMAGE_TYPES)),
                        "blocked_types": array_of(enum(*IMAGE_TYPES)),
                        "min_width": {"type": "integer"},
                        "image_optional": {"type": "boolean"},
                        "notes": TEXT_LIST,
                    }
                )
            ),
            "alt_text_rules": TEXT_LIST,
            "general_rules": TEXT_LIST,
        }
    ),
)

DEFAULT_CHANNEL = {
    "block_transparent": False, "orientation": "any", "allowed_types": [], "blocked_types": [], "min_width": 0,
    "image_optional": False, "notes": [],
}


def image_fact_lines(facts: list[tuple[str, str, str, str, str]]) -> list[str]:
    """The facts about images, as lines for the prompt. Each fact is (subject, attribute, value, scope, path)."""
    lines = [
        f"- {subject} | {attribute}: {value}" + (f" (only for {scope})" if scope else "") + f" [{path}]"
        for subject, attribute, value, scope, path in facts
        if ABOUT_IMAGES.search(f"{subject} {attribute} {value} {scope}")
    ]
    return lines[:MAX_FACTS]


def source_hash(lines: list[str]) -> str:
    return hashlib.sha256(json.dumps([RULES_VERSION, lines]).encode()).hexdigest()


def prompt_for(lines: list[str]) -> Prompt:
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content="Image rules:\n" + "\n".join(lines))])


def checked_rules(raw_reply: str) -> dict[str, Any]:
    """Every campaign channel gets settings, using the defaults where the rules say nothing."""
    reply = json.loads(raw_reply)
    channels = {channel: dict(DEFAULT_CHANNEL) for channel in ASSET_CHANNELS}
    for item in reply["channels"]:
        channel = item.pop("channel")
        channels[channel] = {**DEFAULT_CHANNEL, **item, "min_width": max(0, item["min_width"])}
    return {"channels": channels, "alt_text_rules": reply["alt_text_rules"], "general_rules": reply["general_rules"]}


def empty_rules() -> dict[str, Any]:
    return {"channels": {c: dict(DEFAULT_CHANNEL) for c in ASSET_CHANNELS}, "alt_text_rules": [], "general_rules": []}
