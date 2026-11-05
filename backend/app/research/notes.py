"""Turns web pages into a few short findings, each tied to its source and an exact sentence from it.

A finding whose sentence isn't on the page is dropped, so a source can't be made up. A finding about the brand
or its products is dropped too, in code and not only by instruction: on those, the brand's documents rule.
Dates come only from the page itself; the model is never asked for one, so a date shown is one the page gave.
"""

import json
import re
from dataclasses import dataclass

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, strict_object
from app.ai.service import AiService
from app.brand.rules.evidence import Document
from app.config import ModelSize
from app.research.client import WebPage, WebResearch

RESULTS = 4
PAGE_CHARS = 6000
MAX_FINDINGS = 3
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")

INSTRUCTIONS = """\
You take notes from web pages for a marketing campaign. Keep only facts that would make the copy \
stronger: figures, trends, recent events, named studies.

- Each finding is one plain sentence, with any number exactly as the page gives it.
- quote is the exact sentence from the page that proves it, copied character for character.
- page is the number of the page it came from.
- Leave out anything about the brand named below or its products, prices or rules: the brand's own \
documents rule on those, never the web.
- Leave out opinions, adverts and anything you can't tie to a sentence.
- At most three findings, best first. None is fine when the pages have nothing solid."""

NOTES_SCHEMA = OutputSchema(
    name="research_notes",
    schema=strict_object({
        "findings": array_of(strict_object({"finding": TEXT, "quote": TEXT, "page": {"type": "integer"}}))
    }),
)


@dataclass(frozen=True)
class Finding:
    finding: str
    quote: str
    url: str
    title: str
    date: str


def research(
    ai: AiService, web: WebResearch, query: str, brand_name: str, *, chat_id: int | None, brand_id: int | None,
    skip_urls: frozenset[str] = frozenset(), off_limits: tuple[str, ...] = (),
) -> list[Finding]:
    found = web.search(query, RESULTS + len(skip_urls))
    pages = [WebPage(p.url, p.title, _plain(p.text), p.date) for p in found if p.url not in skip_urls and p.text.strip()]
    pages = pages[:RESULTS]
    if not pages:
        return []
    listing = "\n\n".join(
        f"=== PAGE {i} ===\nURL: {p.url}\nTitle: {p.title}\nDate: {p.date or 'not given'}\n\n{p.text[:PAGE_CHARS]}"
        for i, p in enumerate(pages, start=1)
    )
    reply = ai.complete(
        step=f"Research notes: {query}"[:200],
        size=ModelSize.SMALL,
        prompt=Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=f"Brand: {brand_name}\nSearch: {query}\n\n{listing}")]),
        output_schema=NOTES_SCHEMA,
        chat_id=chat_id,
        brand_id=brand_id,
    )
    findings = []
    for item in json.loads(reply.text)["findings"]:
        if not 1 <= item["page"] <= len(pages):
            continue
        page = pages[item["page"] - 1]
        if not item["finding"].strip() or not Document(page.text).contains(item["quote"]):
            continue
        if _mentions(f"{item['finding']} {item['quote']}", (brand_name, *off_limits)):
            continue
        findings.append(Finding(item["finding"].strip(), item["quote"].strip(), page.url, page.title, page.date))
    return findings[:MAX_FINDINGS]


def _mentions(text: str, names: tuple[str, ...]) -> bool:
    """True when the text names the brand or one of its products, as a whole word: written as the brand writes
    it ("Acme") or in capitals ("ACME"). Matching the capitals keeps a brand named after an everyday word
    ("Square", "Notion") from dropping findings that only use the word ("the square footage").

    What this misses: the name in lower case ("acme") or other spellings. Those are left to the notes
    step's instruction to leave the brand out. A sentence that starts with an everyday-word brand name
    ("Square footage...") is still dropped."""
    forms = {form for name in names if name.strip() for form in (name.strip(), name.strip().upper())}
    return any(re.search(rf"(?<!\w){re.escape(form)}(?!\w)", text) for form in forms)


def _plain(markdown: str) -> str:
    """Page text without link targets and images, so quotes can be matched to it."""
    return _LINK.sub(r"\1", markdown)
