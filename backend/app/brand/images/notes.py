"""AI steps for images: describing images that have no description, and turning free-text
restriction notes into clear fields the picker can enforce without AI.
"""

import json
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, Image, OutputSchema, Prompt, Turn, array_of, enum, strict_object

NOTES_VERSION = 2
DESCRIBE_VERSION = 2
SHORT_DESCRIPTION_WORDS = 6
"""A description shorter than this is too thin to choose by, so the vision model looks at the image too."""
NOTES_BATCH = 25

IMAGE_TYPES = ("photography", "illustration", "product_screenshot", "logo", "icon", "abstract_graphic",
               "social_template", "chart", "other")
CHANNELS = ("email", "linkedin", "x", "blog", "landing_page", "events", "paid_ads", "press", "print")
ASSET_CHANNELS = ("email", "linkedin", "x", "blog", "landing_page")
"""The channels campaign assets are written for."""

DESCRIBE_INSTRUCTIONS = f"""\
You describe one image from a company's brand library, for a writer choosing images.

- description: one or two plain sentences on what it shows: subject, setting, colors, mood, and any \
people or text visible. Don't guess names, places or brands you can't read.
- image_type: one of {", ".join(IMAGE_TYPES)}.
- has_people: whether a person is recognisable.
- has_text: whether readable text is part of the image."""

DESCRIBE_SCHEMA = OutputSchema(
    name="image_description",
    schema=strict_object(
        {"description": TEXT, "image_type": enum(*IMAGE_TYPES), "has_people": {"type": "boolean"},
         "has_text": {"type": "boolean"}}
    ),
)

NOTES_INSTRUCTIONS = f"""\
You turn each image's rights and restriction notes into clear fields. Today's date is given with the images.

For each image give:
- usable: false when anything rules it out for new public content: retired or deprecated, internal \
only, a person who has left the company or not consented, a past one-off event, an expired licence.
- retired: the image or what it shows (such as an old logo) is retired or deprecated.
- expired: it was tied to a date or event that has passed, or its licence has ended.
- no_crop: it must not be cropped, or a part of it must stay visible.
- allowed_channels: when the notes limit it to some channels, those channels; otherwise empty. \
Channels: {", ".join(CHANNELS)}.
- blocked_channels: channels the notes rule out.
- rules: other conditions in plain words, such as "keep the early access label visible" or \
"prefer a diagram where one will do". Empty when none.
- reason: one short line on why it is not usable, or "" when it is.

Also mark an image not usable when it breaks one of the brand's image rules listed, such as a banned \
motif or a retired logo, judged from its description; give the rule in reason.

Only use what the notes, the description and the rules say. A note that a release or consent is on file \
is a good sign, not a limit."""

NOTES_SCHEMA = OutputSchema(
    name="image_notes",
    schema=strict_object(
        {
            "images": array_of(
                strict_object(
                    {
                        "id": {"type": "integer"},
                        "usable": {"type": "boolean"},
                        "retired": {"type": "boolean"},
                        "expired": {"type": "boolean"},
                        "no_crop": {"type": "boolean"},
                        "allowed_channels": array_of(enum(*CHANNELS)),
                        "blocked_channels": array_of(enum(*CHANNELS)),
                        "rules": TEXT_LIST,
                        "reason": TEXT,
                    }
                )
            )
        }
    ),
)


def describe_prompt(path: str, title: str, note: str, data_url: str) -> Prompt:
    text = f"File: {path}" + (f"\nTitle: {title}" if title else "") + (f"\nLibrary note: {note}" if note else "")
    return Prompt(fixed=DESCRIBE_INSTRUCTIONS, task=[Turn(role="user", content=text, images=(Image(data_url, path),))])


def notes_prompt(today: str, brand_rules: list[str], images: list[dict[str, Any]]) -> Prompt:
    """`images` holds, per image, an id and everything known about it (file name, record, description).

    The brand's image rules are the same for every batch, so they sit in the reused middle part of the prompt.
    """
    rules = "The brand's image rules:\n" + ("\n".join(brand_rules) or "(none)")
    lines = "\n".join(json.dumps(image, ensure_ascii=False) for image in images)
    return Prompt(
        fixed=NOTES_INSTRUCTIONS, campaign=rules, task=[Turn(role="user", content=f"Today is {today}.\n\n{lines}")],
        cache=("fixed", "campaign"),
    )


def checked_notes(raw_reply: str, ids: set[int]) -> dict[int, dict[str, Any]]:
    """Notes for the images that were asked about. An unusable image always has a reason."""
    notes: dict[int, dict[str, Any]] = {}
    for item in json.loads(raw_reply)["images"]:
        image_id = item.pop("id")
        if image_id not in ids:
            continue
        if not item["usable"] and not item["reason"].strip():
            item["reason"] = "Its notes rule it out."
        notes[image_id] = item
    return notes
