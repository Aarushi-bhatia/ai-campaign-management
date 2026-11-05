"""Matches what documents say about other documents to the actual files.

Cards record claims like "this replaces the 2024 guidelines" or "X is the current version" in free text.
This step finds which file each claim is about, and what it means for that file.
"""

import json
from dataclasses import dataclass

from app.ai.prompt import OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.brand.models import BrandFile

LINKS_VERSION = 1
EFFECTS = ("replaces", "outdated", "current", "higher_authority", "lower_authority", "other")

INSTRUCTIONS = """\
You match statements that brand documents make about other documents to the files they mean.

You get the list of files in the brand folder, then numbered statements. For each statement give:
- target_id: the id of the file the statement is about, or 0 when it is about something not in the \
list (a deck, a website, a person) or when you can't tell which file it means.
- effect, for that file:
  - replaces: the speaking document says it replaces or supersedes this file.
  - outdated: the statement says this file is old, out of date, wrong, or not to be used.
  - current: the statement says this file is the current one, the one to follow.
  - higher_authority: the statement says this file outranks other documents.
  - lower_authority: the statement says this file ranks below other documents.
  - other: anything else.

Match by meaning: "the 2024 guidelines" can be a file named Brand_Guidelines_v3 if its date or summary \
fits. Never pick the speaking document itself."""

SCHEMA = OutputSchema(
    name="document_links",
    schema=strict_object(
        {
            "links": array_of(
                strict_object({"statement": {"type": "integer"}, "target_id": {"type": "integer"}, "effect": enum(*EFFECTS)})
            )
        }
    ),
)


@dataclass(frozen=True)
class Statement:
    source_id: int
    about: str
    claim: str
    evidence: str


@dataclass(frozen=True)
class LinkDraft:
    source_id: int
    target_id: int
    effect: str
    claim: str
    evidence: str


def statements(documents: list[BrandFile]) -> list[Statement]:
    found: list[Statement] = []
    for document in documents:
        card = document.card or {}
        for item in card.get("replaces", []):
            found.append(Statement(document.id, item["document"], "This document replaces it.", item["evidence"]))
        for item in card.get("claims_about_other_documents", []):
            found.append(Statement(document.id, item["document"], item["claim"], item["evidence"]))
    return found


def prompt_for(documents: list[BrandFile], found: list[Statement]) -> Prompt:
    paths = {document.id: document.path for document in documents}
    files = "\n".join(
        f"[{d.id}] {d.path} | date {(d.card or {}).get('date', {}).get('iso') or 'unknown'} | "
        f"{(d.card or {}).get('summary', '')[:160]}"
        for d in documents
    )
    numbered = "\n".join(
        f'[{n}] Said by [{s.source_id}] {paths[s.source_id]}, about "{s.about}": {s.claim} (quote: "{s.evidence}")'
        for n, s in enumerate(found, start=1)
    )
    task = f"Files:\n{files}\n\nStatements:\n{numbered}"
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=task)])


def checked_links(raw_reply: str, documents: list[BrandFile], found: list[Statement]) -> list[LinkDraft]:
    """Keeps links that point at a real file other than the speaker, with a meaningful effect."""
    ids = {document.id for document in documents}
    links: list[LinkDraft] = []
    for item in json.loads(raw_reply)["links"]:
        index = item["statement"] - 1
        if not 0 <= index < len(found) or item["effect"] == "other":
            continue
        statement = found[index]
        if item["target_id"] in ids and item["target_id"] != statement.source_id:
            links.append(
                LinkDraft(statement.source_id, item["target_id"], item["effect"], statement.claim, statement.evidence)
            )
    return links
