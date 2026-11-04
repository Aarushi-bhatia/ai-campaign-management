"""Web research for a campaign. It only runs while planning, or when the marketer asks for a better source.

Each search runs once per campaign, and only once it has really run: a search that failed (a timeout, an
error from the search service or from the notes step) is reported as failed, marked on its plan card with a Try
again button, and also tried again on the next chat change to the plan. A finding belongs to the plan cards that
asked for it. A card keeps its findings when a plan edit only rewords its search, so that costs nothing; when the
plan-edit model says the marketer moved the card's research to a different subject, its old findings stop
counting, the chat says so, and the new search runs. Whether a search changed subject is the model's call: it
read the marketer's message, and counting shared words gets it wrong both ways.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.ai.service import AiService
from app.campaign.models import Campaign
from app.campaign.runtime import Runtime
from app.research.client import WebResearch
from app.research.notes import Finding, research

log = logging.getLogger(__name__)

PARALLEL_SEARCHES = 3


class UnknownFinding(ValueError):
    pass


@dataclass(frozen=True)
class Search:
    """What one search came back with: findings, or why it failed."""

    findings: list[dict[str, Any]]
    error: str | None = None


@dataclass
class CampaignResearch:
    ai: AiService
    web: WebResearch | None
    brand_name: str
    campaign: Campaign
    runtime: Runtime | None = None
    """When given, several searches run at once, each logging its AI call in its own database session."""
    off_limits: tuple[str, ...] = ()
    """The brand's and its products' names. A web finding about them is dropped: brand documents rule there."""

    def for_plan(self, research_changed: frozenset[str] = frozenset()) -> list[str]:
        """Runs the searches the plan asks for that haven't run yet. Returns lines for the chat.
        `research_changed` holds the cards a plan edit moved to a different research subject."""
        moved = self.relink(research_changed)
        cards = (self.campaign.plan or {}).get("assets", [])
        has_findings = {i for f in self.campaign.research if not f["removed"] for i in f["asset_ids"]}
        searched = {_key(q) for q in self.campaign.searches}
        wanted: dict[str, tuple[str, list[str]]] = {}
        for card in cards:
            query = card.get("research_query", "").strip()
            if not query or card["id"] in has_findings or _key(query) in searched:
                continue
            wanted.setdefault(_key(query), (query, []))[1].append(card["id"])
        notes = [f"“{card['title']}”: its research moved to a new subject, so its earlier findings no longer count."
                 for card in cards if card["id"] in moved]
        if not wanted:
            if (self.campaign.plan or {}).get("failed_searches"):
                self.campaign.plan = {**self.campaign.plan, "failed_searches": []}
            return notes
        if self.web is None:
            return [*notes, "Web research is off (no FIRECRAWL_API_KEY), so the plan uses brand documents only."]
        jobs = list(wanted.values())
        results = self._run_all([(query, ids, frozenset()) for query, ids in jobs])
        failed = []
        for (query, _), result in zip(jobs, results, strict=True):
            if result.error:
                failed.append(query)
                notes.append(f"Web search for “{query}” failed ({result.error}). Nothing was found or kept; press "
                             "Try again on its plan card, or it runs again on the next chat change to the plan.")
                continue
            self.campaign.research = [*self.campaign.research, *result.findings]
            self.campaign.searches = [*self.campaign.searches, query]
            notes.append(f"Searched the web for “{query}”: {_count(len(result.findings))}, shown on the plan.")
        # Plan cards show a Try again button for these.
        self.campaign.plan = {**self.campaign.plan, "failed_searches": failed}
        return notes

    def on_request(self, query: str, asset_ids: list[str]) -> list[str]:
        """Research the marketer asked for directly, during an edit. Its findings count as approved."""
        if self.web is None:
            return ["Web research is off (no FIRECRAWL_API_KEY)."]
        result = self._search(query, asset_ids, skip=frozenset(f["url"] for f in self.campaign.research))
        if result.error:
            return [f"Web search for “{query}” failed ({result.error}). Ask again to retry."]
        self.campaign.research = [*self.campaign.research, *result.findings]
        self.campaign.searches = [*self.campaign.searches, query]
        return [f"Searched the web for “{query}”, as asked: {_count(len(result.findings))}."]

    def remove(self, finding_id: str) -> None:
        self._set_removed(finding_id, True)

    def bring_back(self, finding_id: str) -> None:
        self._set_removed(finding_id, False)

    def better_source(self, finding_id: str) -> str:
        """Searches again, leaving out every page already used. The old finding is only replaced when
        something new turns up; otherwise it stays as it was."""
        finding = next(f for f in self._known(finding_id) if f["id"] == finding_id)
        if self.web is None:
            return "Web research is off (no FIRECRAWL_API_KEY)."
        used = frozenset(f["url"] for f in self.campaign.research)
        result = self._search(finding["query"], finding["asset_ids"], skip=used)
        if result.error:
            return f"Couldn't look for a better source for “{finding['query']}”: {result.error}. The finding is kept."
        if not result.findings:
            return f"Looked for a better source for “{finding['query']}”: nothing new turned up, so the finding is kept."
        self.remove(finding_id)
        self.campaign.research = [*self.campaign.research, *result.findings]
        return f"Looked for a better source for “{finding['query']}”: {_count(len(result.findings))}, replacing the old one."

    def relink(self, research_changed: frozenset[str] = frozenset()) -> set[str]:
        """Ties each finding to the plan cards that still want it: the cards it was found for, while they are in
        the plan, still ask for research, and weren't moved to a different subject, plus any card asking the same
        search. Returns the cards that let findings go because their subject changed. A finding left with no card
        is kept for the record but no longer counts, so a deleted card's findings never reach the writing, and
        a later card that reuses its id doesn't inherit them."""
        cards = {c["id"]: c for c in (self.campaign.plan or {}).get("assets", [])}
        asking = {i for i, c in cards.items() if c.get("research_query", "").strip()}
        relinked, moved = [], set()
        for finding in self.campaign.research:
            same_search = {i for i, c in cards.items() if _key(c.get("research_query", "")) == _key(finding["query"])}
            ids = []
            for i in finding["asset_ids"]:
                if i in asking and (i not in research_changed or i in same_search):
                    ids.append(i)
                elif i in research_changed and not finding["removed"]:
                    moved.add(i)
            ids += [i for i in sorted(same_search) if i not in ids]
            relinked.append({**finding, "asset_ids": ids})
        self.campaign.research = relinked
        return moved

    def _set_removed(self, finding_id: str, removed: bool) -> None:
        self.campaign.research = [{**f, "removed": removed} if f["id"] == finding_id else f
                                  for f in self._known(finding_id)]

    def _run_all(self, jobs: list[tuple[str, list[str], frozenset[str]]]) -> list[Search]:
        """Searches at the same time when they can, so planning waits for the slowest one, not the sum."""
        if self.runtime is None or len(jobs) == 1:
            return [self._search(*job) for job in jobs]
        # The threads get plain values only, never the campaign itself, which belongs to this request's session.
        chat_id, brand_id, runtime = self.campaign.chat_id, self.campaign.brand_id, self.runtime

        def in_own_session(job: tuple[str, list[str], frozenset[str]]) -> Search:
            with runtime.sessions() as session:
                return self._search(*job, ai=runtime.ai(session), chat_id=chat_id, brand_id=brand_id)

        with ThreadPoolExecutor(max_workers=PARALLEL_SEARCHES) as pool:
            return list(pool.map(in_own_session, jobs))

    def _search(self, query: str, asset_ids: list[str], skip: frozenset[str], ai: AiService | None = None,
                chat_id: int | None = None, brand_id: int | None = None) -> Search:
        """Never raises: a research problem must not break planning or editing."""
        try:
            found = research(ai or self.ai, self.web, query, self.brand_name,
                             chat_id=self.campaign.chat_id if chat_id is None else chat_id,
                             brand_id=self.campaign.brand_id if brand_id is None else brand_id,
                             skip_urls=skip, off_limits=self.off_limits)
        except Exception as error:
            log.warning("Web research for %r failed: %s", query, error)
            return Search([], str(error) or type(error).__name__)
        return Search([_finding(f, query, asset_ids) for f in found])

    def _known(self, finding_id: str) -> list[dict[str, Any]]:
        if not any(f["id"] == finding_id for f in self.campaign.research):
            raise UnknownFinding("No such research finding.")
        return self.campaign.research


def _finding(found: Finding, query: str, asset_ids: list[str]) -> dict[str, Any]:
    return {"id": f"r{uuid4().hex[:8]}", "query": query, "asset_ids": list(asset_ids), "finding": found.finding,
            "quote": found.quote, "url": found.url, "title": found.title, "date": found.date or "date unknown",
            "removed": False}


def approved(campaign: Campaign, asset_id: str | None = None) -> list[dict[str, Any]]:
    """Findings the marketer kept that a plan card still uses, optionally only those for one asset."""
    return [f for f in campaign.research
            if not f["removed"] and f["asset_ids"] and (asset_id is None or asset_id in f["asset_ids"])]


def _key(query: str) -> str:
    return " ".join(query.lower().split())


def _count(n: int) -> str:
    return "no usable findings" if n == 0 else f"{n} finding{'s' if n != 1 else ''}"
