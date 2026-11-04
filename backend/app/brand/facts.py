"""Step 3 of reading a brand: single facts and rules from the documents that set them.

Internal notes are included on purpose. They are never quoted, but their facts are what the
conflict step checks against the documents in charge.
"""

import json
from dataclasses import dataclass

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.brand.evidence import Document

FACT_VERSION = 1
DOC_TYPES_WITH_FACTS = {"rule", "reference", "case_study", "press", "internal_note"}
"""Only these documents' facts count. A document whose type changes away keeps its facts, unused, so changing
it back brings them back at once, without reading it again."""


def counts(doc_type: str | None) -> bool:
    return doc_type in DOC_TYPES_WITH_FACTS
MAX_FACTS = 100
KINDS = ("must", "must_not", "may", "fact")

INSTRUCTIONS = f"""\
You pull single facts and rules out of one brand document, for a copywriter who must respect them.

Each fact has:
- subject: the one thing it is about. Use a name from the names list when one fits, spelled as listed. \
For rules about writing itself use a short plain subject such as "headlines", "numbers" or "email subject lines".
- attribute: a short lower-case label for what is said about the subject, such as "status", \
"approved wording", "price", "banned term", "first mention".
- value: what the document says, in a few words.
- kind: must (the writer has to), must_not (the writer may not), may (allowed), or fact (a statement of fact).
- scope: the channel, audience or product it is limited to, or "" when it applies everywhere.
- evidence: one exact sentence or line copied from the document, word for word.

One point per fact. Keep figures, dates, names and approved wordings exact. Skip examples, stories and \
advice that doesn't bind the writer. At most {MAX_FACTS} facts, the ones that matter most."""

SCHEMA = OutputSchema(
    name="facts",
    schema=strict_object(
        {
            "facts": array_of(
                strict_object(
                    {"subject": TEXT, "attribute": TEXT, "value": TEXT, "kind": enum(*KINDS), "scope": TEXT, "evidence": TEXT}
                )
            )
        }
    ),
)


@dataclass(frozen=True)
class FactDraft:
    subject: str
    attribute: str
    value: str
    kind: str
    scope: str
    evidence: str


def prompt_for(path: str, names: str, text: str) -> Prompt:
    task = f"Names list:\n{names or '(none)'}\n\nFile path: {path}\n\n--- DOCUMENT ---\n{text}"
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=task)])


def checked_facts(raw_reply: str, text: str) -> tuple[list[FactDraft], int]:
    """The facts whose quote is in the document, and how many were dropped because it wasn't."""
    source = Document(text)
    kept: list[FactDraft] = []
    dropped = 0
    for item in json.loads(raw_reply)["facts"][:MAX_FACTS]:
        if not item["subject"].strip() or not source.contains(item["evidence"]):
            dropped += 1
            continue
        kept.append(FactDraft(**{key: item[key].strip() for key in FactDraft.__dataclass_fields__}))
    return kept, dropped
