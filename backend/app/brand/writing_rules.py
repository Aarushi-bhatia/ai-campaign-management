"""Rules a plain text search can check in finished copy: banned words, retired names, length and hashtag limits.

They come from the brand summary and the brand's length and hashtag rules, once per brand, and are saved until those
change. Retired names also come straight from the names table, with no AI.
"""

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.ai.service import AiService
from app.brand.evidence import Document
from app.brand.models import Brand, Entity
from app.brand.settle import usable_facts
from app.config import ModelSize

RULES_VERSION = 2
CHANNELS = ("email", "linkedin", "x", "blog", "landing_page")
FIELDS = ("subject", "preview_text", "text", "title", "headline", "body", "button_text")
MAX_FACTS = 120
_ABOUT_LENGTH = re.compile(r"\b(characters?|chars|words|length|limit|maximum|max|under \d+|at most \d+|hashtags?)\b",
                           re.IGNORECASE)

INSTRUCTIONS = """\
You turn a brand's writing rules into a list a simple text search can check in finished marketing copy.

- banned: words and phrases that must never appear in public copy, as they would be written. Give each \
variant as its own entry (for example "best-in-class" and "best in class"). Include what to use instead, \
or "". Leave out words that are allowed in some senses or places; a text search can't tell senses apart.
- old_names: retired or replaced names, with the current name to use.
- limits: a maximum length for one field on one channel, only where a rule gives a number.
- hashtags: the most hashtags one post on a channel may have, only where a rule says: 0 when the rule \
forbids hashtags there, otherwise the number it allows (for example "0–2 hashtags" is 2). A rule that only \
says where hashtags go, or what they must not contain, gives no number.
- quote: the exact sentence or table row the rule comes from.

Only use the rules given. Never add general writing advice."""

SCHEMA = OutputSchema(
    name="writing_rules",
    schema=strict_object({
        "banned": array_of(strict_object({"term": TEXT, "instead": TEXT, "quote": TEXT})),
        "old_names": array_of(strict_object({"old": TEXT, "new": TEXT, "quote": TEXT})),
        "limits": array_of(strict_object({
            "channel": enum(*CHANNELS), "field": enum(*FIELDS), "max": {"type": "integer"},
            "unit": enum("characters", "words"), "quote": TEXT,
        })),
        "hashtags": array_of(strict_object({"channel": enum(*CHANNELS), "max": {"type": "integer"}, "quote": TEXT})),
    }),
)


def empty_rules() -> dict[str, Any]:
    return {"banned": [], "old_names": [], "limits": [], "hashtags": []}


def ensure(session: Session, ai: AiService, brand: Brand) -> dict[str, Any]:
    """The brand's writing rules, worked out again only when the summary or length and hashtag rules changed."""
    length_rules = _length_rules(session, brand.id)
    source = f"{RULES_VERSION}\n{brand.summary or ''}\n" + "\n".join(length_rules)
    digest = hashlib.sha256(source.encode()).hexdigest()
    if brand.writing_rules is not None and brand.writing_rules_hash == digest:
        return with_names(session, brand)
    rules = empty_rules()
    if brand.summary or length_rules:
        text = (f"=== BRAND SUMMARY ===\n{brand.summary or '(none)'}\n\n=== LENGTH AND HASHTAG RULES ===\n"
                + ("\n".join(length_rules) or "(none)"))
        reply = ai.complete(
            step="Writing rules", size=ModelSize.MEDIUM, brand_id=brand.id, output_schema=SCHEMA,
            prompt=Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=text)]),
        )
        rules = checked(json.loads(reply.text), text)
        brand.writing_rules_call_id = reply.call_id
    brand.writing_rules, brand.writing_rules_hash = rules, digest
    session.commit()
    return with_names(session, brand)


def checked(raw: dict[str, Any], source: str) -> dict[str, Any]:
    """Keeps only rules whose quote is in the source, and drops empty or too-short terms."""
    doc = Document(source)
    banned = [{"term": r["term"].strip(), "instead": r["instead"].strip()} for r in raw["banned"]
              if len(r["term"].strip()) >= 3 and doc.contains(r["quote"])]
    old = [{"old": r["old"].strip(), "new": r["new"].strip()} for r in raw["old_names"]
           if len(r["old"].strip()) >= 3 and doc.contains(r["quote"])]
    limits = [{k: r[k] for k in ("channel", "field", "max", "unit")} for r in raw["limits"]
              if r["max"] > 0 and doc.contains(r["quote"])]
    hashtags = [{"channel": r["channel"], "max": r["max"]} for r in raw["hashtags"]
                if r["max"] >= 0 and doc.contains(r["quote"])]
    return {"banned": banned, "old_names": old, "limits": limits, "hashtags": hashtags}


def with_names(session: Session, brand: Brand) -> dict[str, Any]:
    """The saved rules plus every old name in the names table."""
    rules = brand.writing_rules or empty_rules()
    old = {r["old"].lower(): r for r in rules["old_names"]}
    for entity in session.scalars(select(Entity).where(Entity.brand_id == brand.id)):
        for old_name in entity.old_names:
            old.setdefault(old_name["name"].lower(), {"old": old_name["name"], "new": entity.name})
    return {"hashtags": [], **rules, "old_names": list(old.values())}


def _length_rules(session: Session, brand_id: int) -> list[str]:
    lines = []
    for fact, doc in usable_facts(session, brand_id):
        text = f"{fact.subject} | {fact.attribute}: {fact.value}"
        if fact.kind in ("must", "must_not", "may") and _ABOUT_LENGTH.search(f"{text} {fact.evidence}"):
            lines.append(f"{text} | {fact.scope or 'all'} | {doc.path} | {fact.evidence}")
    return lines[:MAX_FACTS]
