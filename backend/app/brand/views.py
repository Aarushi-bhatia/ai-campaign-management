"""Builds the Brand page's data from what is stored."""

from collections import Counter
from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.brand import facts as fact_types
from app.brand.images.library import image_views, rules_for
from app.brand.images.notes import ASSET_CHANNELS
from app.brand.images.picking import AssetSpec, blocked_reason
from app.brand.models import Brand, Conflict, DocLink, Entity, Fact, ImageInfo, Section
from app.brand.schemas import (
    BrandOut,
    BrandSummary,
    ConflictFactOut,
    ConflictOut,
    DecisionOut,
    DocumentOut,
    EntityOut,
    ImageOut,
    LinkOut,
    OtherFileOut,
    ReadingCostOut,
)
from app.brand.service import BrandService
from app.brand.settle import chosen_winner, conflict_target, decisions_of, winning_fact_ids

RULE_ORDER = {"needs_human": 0, "you": 1}


def brand_view(session: Session, brands: BrandService, brand: Brand) -> BrandOut:
    documents = [f for f in brand.files if f.kind == "document"]
    path_of = {d.id: d.path for d in documents}
    sections = _counts(session, Section.file_id, Section.brand_id == brand.id)
    fact_counts = _counts(session, Fact.file_id, Fact.brand_id == brand.id)
    return BrandOut(
        **BrandSummary.model_validate(brand).model_dump(),
        documents=[
            DocumentOut(
                id=d.id, path=d.path, tokens=(d.basics or {}).get("tokens", 0), sections=sections.get(d.id, 0),
                facts=fact_counts.get(d.id, 0) if fact_types.counts(d.doc_type) else 0, basics=d.basics, card=d.card, card_error=d.card_error,
                card_call_id=d.card_call_id, facts_error=d.facts_error, facts_call_id=d.facts_call_id,
                doc_type=d.doc_type, status=d.status, status_reason=d.status_reason,
                replaced_by=path_of.get(d.replaced_by_id) if d.replaced_by_id else None,
            )
            for d in documents
        ],
        other_files=[OtherFileOut.model_validate(f) for f in brand.files if f.kind != "document"],
        reading_cost=ReadingCostOut(**asdict(brands.reading_cost(brand.id))),
        conflicts=_conflicts(session, brand.id, path_of),
        entities=[
            EntityOut.model_validate(e)
            for e in session.scalars(select(Entity).where(Entity.brand_id == brand.id).order_by(Entity.name))
        ],
        links=[
            LinkOut(source=path_of[l.source_id], target=path_of[l.target_id], effect=l.effect, claim=l.claim,
                    evidence=l.evidence)
            for l in session.scalars(select(DocLink).where(DocLink.brand_id == brand.id))
            if l.source_id in path_of and l.target_id in path_of
        ],
        decisions=[DecisionOut.model_validate(d) for d in brands.decisions(brand.id)],
        excluded=brands.exclusions(brand.id),
        summary=brand.summary,
        summary_edited=brand.summary_edited,
        summary_stale=brand.summary_stale,
        summary_call_id=brand.summary_call_id,
        images=_images(session, brand),
        image_rules=brand.image_rules,
        image_rules_call_id=brand.image_rules_call_id,
    )


def file_url(brand_id: int, path: str) -> str:
    return f"/api/brands/{brand_id}/files/{path}"


def _images(session: Session, brand: Brand) -> list[ImageOut]:
    rows = {
        info.file_id: info for info in session.scalars(select(ImageInfo).where(ImageInfo.brand_id == brand.id))
    }
    path_to_file = {f.path: f.id for f in brand.files if f.kind == "image"}
    rules = rules_for(brand)["channels"]
    out = []
    for view in image_views(session, brand.id):
        row = rows[path_to_file[view.path]]
        restricted = [blocked_reason(view, AssetSpec(channel, "", "", slot="inline"), rules) for channel in ASSET_CHANNELS]
        out.append(
            ImageOut(
                id=view.id, path=view.path, url=file_url(brand.id, view.path), title=view.title,
                description=view.description, description_source=row.description_source, image_type=view.image_type,
                tags=list(view.tags), width=view.width, height=view.height, transparent=view.transparent,
                record=row.record, notes=view.notes, usable_override=view.usable_override,
                blocked=restricted[0] if all(restricted) else None,
                channels={
                    channel: blocked_reason(view, AssetSpec(channel, "", ""), rules) for channel in ASSET_CHANNELS
                },
                describe_call_id=row.describe_call_id, notes_call_id=row.notes_call_id,
            )
        )
    return out


def _conflicts(session: Session, brand_id: int, path_of: dict[int, str]) -> list[ConflictOut]:
    rows = list(session.scalars(select(Conflict).where(Conflict.brand_id == brand_id)))
    fact_ids = [fact_id for row in rows for fact_id in row.fact_ids]
    facts = {f.id: f for f in session.scalars(select(Fact).where(Fact.id.in_(fact_ids)))}
    decisions = decisions_of(session, brand_id)
    out = []
    for row in rows:
        members = [facts[fact_id] for fact_id in row.fact_ids if fact_id in facts]
        if not members:
            continue
        side_of_fact = {fact_id: index for index, side in enumerate(row.sides) for fact_id in side["fact_ids"]}
        winning = set(winning_fact_ids(row, facts))
        winning_side = next((side_of_fact[i] for i in winning if i in side_of_fact), None)
        paths = sorted({path_of[f.file_id] for f in members if f.file_id in path_of})
        out.append(
            ConflictOut(
                id=row.id,
                subject=Counter(f.subject for f in members).most_common(1)[0][0],
                point=row.point,
                topic=row.topic,
                rule=row.rule,
                reason=row.reason,
                winner=path_of.get(row.winner_file_id) if row.winner_file_id else None,
                owners=[path_of[i] for i in row.owner_file_ids if i in path_of],
                sides=[side["position"] for side in row.sides],
                winning_side=winning_side,
                facts=[
                    ConflictFactOut(id=f.id, side=side_of_fact.get(f.id, 0), path=path_of.get(f.file_id, ""),
                                    attribute=f.attribute, value=f.value, kind=f.kind, evidence=f.evidence)
                    for f in members
                ],
                target=conflict_target(row, facts, paths),
                decided_target=chosen_winner(row, facts, paths, decisions)[2],
                call_id=row.call_id,
            )
        )
    return sorted(out, key=lambda c: (RULE_ORDER.get(c.rule, 2), c.subject.lower(), c.id))


def _counts(session: Session, column, condition) -> dict[int, int]:
    return dict(session.execute(select(column, func.count()).where(condition).group_by(column)).all())
