"""Reads a brand, step by step:

1. basic facts and sections with search vectors (no AI, except the vectors)
2. a card per document (small model)
   images: info from the brand's image info file, and descriptions for images without a useful one
   (small vision model)
3. old and new names (medium model)
4. what documents say about each other, then final statuses (medium model, then rules)
5. single facts from rule and fact documents (medium model)
6. conflicts between documents, then winners (medium model, then rules)
   then image rules per channel, from the winning facts (medium model), and each image's rights and
   restrictions as clear fields, judged against those rules too (small model)
7. the brand summary (large model)

Every step keeps work whose input hasn't changed, so reading again only pays for what is new.
"""

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.service import AiCallFailed, AiService
from app.ai.transport import AiTransport
from app.brand import cards, conflicts, facts, links, names, parsing, summary
from app.brand.images.reading import ImageSteps
from app.brand.models import Brand, BrandFile, Conflict, DocLink, Entity, Fact, Section
from app.brand.settle import settle, summary_source
from app.config import ModelSize, Settings
from app.db import utc_now

log = logging.getLogger(__name__)

EMBED_BATCH = 200
WORKERS = 8


@dataclass(frozen=True)
class BrandReader:
    sessions: sessionmaker[Session]
    transport: AiTransport
    settings: Settings

    def read(self, brand_id: int) -> None:
        images = self._images
        self._run(brand_id, [
            self._prepare, self._index_sections, self._write_cards,
            images.record_info, images.describe,
            self._find_names, self._link_documents, self._settle, self._extract_facts, self._find_conflicts,
            self._settle, images.channel_rules, images.read_notes, self._write_summary,
        ])

    @property
    def _images(self) -> ImageSteps:
        return ImageSteps(self.sessions, self.transport, self.settings, self._phase, self._bump)

    def rebuild_summary(self, brand_id: int) -> None:
        """Rebuilds the summary from the current facts, replacing any edits."""
        with self.sessions() as session:
            session.get_one(Brand, brand_id).summary_edited = False
            session.commit()
        self._run(brand_id, [lambda brand_id: self._write_summary(brand_id, force=True)])

    def _run(self, brand_id: int, steps: list[Callable[[int], None]]) -> None:
        try:
            for step in steps:
                step(brand_id)
        except Exception as error:
            log.exception("Reading brand %s failed", brand_id)
            self._update(brand_id, status="failed", error=str(error), phase="")
            return
        self._update(brand_id, status="ready", error=None, phase="", read_finished_at=utc_now())

    # Steps

    def _prepare(self, brand_id: int) -> None:
        with self.sessions() as session:
            documents = _documents(session, brand_id)
            for document in documents:
                document.basics = parsing.basics(document.path, document.text or "")
            brand = session.get_one(Brand, brand_id)
            brand.status, brand.error = "reading", None
            brand.documents_total = len(documents)
            brand.documents_done = sum(1 for document in documents if not _needs_card(document))
            session.commit()

    def _index_sections(self, brand_id: int) -> None:
        """Splits changed documents into sections and gives each new section a search vector. The old sections
        are replaced only once every new one has its vector, in one step: if an embedding call fails, the
        documents keep their old sections, and the next read tries again."""
        with self.sessions() as session:
            changed = [d for d in _documents(session, brand_id) if d.sections_sha256 != d.sha256]
            if not changed:
                return
            self._phase(brand_id, "sections", len(changed))
            new_sections = [
                Section(brand_id=brand_id, file_id=document.id, position=position, heading=draft.heading,
                        text=draft.text, tokens=draft.tokens)
                for document in changed
                for position, draft in enumerate(parsing.split_sections(document.text or ""))
            ]
            ai = AiService(session, self.transport, self.settings, self.sessions)
            for start in range(0, len(new_sections), EMBED_BATCH):
                batch = new_sections[start : start + EMBED_BATCH]
                vectors = ai.embed(
                    step=f"Brand reading: search vectors ({start + 1}–{start + len(batch)} of {len(new_sections)})",
                    texts=[f"{section.heading}\n\n{section.text}" for section in batch],
                    brand_id=brand_id,
                )
                for section, vector in zip(batch, vectors, strict=True):
                    section.embedding = vector
            session.execute(delete(Section).where(Section.file_id.in_([d.id for d in changed])))
            session.add_all(new_sections)
            for document in changed:
                document.sections_sha256 = document.sha256
            session.commit()

    def _write_cards(self, brand_id: int) -> None:
        with self.sessions() as session:
            pending = [d.id for d in _documents(session, brand_id) if _needs_card(d)]
        self._phase(brand_id, "cards", len(pending))
        self._in_parallel(pending, lambda file_id: self._write_card(brand_id, file_id))

    def _write_card(self, brand_id: int, file_id: int) -> None:
        """A failed card is recorded on the file and doesn't stop the others."""
        with self.sessions() as session:
            document = session.get_one(BrandFile, file_id)
            try:
                reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                    step=f"Brand reading: document card ({document.path})",
                    size=ModelSize.SMALL,
                    prompt=cards.prompt_for(document.path, document.basics or {}, document.text or ""),
                    output_schema=cards.SCHEMA,
                    brand_id=brand_id,
                )
                document.card = cards.checked_card(reply.text, document.text or "")
                document.card_call_id, document.card_error = reply.call_id, None
            except (AiCallFailed, ValueError, KeyError) as error:
                document.card_error = str(error)
            document.card_sha256, document.card_version = document.sha256, cards.CARD_VERSION
            session.execute(update(Brand).where(Brand.id == brand_id).values(documents_done=Brand.documents_done + 1))
            session.commit()
        self._bump(brand_id)

    def _find_names(self, brand_id: int) -> None:
        with self.sessions() as session:
            brand = session.get_one(Brand, brand_id)
            documents = _documents(session, brand_id)
            found = names.collect_names([d.card for d in documents if d.card])
            hints = names.rename_sentences([(d.path, d.text or "") for d in documents], found)
            input_hash = _hash(names.NAMES_VERSION, found, hints)
            if brand.names_hash == input_hash:
                return
            self._phase(brand_id, "names", 1)
            entities: list[names.EntityDraft] = []
            if found:
                reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                    step="Brand reading: old and new names",
                    size=ModelSize.MEDIUM,
                    prompt=names.prompt_for(found, hints),
                    output_schema=names.SCHEMA,
                    brand_id=brand_id,
                )
                entities = names.checked_entities(reply.text, [(d.path, d.text or "") for d in documents])
            session.execute(delete(Entity).where(Entity.brand_id == brand_id))
            session.add_all(
                Entity(brand_id=brand_id, name=e.name, kind=e.kind, short_forms=e.short_forms, old_names=e.old_names)
                for e in entities
            )
            brand.names_hash = input_hash
            session.commit()

    def _link_documents(self, brand_id: int) -> None:
        with self.sessions() as session:
            brand = session.get_one(Brand, brand_id)
            documents = [d for d in _documents(session, brand_id) if d.card]
            found = links.statements(documents)
            input_hash = _hash(
                links.LINKS_VERSION,
                [[s.source_id, s.about, s.claim, s.evidence] for s in found],
                [[d.id, d.path, d.card.get("date", {}).get("iso"), d.card.get("summary")] for d in documents],
            )
            if brand.links_hash == input_hash:
                return
            self._phase(brand_id, "links", 1)
            drafts: list[links.LinkDraft] = []
            if found:
                reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                    step="Brand reading: what documents say about each other",
                    size=ModelSize.MEDIUM,
                    prompt=links.prompt_for(documents, found),
                    output_schema=links.SCHEMA,
                    brand_id=brand_id,
                )
                drafts = links.checked_links(reply.text, documents, found)
            session.execute(delete(DocLink).where(DocLink.brand_id == brand_id))
            session.add_all(
                DocLink(brand_id=brand_id, source_id=d.source_id, target_id=d.target_id, effect=d.effect,
                        claim=d.claim, evidence=d.evidence)
                for d in drafts
            )
            brand.links_hash = input_hash
            session.commit()

    def _settle(self, brand_id: int) -> None:
        with self.sessions() as session:
            settle(session, brand_id)

    def _extract_facts(self, brand_id: int) -> None:
        with self.sessions() as session:
            documents = _documents(session, brand_id)
            no_longer = [d.id for d in documents if d.doc_type not in facts.DOC_TYPES_WITH_FACTS]
            session.execute(delete(Fact).where(Fact.file_id.in_(no_longer)))
            session.commit()
            pending = [d.id for d in documents if d.doc_type in facts.DOC_TYPES_WITH_FACTS and _needs_facts(d)]
            entities = _entities(session, brand_id)
        vocabulary = names.vocabulary(entities)
        self._phase(brand_id, "facts", len(pending))
        self._in_parallel(pending, lambda file_id: self._extract(brand_id, file_id, vocabulary))
        with self.sessions() as session:
            keys = names.subject_keys(_entities(session, brand_id))
            for fact in session.scalars(select(Fact).where(Fact.brand_id == brand_id)):
                fact.subject_key = names.key_for(fact.subject, keys)
            session.commit()

    def _extract(self, brand_id: int, file_id: int, vocabulary: str) -> None:
        with self.sessions() as session:
            document = session.get_one(BrandFile, file_id)
            try:
                reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                    step=f"Brand reading: facts ({document.path})",
                    size=ModelSize.MEDIUM,
                    prompt=facts.prompt_for(document.path, vocabulary, document.text or ""),
                    output_schema=facts.SCHEMA,
                    brand_id=brand_id,
                )
                kept, dropped = facts.checked_facts(reply.text, document.text or "")
                session.execute(delete(Fact).where(Fact.file_id == file_id))
                session.add_all(
                    Fact(brand_id=brand_id, file_id=file_id, subject=f.subject, subject_key=f.subject.lower(),
                         attribute=f.attribute, value=f.value, kind=f.kind, scope=f.scope, evidence=f.evidence)
                    for f in kept
                )
                if dropped:
                    log.info("Dropped %s facts from %s: quote not found", dropped, document.path)
                document.facts_call_id, document.facts_error = reply.call_id, None
            except (AiCallFailed, ValueError, KeyError) as error:
                document.facts_error = str(error)
            document.facts_sha256, document.facts_version = document.sha256, facts.FACT_VERSION
            session.commit()
        self._bump(brand_id)

    def _find_conflicts(self, brand_id: int) -> None:
        with self.sessions() as session:
            brand = session.get_one(Brand, brand_id)
            groups = _fact_groups(session, brand_id)
            checked = dict(brand.checked_groups or {})
            stale = [key for key in checked if checked[key] != groups.get(key, (None,))[0]]
            session.execute(delete(Conflict).where(Conflict.brand_id == brand_id, Conflict.subject_key.in_(stale)))
            for key in stale:
                checked.pop(key)
            brand.checked_groups = checked
            session.commit()
            pending = [key for key, (group_hash, _) in groups.items() if checked.get(key) != group_hash]
        self._phase(brand_id, "conflicts", len(pending))
        self._in_parallel(pending, lambda key: self._check_group(brand_id, key, groups[key][0]))

    def _check_group(self, brand_id: int, subject_key: str, group_hash: str) -> None:
        with self.sessions() as session:
            documents = {d.id: d for d in _documents(session, brand_id)}
            rows = list(
                session.scalars(
                    select(Fact).where(Fact.brand_id == brand_id, Fact.subject_key == subject_key).order_by(Fact.id)
                )
            )
            views = [conflicts.FactView(f.id, f.file_id, f.attribute, f.value, f.kind, f.scope) for f in rows]
            sheets = [_sheet(documents[file_id]) for file_id in sorted({f.file_id for f in rows})]
            try:
                reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                    step=f"Brand reading: conflicts ({rows[0].subject})",
                    size=ModelSize.MEDIUM,
                    prompt=conflicts.prompt_for(rows[0].subject, sheets, views),
                    output_schema=conflicts.SCHEMA,
                    brand_id=brand_id,
                )
                found = conflicts.checked_conflicts(reply.text, views)
            except (AiCallFailed, ValueError, KeyError):
                log.exception("Conflict check for %s failed; it will be tried again on the next read", subject_key)
                self._bump(brand_id)
                return
            session.execute(delete(Conflict).where(Conflict.brand_id == brand_id, Conflict.subject_key == subject_key))
            session.add_all(
                Conflict(brand_id=brand_id, subject_key=subject_key, group_hash=group_hash, point=item.point,
                         topic=item.topic, fact_ids=item.fact_ids, owner_file_ids=item.owner_file_ids,
                         sides=[{"position": side.position, "fact_ids": side.fact_ids} for side in item.sides],
                         rule="needs_human", reason="Not judged yet.", call_id=reply.call_id)
                for item in found
            )
            # Merged in the database: checks run in parallel and must not overwrite each other.
            entry = func.jsonb_build_object(subject_key, group_hash)
            session.execute(
                update(Brand).where(Brand.id == brand_id).values(checked_groups=Brand.checked_groups.op("||")(entry))
            )
            session.commit()
        self._bump(brand_id)

    def _write_summary(self, brand_id: int, force: bool = False) -> None:
        with self.sessions() as session:
            brand = session.get_one(Brand, brand_id)
            text = summary_source(session, brand)
            input_hash = summary.source_hash(text)
            if not force and (brand.summary_edited or (brand.summary and brand.summary_source_hash == input_hash)):
                return
            self._phase(brand_id, "summary", 1)
            reply = AiService(session, self.transport, self.settings, self.sessions).complete(
                step="Brand reading: brand summary",
                size=ModelSize.LARGE,
                prompt=summary.prompt_for(text),
                brand_id=brand_id,
            )
            brand.summary, brand.summary_source_hash = reply.text, input_hash
            brand.summary_call_id, brand.summary_stale = reply.call_id, False
            session.commit()

    # Helpers

    def _in_parallel(self, items: list, work: Callable[..., None]) -> None:
        with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="brand") as pool:
            list(pool.map(work, items))

    def _phase(self, brand_id: int, phase: str, total: int) -> None:
        self._update(brand_id, phase=phase, phase_done=0, phase_total=total)

    def _bump(self, brand_id: int) -> None:
        with self.sessions() as session:
            session.execute(update(Brand).where(Brand.id == brand_id).values(phase_done=Brand.phase_done + 1))
            session.commit()

    def _update(self, brand_id: int, **values: object) -> None:
        with self.sessions() as session:
            session.execute(update(Brand).where(Brand.id == brand_id).values(**values))
            session.commit()


