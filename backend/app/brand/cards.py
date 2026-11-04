"""Step 2 of reading a brand: a short card per document, written by the small model.

Every claim on a card must quote the sentence that proves it. The quotes are then checked
against the document. A field whose quote can't be found goes back to "unknown".
"""

import json
import re
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.brand.evidence import Document

CARD_VERSION = 2
"""Raise this when the prompt or schema changes, so existing cards are written again."""

KINDS = ["rule", "reference", "example", "template", "persona", "case_study", "press", "internal_note", "index", "other"]
STATUSES = ["current", "replaced", "draft", "archived", "unknown"]

INSTRUCTIONS = f"""\
You write a short card describing one document from a company's brand folder. A later step \
compares all the cards, so record what this document says. Don't judge it against other documents.

Fields:
- summary: two or three plain sentences on what the document covers and who it is for.
- kind: rule (guidelines, policies, playbooks the writer must follow), reference (product facts, \
pricing, claims), example (past published content), template, persona, case_study, press, \
internal_note (meeting notes, chat exports, sales notes), index (a start-here or folder guide), other.
- claimed_status: what the document says about its own status: current, replaced, draft or archived. \
It is a draft only when it says it is still a draft, unapproved or not final. A line saying it was first \
drafted and later updated or published is not a draft. Use unknown when it says nothing.
- date: the latest date the document gives for itself (written, updated, effective, checked). \
as_written is the text as it appears; iso is YYYY-MM-DD, using the first day of the month or \
year when the day is missing; empty when unknown.
- owner: the person or team responsible for the document, and their role if stated.
- safe_to_quote: "no" when the document says it is internal, confidential, or not for customers; \
"yes" when it says it is approved for external use or was published externally; otherwise "unknown".
- rules_on: topics this document sets rules or facts for (for example "pricing", "certifications", \
"email", "logo use"). Empty for examples and notes.
- replaces: other documents this one says it replaces or supersedes.
- claims_about_other_documents: anything it says about another document's status or authority, such \
as "X is the current version", "if a deck says otherwise, the deck is out of date".
- mentions: products, channels, customers and people named in the document.

Evidence rules:
- Every `evidence` is one exact sentence or line copied from the document, word for word.
- If no sentence supports a value, use unknown or an empty value and empty evidence. Never guess.
- The file path and the hints are context only. They are not evidence.
"""


SCHEMA = OutputSchema(
    name="document_card",
    schema=strict_object(
        {
            "summary": TEXT,
            "kind": enum(*KINDS),
            "claimed_status": strict_object({"value": enum(*STATUSES), "evidence": TEXT}),
            "date": strict_object({"as_written": TEXT, "iso": TEXT, "evidence": TEXT}),
            "owner": strict_object({"name": TEXT, "role": TEXT, "evidence": TEXT}),
            "safe_to_quote": strict_object({"value": enum("yes", "no", "unknown"), "evidence": TEXT}),
            "rules_on": TEXT_LIST,
            "replaces": array_of(strict_object({"document": TEXT, "evidence": TEXT})),
            "claims_about_other_documents": array_of(strict_object({"document": TEXT, "claim": TEXT, "evidence": TEXT})),
            "mentions": strict_object({"products": TEXT_LIST, "channels": TEXT_LIST, "customers": TEXT_LIST, "people": TEXT_LIST}),
        }
    ),
)


def prompt_for(path: str, basics: dict[str, Any], text: str) -> Prompt:
    hints = {key: basics[key] for key in ("frontmatter", "top_labels", "name_hints") if basics.get(key)}
    task = f"File path: {path}\nHints found without AI: {json.dumps(hints, ensure_ascii=False)}\n\n--- DOCUMENT ---\n{text}"
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=task)])


def checked_card(raw_reply: str, document: str) -> dict[str, Any]:
    """Parses the model's card and removes every claim whose quote isn't in the document.

    Removed claims are kept under `unverified`, so the Brand page can show what was dropped. A quote that is
    only the claimed value, or a single word, isn't proof (see `Document.proves`).
    """
    card: dict[str, Any] = json.loads(raw_reply)
    source = Document(document)
    unverified: list[dict[str, str]] = []

    def found(evidence: str, value: str = "") -> bool:
        return source.proves(evidence, value)

    def drop(field: str, value: str, evidence: str) -> None:
        unverified.append({"field": field, "value": value, "evidence": evidence})

    status = card["claimed_status"]
    if status["value"] != "unknown" and not found(status["evidence"], status["value"]):
        drop("claimed_status", status["value"], status["evidence"])
        card["claimed_status"] = {"value": "unknown", "evidence": ""}

    date = card["date"]
    if (date["as_written"] or date["iso"]) and not found(date["evidence"]):
        drop("date", date["as_written"], date["evidence"])
        card["date"] = {"as_written": "", "iso": "", "evidence": ""}
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date["iso"]):
        date["iso"] = ""

    owner = card["owner"]
    if owner["name"] and not found(owner["evidence"], owner["name"]):
        drop("owner", owner["name"], owner["evidence"])
        card["owner"] = {"name": "", "role": "", "evidence": ""}

    safe = card["safe_to_quote"]
    if safe["value"] != "unknown" and not found(safe["evidence"]):
        drop("safe_to_quote", safe["value"], safe["evidence"])
        card["safe_to_quote"] = {"value": "unknown", "evidence": ""}

    for field, label in (("replaces", "document"), ("claims_about_other_documents", "claim")):
        kept = []
        for item in card[field]:
            if found(item["evidence"]):
                kept.append(item)
            else:
                drop(field, item[label], item["evidence"])
        card[field] = kept

    card["unverified"] = unverified
    return card
