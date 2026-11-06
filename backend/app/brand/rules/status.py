"""Decides each document's final status from what all the documents say. Plain rules, no AI.

The order, highest first:
1. The user's correction.
2. Another document says it replaces this one, or that this one is out of date. A document that says
   it replaces another beats a label calling the old one current. When two documents each claim to
   replace the other, the newer one wins; with no dates to go on, it is left for a person to decide.
3. What the document says about itself: draft, archived or replaced.
4. Its file name or folder marks it as old (archive, old, deprecated).
5. Otherwise it is current.
"""

from dataclasses import dataclass

STALE_HINTS = ("archive", "old", "deprecated")


@dataclass(frozen=True)
class DocView:
    id: int
    path: str
    claimed: str
    """What the document says about itself: current, replaced, draft, archived or unknown."""
    claimed_evidence: str
    date: str
    """YYYY-MM-DD, or empty when unknown."""
    name_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkView:
    source_id: int
    target_id: int
    effect: str
    evidence: str


@dataclass(frozen=True)
class StatusResult:
    status: str
    """current, replaced, draft, archived or unclear."""
    reason: str
    replaced_by: int | None = None


def decide_statuses(
    docs: list[DocView], links: list[LinkView], corrections: dict[int, str]
) -> dict[int, StatusResult]:
    by_id = {doc.id: doc for doc in docs}
    return {doc.id: _decide(doc, by_id, links, corrections) for doc in docs}


def _decide(doc: DocView, by_id: dict[int, DocView], links: list[LinkView],
            corrections: dict[int, str]) -> StatusResult:
    """The first rule that settles it, in the order the module docstring gives."""
    if doc.id in corrections:
        return StatusResult(corrections[doc.id], "You set this on the Brand page.")
    incoming = [link for link in links if link.target_id == doc.id and link.source_id in by_id]
    called_current = [link for link in incoming if link.effect == "current"]
    return (_by_other_documents(doc, by_id, links, incoming, called_current)
            or _by_itself(doc)
            or _by_name(doc)
            or _current(doc, by_id, called_current))


def _by_other_documents(doc: DocView, by_id: dict[int, DocView], links: list[LinkView], incoming: list[LinkView],
                        called_current: list[LinkView]) -> StatusResult | None:
    """Rule 2: another document replaces this one or says it is out of date. None when none does."""
    against = []
    for link in incoming:
        if link.effect not in ("replaces", "outdated"):
            continue
        rival = by_id[link.source_id]
        if _says_it_replaces(links, doc, rival):
            if not (doc.date and rival.date) or doc.date == rival.date:
                return StatusResult(
                    "unclear",
                    f"This and {rival.path} each say they replace the other, and their dates don't settle it.",
                )
            if doc.date > rival.date:
                continue
        against.append(link)
    return _replaced(against, by_id, called_current) if against else None


def _says_it_replaces(links: list[LinkView], doc: DocView, rival: DocView) -> bool:
    return any(link.source_id == doc.id and link.target_id == rival.id and link.effect == "replaces"
               for link in links)


def _replaced(against: list[LinkView], by_id: dict[int, DocView], called_current: list[LinkView]) -> StatusResult:
    """Replaced, by the strongest claim: one that says it replaces beats "out of date", then the newest."""
    strongest = max(against, key=lambda link: (link.effect == "replaces", by_id[link.source_id].date))
    source = by_id[strongest.source_id]
    verb = "says it replaces this" if strongest.effect == "replaces" else "says this is out of date"
    reason = f'{source.path} {verb}: "{strongest.evidence}"'
    if called_current:
        labels = ", ".join(sorted({by_id[link.source_id].path for link in called_current}))
        reason += f" {labels} calls it current, but a document that replaces another beats a label."
    return StatusResult("replaced", reason, replaced_by=source.id)


def _by_itself(doc: DocView) -> StatusResult | None:
    """Rule 3: what the document says about itself."""
    if doc.claimed in ("draft", "archived", "replaced"):
        return StatusResult(doc.claimed, f'It says so itself: "{doc.claimed_evidence}"')
    return None


def _by_name(doc: DocView) -> StatusResult | None:
    """Rule 4: its file name or folder marks it as old."""
    stale = [hint for hint in doc.name_hints if hint in STALE_HINTS]
    if stale:
        return StatusResult("archived", f"Its file name or folder marks it as old ({', '.join(stale)}).")
    return None


def _current(doc: DocView, by_id: dict[int, DocView], called_current: list[LinkView]) -> StatusResult:
    """Rule 5: current, with the best reason there is."""
    if doc.claimed == "current":
        return StatusResult("current", f'It says it is current: "{doc.claimed_evidence}"')
    if called_current:
        return StatusResult("current", f"{by_id[called_current[0].source_id].path} calls it current.")
    return StatusResult("current", "Nothing marks it as old, replaced or a draft.")