def _documents(session: Session, brand_id: int) -> list[BrandFile]:
    """In a fixed order, so prompts built from them are identical between reads."""
    return list(
        session.scalars(
            select(BrandFile).where(BrandFile.brand_id == brand_id, BrandFile.kind == "document").order_by(BrandFile.id)
        )
    )


def _entities(session: Session, brand_id: int) -> list[names.EntityDraft]:
    return [
        names.EntityDraft(e.name, e.kind, e.short_forms, e.old_names)
        for e in session.scalars(select(Entity).where(Entity.brand_id == brand_id))
    ]


def _fact_groups(session: Session, brand_id: int) -> dict[str, tuple[str, list[int]]]:
    """Subjects with facts from at least two documents, with the hash of those facts and their files."""
    rows = session.execute(
        select(Fact.subject_key, Fact.file_id, BrandFile.sha256, Fact.attribute, Fact.value, Fact.kind)
        .join(BrandFile, BrandFile.id == Fact.file_id)
        .where(Fact.brand_id == brand_id)
    )
    by_subject: dict[str, list] = defaultdict(list)
    for subject_key, file_id, sha, attribute, value, kind in rows:
        by_subject[subject_key].append((file_id, (sha, attribute, value, kind)))
    return {
        key: (conflicts.group_hash(key, [row for _, row in items]), sorted({file_id for file_id, _ in items}))
        for key, items in by_subject.items()
        if len({file_id for file_id, _ in items}) >= 2
    }


def _sheet(document: BrandFile) -> conflicts.DocSheet:
    card = document.card or {}
    owner = card.get("owner", {})
    return conflicts.DocSheet(
        id=document.id,
        path=document.path,
        doc_type=document.doc_type or "unknown",
        status=document.status or "current",
        owner=", ".join(filter(None, [owner.get("name"), owner.get("role")])),
        rules_on=card.get("rules_on", []),
    )


def _needs_card(document: BrandFile) -> bool:
    return (
        document.card_sha256 != document.sha256
        or document.card_version != cards.CARD_VERSION
        or document.card_error is not None
    )


def _needs_facts(document: BrandFile) -> bool:
    return (
        document.facts_sha256 != document.sha256
        or document.facts_version != facts.FACT_VERSION
        or document.facts_error is not None
    )


def _hash(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
