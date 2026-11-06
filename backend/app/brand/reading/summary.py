"""The brand summary: a few pages built from the winning facts, sent with every campaign request.

It is built by the large model because every asset is written on top of it.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from app.ai.prompt import Prompt, Turn

SUMMARY_VERSION = 1

INSTRUCTIONS = """\
You write the brand summary that a copywriter keeps open while writing anything for this company. \
It is built from facts already checked against the brand's documents. Use only those facts.

Write plain markdown, at most about 2,500 words, with these sections where the facts allow:
1. The company: the standard description. Quote the current approved boilerplate exactly if there is one.
2. Voice and tone: how the brand sounds, with the do's and don'ts.
3. Words: banned terms and preferred terms, with the replacement for each.
4. Names: every product and the company, the first-mention and later forms, and old names never to use.
5. Products: one or two lines each on what it does and doesn't do.
6. Claims: what may and may not be said, with approved wordings quoted exactly.
7. Proof: customers and figures cleared for use, with what each may be used for.

Keep every figure, date, name and approved wording exact. Write rules as short direct sentences. \
Leave out channel-specific rules (email, social, blog, landing page); those are looked up per asset."""


@dataclass(frozen=True)
class SummaryFact:
    subject: str
    attribute: str
    value: str
    kind: str
    scope: str
    doc_path: str


def source_text(brand_name: str, facts: list[SummaryFact]) -> str:
    """The facts, grouped by subject, as given to the model. Its hash tells when the summary is out of date."""
    by_subject: dict[str, list[SummaryFact]] = defaultdict(list)
    for fact in facts:
        by_subject[fact.subject].append(fact)
    blocks = []
    for subject in sorted(by_subject, key=lambda s: (-len(by_subject[s]), s.lower())):
        lines = [
            f"- [{f.kind}] {f.attribute}: {f.value}" + (f" (only for {f.scope})" if f.scope else "")
            + f" [{f.doc_path}]"
            for f in sorted(by_subject[subject], key=lambda f: (f.attribute, f.value))
        ]
        blocks.append(f"## {subject}\n" + "\n".join(lines))
    return f"Brand: {brand_name}\n\n" + "\n\n".join(blocks)


def source_hash(text: str) -> str:
    return hashlib.sha256(f"{SUMMARY_VERSION}\n{text}".encode()).hexdigest()


def prompt_for(text: str) -> Prompt:
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=text)])
