"""Finds facts from different documents that disagree, and picks the winner.

Finding a disagreement needs the model. Picking the winner is plain rules, highest first:
1. replaces: a document that replaces another (or calls it out of date) beats it, and a document that
   has been replaced loses to the live ones.
2. owner: the document in charge of the topic beats the others. Internal documents (internal notes, or
   anything marked not for public copy) are never in charge of what is said in public, so they lose to
   the others here even when named in charge.
3. approved: an approved document beats a draft.
4. newer: the newer document beats the older one.
5. live: a live document beats an archived or replaced one.
Documents on the same side of a disagreement don't compete: as soon as every document left is on one
side, that side wins. Anything still tied is left for a person to decide.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, strict_object

CONFLICT_VERSION = 2
MAX_FACTS_PER_CALL = 300

INSTRUCTIONS = """\
You check whether a brand's documents disagree about one subject.

You get the documents, then facts about the subject, each from one document. Find the points where \
documents disagree: the same attribute with different values (two prices, two statuses, two wordings), \
or a rule in one document that another breaks or forbids (one says say X, another says never say X).

These are not disagreements: the same thing said twice, more detail in one place, or facts about \
different things.

For each disagreement give:
- point: one plain line naming what they disagree on.
- topic: a short label for the area, such as "certifications", "pricing" or "product naming".
- sides: the positions taken. Each side has a short `position` and the `fact_ids` that take it. Facts \
that agree go on the same side, even from different documents. At least two sides.
- owner_doc_ids: the documents in charge of this topic, judged by what each document says it sets \
rules on and who owns it. Leave it empty when no document is clearly in charge.

Return an empty list when nothing disagrees."""

SCHEMA = OutputSchema(
    name="conflicts",
    schema=strict_object(
        {
            "conflicts": array_of(
                strict_object(
                    {
                        "point": TEXT,
                        "topic": TEXT,
                        "sides": array_of(strict_object({"position": TEXT, "fact_ids": array_of({"type": "integer"})})),
                        "owner_doc_ids": array_of({"type": "integer"}),
                    }
                )
            )
        }
    ),
)


@dataclass(frozen=True)
class FactView:
    id: int
    file_id: int
    attribute: str
    value: str
    kind: str
    scope: str


@dataclass(frozen=True)
class DocSheet:
    """What the model is told about each document in a group."""

    id: int
    path: str
    doc_type: str
    status: str
    owner: str
    rules_on: list[str]


@dataclass(frozen=True)
class Side:
    position: str
    fact_ids: list[int]


@dataclass(frozen=True)
class Found:
    point: str
    topic: str
    sides: list[Side]
    owner_file_ids: list[int]

    @property
    def fact_ids(self) -> list[int]:
        return sorted(fact_id for side in self.sides for fact_id in side.fact_ids)


def group_hash(subject_key: str, rows: list[tuple[str, str, str, str]]) -> str:
    """Identifies a subject's facts by content, so an unchanged group isn't sent to the model again.

    Each row is (file content hash, attribute, value, kind).
    """
    payload = json.dumps([CONFLICT_VERSION, subject_key, sorted(rows)], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def prompt_for(subject: str, docs: list[DocSheet], facts: list[FactView]) -> Prompt:
    doc_lines = "\n".join(
        f"[{d.id}] {d.path} | type {d.doc_type} | status {d.status} | owner {d.owner or 'unknown'} | "
        f"sets rules on: {', '.join(d.rules_on) or 'nothing stated'}"
        for d in docs
    )
    fact_lines = "\n".join(
        f"[{f.id}] doc {f.file_id} | {f.attribute}: {f.value} ({f.kind}{', ' + f.scope if f.scope else ''})"
        for f in facts[:MAX_FACTS_PER_CALL]
    )
    task = f"Subject: {subject}\n\nDocuments:\n{doc_lines}\n\nFacts:\n{fact_lines}"
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=task)])


def checked_conflicts(raw_reply: str, facts: list[FactView]) -> list[Found]:
    """Keeps disagreements with at least two sides, whose facts exist and come from two or more documents.

    A fact listed on more than one side stays on the first.
    """
    file_of = {fact.id: fact.file_id for fact in facts}
    found: list[Found] = []
    for item in json.loads(raw_reply)["conflicts"]:
        seen: set[int] = set()
        sides = []
        for side in item["sides"]:
            fact_ids = sorted({i for i in side["fact_ids"] if i in file_of and i not in seen})
            seen.update(fact_ids)
            if fact_ids:
                sides.append(Side(side["position"].strip(), fact_ids))
        files = {file_of[fact_id] for fact_id in seen}
        if len(sides) < 2 or len(files) < 2:
            continue
        owners = sorted({doc_id for doc_id in item["owner_doc_ids"] if doc_id in files})
        found.append(Found(item["point"].strip(), item["topic"].strip(), sides, owners))
    return found


@dataclass(frozen=True)
class Candidate:
    file_id: int
    path: str
    status: str
    date: str
    internal: bool = False
    """An internal note, or a document marked not for public copy."""


@dataclass(frozen=True)
class Verdict:
    winner_file_id: int | None
    rule: str
    reason: str


Rule = tuple[str, Callable[[], list[Candidate]], Callable[[Candidate, list[Candidate]], str]]
"""A rule's name, how it narrows the field, and how it explains a win."""


