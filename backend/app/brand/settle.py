"""Works out document statuses and conflict winners from what is stored. No AI.

Runs at the end of every read and straight after every correction, so corrections apply at once.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brand import conflicts as conflict_rules
from app.brand import summary
from app.brand.models import Brand, BrandDecision, BrandFile, Conflict, DocLink, Fact
from app.brand.status import DocView, LinkView, decide_statuses


def conflict_target(subject_key: str, paths: list[str]) -> str:
    """How a conflict is named in a correction, so the correction still finds it after a re-read."""
    return f"{subject_key} | {' + '.join(sorted(paths))}"


def settle(session: Session, brand_id: int) -> None:
    brand = session.get_one(Brand, brand_id)
    documents = _documents(session, brand_id)
    by_id = {document.id: document for document in documents}
    by_path = {document.path: document for document in documents}
    decisions = _decisions(session, brand_id)

    for document in documents:
        document.doc_type = decisions.get(("document_kind", document.path)) or (document.card or {}).get("kind")

    links = list(session.scalars(select(DocLink).where(DocLink.brand_id == brand_id)))
    corrections = {
        by_path[target].id: value
        for (kind, target), value in decisions.items()
        if kind == "document_status" and target in by_path
    }
    results = decide_statuses(
        [_doc_view(document) for document in documents],
        [LinkView(link.source_id, link.target_id, link.effect, link.evidence) for link in links],
        corrections,
    )
    for document in documents:
        result = results[document.id]
        document.status, document.status_reason, document.replaced_by_id = (
            result.status, result.reason, result.replaced_by,
        )

    replaces = {(link.source_id, link.target_id) for link in links if link.effect in ("replaces", "outdated")}
    replaces |= {(d.replaced_by_id, d.id) for d in documents if d.replaced_by_id}
    outranking = {link.target_id for link in links if link.effect == "higher_authority"}
    outranked = {link.target_id for link in links if link.effect == "lower_authority"}
    for conflict in session.scalars(select(Conflict).where(Conflict.brand_id == brand_id)):
        _judge(session, conflict, by_id, decisions, replaces, outranking, outranked)

    session.flush()
    if brand.summary:
        brand.summary_stale = summary.source_hash(summary_source(session, brand)) != brand.summary_source_hash
    session.commit()


def usable_facts(session: Session, brand_id: int) -> list[tuple[Fact, BrandFile]]:
    """Facts from current, quotable documents, minus facts that lost a conflict, with their documents."""
    documents = {d.id: d for d in _documents(session, brand_id)}
    usable = {
        doc_id for doc_id, d in documents.items()
        if d.status == "current" and (d.card or {}).get("safe_to_quote", {}).get("value") != "no"
    }
    facts = {f.id: f for f in session.scalars(select(Fact).where(Fact.brand_id == brand_id).order_by(Fact.id))}
    excluded: set[int] = set()
    for conflict in session.scalars(select(Conflict).where(Conflict.brand_id == brand_id)):
        winning = set(winning_fact_ids(conflict, facts))
        excluded.update(fact_id for fact_id in conflict.fact_ids if fact_id not in winning)
    return [(f, documents[f.file_id]) for f in facts.values() if f.file_id in usable and f.id not in excluded]


def summary_source(session: Session, brand: Brand) -> str:
    """The facts the summary is built from."""
    chosen = [
        summary.SummaryFact(f.subject, f.attribute, f.value, f.kind, f.scope, document.path)
        for f, document in usable_facts(session, brand.id)
    ]
    return summary.source_text(brand.name, chosen)


def winning_fact_ids(conflict: Conflict, facts: dict[int, Fact]) -> list[int]:
    """The facts on the winning side. None when nobody has won yet."""
    if conflict.winner_file_id is None:
        return []
    for side in conflict.sides:
        if any(facts[i].file_id == conflict.winner_file_id for i in side["fact_ids"] if i in facts):
            return side["fact_ids"]
    return []


def side_of_files(conflict: Conflict, facts: dict[int, Fact]) -> dict[int, int]:
    """Which side each document takes. A document with facts on two sides counts for the first."""
    sides: dict[int, int] = {}
    for index, side in enumerate(conflict.sides):
        for fact_id in side["fact_ids"]:
            if fact_id in facts:
                sides.setdefault(facts[fact_id].file_id, index)
    return sides


def _judge(
    session: Session,
    conflict: Conflict,
    by_id: dict[int, BrandFile],
    decisions: dict[tuple[str, str], str],
    replaces: set[tuple[int, int]],
    outranking: set[int],
    outranked: set[int],
) -> None:
    facts = {f.id: f for f in session.scalars(select(Fact).where(Fact.id.in_(conflict.fact_ids)))}
    file_ids = sorted({fact.file_id for fact in facts.values()})
    candidates = [
        conflict_rules.Candidate(
            file_id, by_id[file_id].path, by_id[file_id].status or "current",
            (by_id[file_id].card or {}).get("date", {}).get("iso", ""), _is_internal(by_id[file_id]),
        )
        for file_id in file_ids
        if file_id in by_id
    ]
    chosen_path = decisions.get(("conflict_winner", conflict_target(conflict.subject_key, [c.path for c in candidates])))
    chosen = next((c for c in candidates if c.path == chosen_path), None)
    if chosen:
        conflict.winner_file_id, conflict.rule, conflict.reason = chosen.file_id, "you", "You chose this on the Brand page."
        return
    verdict = conflict_rules.pick_winner(
        candidates, conflict.owner_file_ids, conflict.topic, replaces, outranked, outranking,
        side_of_files(conflict, facts),
    )
    conflict.winner_file_id, conflict.rule, conflict.reason = verdict.winner_file_id, verdict.rule, verdict.reason


def _is_internal(document: BrandFile) -> bool:
    not_public = (document.card or {}).get("safe_to_quote", {}).get("value") == "no"
    return document.doc_type == "internal_note" or not_public


def _doc_view(document: BrandFile) -> DocView:
    card = document.card or {}
    return DocView(
        id=document.id,
        path=document.path,
        claimed=card.get("claimed_status", {}).get("value", "unknown"),
        claimed_evidence=card.get("claimed_status", {}).get("evidence", ""),
        date=card.get("date", {}).get("iso", ""),
        name_hints=tuple((document.basics or {}).get("name_hints", [])),
    )


def _documents(session: Session, brand_id: int) -> list[BrandFile]:
    return list(
        session.scalars(
            select(BrandFile).where(BrandFile.brand_id == brand_id, BrandFile.kind == "document").order_by(BrandFile.id)
        )
    )


def _decisions(session: Session, brand_id: int) -> dict[tuple[str, str], str]:
    rows = session.scalars(select(BrandDecision).where(BrandDecision.brand_id == brand_id).order_by(BrandDecision.id))
    return {(row.kind, row.target): row.value for row in rows}
