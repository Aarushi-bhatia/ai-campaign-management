"""The tools the campaign agent uses to look things up in the brand. Only current material comes back;
internal material is labelled as background, never to be quoted. The tools also note which settled
conflicts the agent ran into, so the chat can say which document was used over which.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompt import TEXT, strict_object
from app.ai.service import AiService, Tool
from app.brand import facts as fact_types
from app.brand import names
from app.brand.images.library import rules_for
from app.brand.models import Brand, BrandFile, Conflict, Entity, Fact, Section
from app.brand.settle import winning_fact_ids

SEARCH_RESULTS = 6
FACT_RESULTS = 30
SECTION_CHARS = 1500
DOCUMENT_CHARS = 12000

CHANNEL_RULES = 60
"""At most this many rules for one channel, the most relevant ones (see `_channel_score`)."""

CHANNEL_WORDS = {
    "email": ("email", "e-mail", "newsletter", "subject line", "preheader", "inbox"),
    "linkedin": ("linkedin",),
    "x": ("twitter", "tweet", "x post", "x posts", "x thread"),
    "blog": ("blog", "article", "post title"),
    "landing_page": ("landing page", "landing pages", "web page", "website", "hero"),
}


@dataclass
class BrandTools:
    session: Session
    ai: AiService
    brand: Brand
    chat_id: int | None = None
    conflicts_seen: set[int] = field(default_factory=set)

    def tools(self) -> list[Tool]:
        return [
            Tool("search_brand", "Search the brand's current documents by meaning. Returns matching sections.",
                 strict_object({"query": TEXT}), lambda args: self.search(args["query"])),
            Tool("get_facts", "Facts and rules about a product, claim, customer, topic or name, with the sentence "
                 "each comes from. Facts that lost a conflict between documents are left out.",
                 strict_object({"topic": TEXT}), lambda args: self.facts(args["topic"])),
            Tool("get_channel_rules", "The brand's rules for one channel: email, linkedin, x, blog or landing_page.",
                 strict_object({"channel": TEXT}), lambda args: self.channel_rules(args["channel"])),
            Tool("read_document", "Read a document, or one section of it by heading. Use a path from another result.",
                 strict_object({"path": TEXT, "heading": TEXT}), lambda args: self.read(args["path"], args["heading"])),
            Tool("get_conflicts", "Where the brand's documents disagree on a topic, and which side won and why.",
                 strict_object({"topic": TEXT}), lambda args: self.conflicts(args["topic"])),
        ]

    def search(self, query: str) -> str:
        [vector] = self.ai.embed(step="Brand search", texts=[query], brand_id=self.brand.id, chat_id=self.chat_id)
        rows = self.session.execute(
            select(Section, BrandFile)
            .join(BrandFile, BrandFile.id == Section.file_id)
            .where(Section.brand_id == self.brand.id, BrandFile.status == "current")
            .order_by(Section.embedding.cosine_distance(vector))
            .limit(SEARCH_RESULTS)
        ).all()
        return _dump([
            {"path": doc.path, "heading": section.heading, **_label(doc), "text": section.text[:SECTION_CHARS]}
            for section, doc in rows
        ])

    def facts(self, topic: str) -> str:
        words = _words(topic)
        key = names.key_for(topic, names.subject_keys(self._entities()))
        current, winners = self._current_facts()
        scored = []
        for fact, doc in current:
            text = f"{fact.subject} {fact.attribute} {fact.value} {fact.scope}".lower()
            score = (5 if fact.subject_key == key else 0) + sum(1 for word in words if word in text)
            if score:
                scored.append((score, fact, doc))
        scored.sort(key=lambda item: -item[0])
        chosen = [(fact, doc) for _, fact, doc in scored[:FACT_RESULTS]]
        self._note_conflicts(chosen, winners)
        return _dump([_fact_out(fact, doc) for fact, doc in chosen]) if chosen else "No facts found."

    def channel_rules(self, channel: str) -> str:
        channel = channel.strip().lower().replace(" ", "_")
        if channel not in CHANNEL_WORDS:
            return f"Unknown channel. Use one of: {', '.join(CHANNEL_WORDS)}."
        words = CHANNEL_WORDS[channel]
        current, winners = self._current_facts()
        scored = [(score, i, fact, doc) for i, (fact, doc) in enumerate(current)
                  if (score := _channel_score(channel, words, fact, doc))]
        # Most relevant first, so a cut never drops a playbook rule for a passing mention elsewhere.
        scored.sort(key=lambda item: (-item[0], item[1]))
        chosen = [(fact, doc) for _, _, fact, doc in scored[:CHANNEL_RULES]]
        self._note_conflicts(chosen, winners)
        image_rules = rules_for(self.brand)["channels"].get(channel, {})
        if not chosen:
            return _dump({"rules": [], "note": f"The brand's documents say nothing about {channel}.",
                          "image_rules": image_rules})
        out = {"rules": [_fact_out(fact, doc, quote=False) for fact, doc in chosen], "image_rules": image_rules}
        if len(scored) > len(chosen):
            out["note"] = f"{len(scored) - len(chosen)} less relevant {channel} rules were left out."
        return _dump(out)

    def read(self, path: str, heading: str) -> str:
        documents = self._documents()
        doc = next((d for d in documents if d.path == path or d.path.endswith(path.lstrip("/"))), None)
        if doc is None:
            return "No such document."
        if doc.status != "current":
            # Only current material reaches the agent; a replaced or archived document's text could slip into copy.
            newer = next((d.path for d in documents if d.id == doc.replaced_by_id), None)
            return (f"{doc.path} is {doc.status or 'not current'}, so it isn't used for this brand"
                    + (f"; read {newer} instead." if newer else "."))
        text = doc.text or ""
        if heading:
            sections = self.session.scalars(
                select(Section).where(Section.file_id == doc.id).order_by(Section.position)
            ).all()
            matching = [s.text for s in sections if heading.lower() in s.heading.lower()]
            text = "\n\n".join(matching) or text
        return _dump({"path": doc.path, "status": doc.status, **_label(doc), "text": text[:DOCUMENT_CHARS]})

    def conflicts(self, topic: str) -> str:
        words = _words(topic)
        found = []
        facts = {f.id: f for f in self.session.scalars(select(Fact).where(Fact.brand_id == self.brand.id))}
        paths = {d.id: d.path for d in self._documents()}
        for conflict in self.session.scalars(select(Conflict).where(Conflict.brand_id == self.brand.id,
                                                                     Conflict.rule != "not_counting")):
            text = f"{conflict.subject_key} {conflict.topic} {conflict.point}".lower()
            if not any(word in text for word in words):
                continue
            self.conflicts_seen.add(conflict.id)
            winning = set(winning_fact_ids(conflict, facts))
            found.append({
                "id": conflict.id,
                "point": conflict.point,
                "settled": conflict.winner_file_id is not None,
                "winner": paths.get(conflict.winner_file_id),
                "reason": conflict.reason,
                "sides": [
                    {"position": side["position"], "won": bool(winning & set(side["fact_ids"])),
                     "documents": sorted({paths.get(facts[i].file_id, "") for i in side["fact_ids"] if i in facts})}
                    for side in conflict.sides
                ],
            })
        return _dump(found) if found else "No conflicts on that topic."

    def _current_facts(self) -> tuple[list[tuple[Fact, BrandFile]], dict[int, int]]:
        """Facts from current documents, minus those that lost a conflict; and, for facts that won a
        conflict, which conflict."""
        docs = {d.id: d for d in self._documents() if d.status == "current" and fact_types.counts(d.doc_type)}
        facts = list(self.session.scalars(select(Fact).where(Fact.brand_id == self.brand.id).order_by(Fact.id)))
        by_id = {f.id: f for f in facts}
        losers: set[int] = set()
        winners: dict[int, int] = {}
        for conflict in self.session.scalars(select(Conflict).where(Conflict.brand_id == self.brand.id)):
            won = set(winning_fact_ids(conflict, by_id))
            losers.update(i for i in conflict.fact_ids if i not in won)
            winners.update({i: conflict.id for i in won})
        return [(f, docs[f.file_id]) for f in facts if f.file_id in docs and f.id not in losers], winners

    def _note_conflicts(self, returned: list[tuple[Fact, BrandFile]], winners: dict[int, int]) -> None:
        """Facts handed to the agent that won a conflict mean the agent is relying on that decision."""
        self.conflicts_seen.update(winners[fact.id] for fact, _ in returned if fact.id in winners)

    def _documents(self) -> list[BrandFile]:
        return list(self.session.scalars(
            select(BrandFile).where(BrandFile.brand_id == self.brand.id, BrandFile.kind == "document")
        ))

    def _entities(self) -> list[names.EntityDraft]:
        return [names.EntityDraft(e.name, e.kind, e.short_forms, e.old_names)
                for e in self.session.scalars(select(Entity).where(Entity.brand_id == self.brand.id))]


def _fact_out(fact: Fact, doc: BrandFile, quote: bool = True) -> dict[str, Any]:
    """A fact for the agent. Channel rules leave out the proving sentence: there are many, and the rule is enough."""
    return {"id": fact.id, "subject": fact.subject, "says": f"{fact.attribute}: {fact.value}", "kind": fact.kind,
            **({"only_for": fact.scope} if fact.scope else {}), "source": doc.path,
            **({"quote": fact.evidence} if quote else {}), **_label(doc)}


def _label(doc: BrandFile) -> dict[str, str]:
    internal = doc.doc_type == "internal_note" or (doc.card or {}).get("safe_to_quote", {}).get("value") == "no"
    return {"use": "background only, never quote or repeat in copy"} if internal else {}


def _channel_score(channel: str, words: tuple[str, ...], fact, doc) -> int:
    """How much a fact is about this channel: rules from the channel's own playbook first, then facts whose
    subject or scope names it, then facts that only mention it. 0 when it has nothing to do with the channel."""
    path = doc.path.lower()
    about = f"{fact.subject} {fact.attribute} {fact.scope}".lower()
    in_path = any(word in path for word in words) or (channel == "x" and "x-" in path.rsplit("/", 1)[-1])
    in_scope = any(word in fact.scope.lower() for word in words) or (channel == "x" and fact.scope.strip().lower() == "x")
    in_about = any(word in about for word in words)
    if not (in_path or in_scope or in_about):
        return 0
    return 4 * in_path + 3 * in_scope + 2 * in_about + ("playbook" in path or "channels/" in path)


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