def pick_winner(
    candidates: list[Candidate],
    owner_ids: list[int],
    topic: str,
    replaces: set[tuple[int, int]],
    outranked: set[int],
    outranking: set[int],
    side_of: dict[int, int] | None = None,
) -> Verdict:
    """Applies the rules in order. Each rule narrows the field; the first to leave one side decides.

    `replaces` holds (newer, older) pairs: the first document replaces or outdates the second.
    `outranking` and `outranked` are documents that another document ranks above or below the rest.
    `side_of` says which side each document takes; without it, every document is its own side.
    """
    contest = _Contest(candidates, owner_ids, topic, replaces, outranked, outranking)
    side = side_of or {c.file_id: c.file_id for c in candidates}
    for rule, apply, explain in contest.rules():
        before = contest.remaining
        contest.remaining = apply()
        if len({side[c.file_id] for c in contest.remaining}) == 1:
            winner = contest.remaining[0]
            losers = [c for c in before if side[c.file_id] != side[winner.file_id]]
            return Verdict(winner.file_id, rule, explain(winner, losers))
    tied = ", ".join(c.path for c in contest.remaining)
    return Verdict(None, "needs_human", f"The rules can't choose between {tied}. Pick one on the Brand page.")


class _Contest:
    """The documents still in the running, and the rules that narrow them, in order."""

    def __init__(self, candidates: list[Candidate], owner_ids: list[int], topic: str,
                 replaces: set[tuple[int, int]], outranked: set[int], outranking: set[int]) -> None:
        self.remaining = list(candidates)
        self._owner_ids = owner_ids
        self._topic = topic
        self._replaces = replaces
        self._outranked = outranked
        self._outranking = outranking

    def rules(self) -> list[Rule]:
        return [
            ("replaces", lambda: self._narrow(self._not_replaced), self._explain_replaced),
            ("owner", self._owners, self._explain_owner),
            (
                "approved",
                lambda: self._narrow(lambda c: c.status != "draft"),
                lambda w, losers: f"{w.path} is approved; {_names(losers)} {_is(losers)} a draft.",
            ),
            (
                "newer",
                lambda: _newest(self.remaining),
                lambda w, losers: f"{w.path} ({w.date}) is newer than {_names(losers, dated=True)}.",
            ),
            (
                "live",
                lambda: self._narrow(lambda c: c.status not in ("archived", "replaced")),
                lambda w, losers: f"{w.path} is live; {_names(losers)} {_is(losers)} archived or replaced.",
            ),
        ]

    def _narrow(self, keep: Callable[[Candidate], bool]) -> list[Candidate]:
        """The documents that pass `keep`; all of them when none does, so a rule never empties the field."""
        kept = [c for c in self.remaining if keep(c)]
        return kept if kept else self.remaining

    def _not_replaced(self, c: Candidate) -> bool:
        return c.status != "replaced" and not any((other.file_id, c.file_id) in self._replaces
                                                  for other in self.remaining)

    def _in_charge(self, c: Candidate) -> bool:
        # An internal document is never in charge of what is said in public, even when it is the only one named.
        return (not c.internal and (c.file_id in self._owner_ids or c.file_id in self._outranking)
                and c.file_id not in self._outranked)

    def _owners(self) -> list[Candidate]:
        field = self.remaining
        if any(self._in_charge(c) for c in field):
            field = [c for c in field if self._in_charge(c)]
        public = [c for c in field if not c.internal]
        return public or field

    def _explain_replaced(self, w: Candidate, losers: list[Candidate]) -> str:
        if all((w.file_id, c.file_id) in self._replaces for c in losers):
            return f"{w.path} replaces {_names(losers)}."
        return f"{_names(losers)} {_has(losers)} been replaced; {w.path} has not."

    def _explain_owner(self, w: Candidate, losers: list[Candidate]) -> str:
        internal = [c for c in losers if c.internal]
        others = [c for c in losers if not c.internal]
        parts = [f"{w.path} is in charge of {self._topic or 'this topic'}"] if self._in_charge(w) else []
        if others:
            parts.append(f"{_names(others)} {_is(others)} not")
        if internal:
            parts.append(f"{_names(internal)} {_is(internal)} internal, so not in charge of what is said in public")
        return "; ".join(parts) + "."


def _newest(remaining: list[Candidate]) -> list[Candidate]:
    if any(not c.date for c in remaining):
        return remaining
    latest = max(c.date for c in remaining)
    return [c for c in remaining if c.date == latest]


def _names(candidates: list[Candidate], dated: bool = False) -> str:
    return ", ".join(f"{c.path} ({c.date})" if dated else c.path for c in candidates)


def _is(candidates: list[Candidate]) -> str:
    return "is" if len(candidates) == 1 else "are"


def _has(candidates: list[Candidate]) -> str:
    return "has" if len(candidates) == 1 else "have"
