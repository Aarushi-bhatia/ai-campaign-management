"""The campaign agent's thinking steps: reviewing the brief, planning, and editing the plan.

Every step uses the large model with the brand lookup tools. Whatever the model returns is checked:
quotes given as proof must be in the named document, and plans only use allowed asset types.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompt import Prompt, Turn
from app.ai.service import AiService
from app.brand.evidence import Document, normalize
from app.brand.models import Brand, BrandFile, Conflict, Fact
from app.brand.settle import conflict_target, side_of_files, winning_fact_ids
from app.campaign import prompts
from app.campaign.brand_tools import CHANNEL_WORDS, BrandTools
from app.campaign.models import Campaign
from app.config import ModelSize
from app.memory.service import core_texts

MAX_OPTIONS = 4


@dataclass
class Review:
    questions: list[dict[str, Any]]
    brief_rules: list[str]
    assumptions: list[str]


@dataclass
class Edit:
    reply: str
    plan: dict[str, Any] | None = None
    ask: dict[str, Any] | None = None
    research_changed: frozenset[str] = frozenset()
    """Ids of the cards whose research the message moved to a different subject, as the model judged it."""


@dataclass
class CampaignAgent:
    session: Session
    ai: AiService
    brand: Brand
    campaign: Campaign
    tools: BrandTools = field(init=False)
    last_call_id: int | None = field(default=None, init=False)
    """The final call of the latest step, for "View prompt"."""
    last_output: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.tools = BrandTools(self.session, self.ai, self.brand, self.campaign.chat_id)

    def review_brief(self) -> Review:
        reply = self._ask("Brief review", prompts.REVIEW_TASK, prompts.REVIEW_SCHEMA)
        questions = [self._checked_question(q) for q in reply["questions"][: prompts.MAX_QUESTIONS]]
        return Review(
            [q for q in questions if q], _clean(reply["brief_rules"]), _clean(reply["assumptions"])[: prompts.MAX_ASSUMPTIONS]
        )

    def make_plan(self, history: str = "") -> tuple[dict[str, Any], list[str]]:
        """Campaign history is only ever given here, at planning."""
        task = prompts.PLAN_TASK.format(channels=", ".join(self.channels_in_use()),
                                        history=prompts.HISTORY_NOTE.format(records=history) if history else "")
        reply = self._ask("Campaign plan", task, prompts.PLAN_SCHEMA)
        plan = {**self._checked_plan(reply["summary"], reply["assets"]),
                "image_exclusions": self._checked_exclusions(reply["image_exclusions"])}
        return plan, _clean(reply["assumptions"])[: prompts.MAX_ASSUMPTIONS]

    def edit_plan(self, message: str) -> Edit:
        task = f"{prompts.EDIT_TASK}\n\n=== CURRENT PLAN ===\n{prompts.plan_text(self.campaign.plan or {})}\n\n" \
               f"=== MESSAGE ===\n{message}"
        reply = self._ask("Plan edit", task, prompts.EDIT_SCHEMA)
        if reply["ask"]["question"].strip():
            options = _options(reply["ask"]["options"])
            return Edit(reply["reply"].strip(), ask={"kind": "unclear", "question": reply["ask"]["question"].strip(),
                                                      "why": "", "source_path": "", "quote": "", "options": options})
        if reply["change"]:
            current = {card["id"] for card in (self.campaign.plan or {}).get("assets", [])}
            changed = frozenset(a["id"].strip() for a in reply["plan"]["assets"]
                                if a.get("research_changed") and a["id"].strip() in current)
            cards = [{k: v for k, v in a.items() if k != "research_changed"} for a in reply["plan"]["assets"]]
            # The image exclusions stay as they are: a chat edit asked to return them stalled the model (most
            # replies timed out). They are lifted with Allow on the plan.
            plan = {**self._checked_plan(reply["plan"]["summary"], cards, keep=current),
                    "image_exclusions": (self.campaign.plan or {}).get("image_exclusions", [])}
            return Edit(reply["reply"].strip(), plan=plan, research_changed=changed)
        return Edit(reply["reply"].strip())

    def channels_in_use(self) -> list[str]:
        """Campaign channels the brand's current documents mention. All of them when none are mentioned."""
        return channels_mentioned(" ".join(
            f"{d.path} {' '.join((d.card or {}).get('rules_on', []))} {' '.join((d.card or {}).get('mentions', {}).get('channels', []))}"
            for d in self._documents() if d.status == "current"
        ))

    def conflict_notes(self, output: str) -> list[str]:
        """One line for each settled conflict whose winning facts show up in what the agent wrote.

        The tools hand the agent many facts; only a conflict it actually relied on is worth a note.
        Each conflict is noted once per campaign.
        """
        fresh = sorted(self.tools.conflicts_seen - set(self.campaign.noted_conflicts))
        if not fresh:
            return []
        written = normalize(output)
        notes, used = [], []
        paths = {d.id: d.path for d in self._documents()}
        for conflict in self.session.scalars(select(Conflict).where(Conflict.id.in_(fresh))):
            if conflict.winner_file_id is None:
                continue
            facts = {f.id: f for f in self.session.scalars(select(Fact).where(Fact.id.in_(conflict.fact_ids)))}
            winning = [facts[i] for i in winning_fact_ids(conflict, facts)]
            if not any(_appears(fact.value, written) for fact in winning):
                continue
            sides = side_of_files(conflict, facts)
            winning_side = sides.get(conflict.winner_file_id)
            losers = sorted({paths[file_id] for file_id, side in sides.items() if side != winning_side})
            notes.append(_note(conflict, paths[conflict.winner_file_id], losers))
            used.append(conflict.id)
        self.campaign.noted_conflicts = [*self.campaign.noted_conflicts, *used]
        return notes

    def _ask(self, step: str, task: str, schema) -> dict[str, Any]:
        prompt = Prompt(
            fixed=prompts.fixed_part(self.brand.name, self.brand.summary, core_texts(self.session, self.brand.id)),
            campaign=prompts.campaign_part(self.campaign),
            task=[Turn(role="user", content=task)],
        )
        reply = self.ai.complete_with_tools(
            step=step, size=ModelSize.LARGE, prompt=prompt, tools=self.tools.tools(), output_schema=schema,
            chat_id=self.campaign.chat_id, brand_id=self.brand.id, cache_key=f"brand-{self.brand.id}",
        )
        self.last_call_id = reply.call_id
        self.last_output = reply.text
        return json.loads(reply.text)

    def _checked_question(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Keeps the proof only when the quote is in the named document; ties conflict questions to the conflict."""
        question = raw["question"].strip()
        if not question:
            return None
        checked = {"kind": raw["kind"], "question": question, "why": raw["why"].strip(), "source_path": "", "quote": "",
                   "options": _options(raw["options"], follow_brief=raw["kind"] == "clash")}
        doc = self._document(raw["source_path"])
        if doc and raw["quote"].strip() and Document(doc.text or "").contains(raw["quote"]):
            checked["source_path"], checked["quote"] = doc.path, raw["quote"].strip()
        if raw["kind"] == "conflict":
            checked.update(self._conflict_options(raw["conflict_id"]))
        return checked

    def _conflict_options(self, conflict_id: int) -> dict[str, Any]:
        """For an unsettled conflict, one option per side; picking one settles it for the brand.

        The conflict must match exactly: this brand's, still unsettled, and one the agent looked up in
        this step. Anything else stays an ordinary question, so an answer can never settle the wrong
        conflict.
        """
        if conflict_id not in self.tools.conflicts_seen:
            return {}
        conflict = self.session.get(Conflict, conflict_id)
        if conflict is None or conflict.brand_id != self.brand.id or conflict.winner_file_id is not None \
                or conflict.rule == "not_counting":
            return {}
        facts = {f.id: f for f in self.session.scalars(select(Fact).where(Fact.id.in_(conflict.fact_ids)))}
        paths = {d.id: d.path for d in self._documents()}
        options = []
        for side in conflict.sides:
            files = [facts[i].file_id for i in side["fact_ids"] if i in facts]
            if files:
                options.append({"label": side["position"], "value": paths[files[0]]})
        doc_paths = sorted({paths[f.file_id] for f in facts.values() if f.file_id in paths})
        return {"options": options[:MAX_OPTIONS], "conflict_target": conflict_target(conflict, facts, doc_paths)}

    def _checked_plan(self, summary: str, assets: list[dict[str, Any]], keep: set[str] | None = None) -> dict[str, Any]:
        """Allowed asset types and channels only, each with a unique id.

        On an edit, `keep` holds the current cards' ids: a card keeps its id only when it is one of them. Every
        other card is new and gets an id this campaign has never used, so it can't inherit a deleted card's
        findings, even when one edit drops a card and adds another in its place."""
        channels = set(self.channels_in_use())
        kept, taken = [], used_card_ids(self.campaign)
        for asset in assets:
            if prompts.CHANNEL_OF[asset["type"]] not in channels:
                continue
            asset_id = asset["id"].strip()
            reusable = asset_id in keep if keep is not None else bool(asset_id)
            if not reusable or asset_id in {c["id"] for c in kept}:
                asset_id = new_card_id(taken)
            taken.add(asset_id)
            kept.append({**{k: str(v).strip() for k, v in asset.items()}, "id": asset_id})
        return {"summary": summary.strip(), "assets": kept}

    def _checked_exclusions(self, raw: list[dict[str, str]]) -> list[dict[str, str]]:
        """Image types the campaign keeps off, each only when its quote is really in the brief or an answer: a hard
        block on images, so a misread one must not hide images unseen. Shown on the plan."""
        source = Document("\n".join([self.campaign.brief, *(q.get("answer") or "" for q in self.campaign.questions)]))
        kept: dict[str, dict[str, str]] = {}
        for item in raw:
            quote = item["quote"].strip()
            if source.contains(quote):
                kept.setdefault(item["image_type"], {"image_type": item["image_type"], "quote": quote})
        return list(kept.values())

    def _document(self, path: str) -> BrandFile | None:
        """A current document, for a quote given as proof: a replaced or archived one proves nothing now."""
        path = path.strip().lstrip("/")
        return next((d for d in self._documents()
                     if d.status == "current" and path and (d.path == path or d.path.endswith(path))), None)

    def _documents(self) -> list[BrandFile]:
        return list(self.session.scalars(
            select(BrandFile).where(BrandFile.brand_id == self.brand.id, BrandFile.kind == "document")
        ))


RULE_PHRASES = {
    "replaces": "it replaced {other}",
    "owner": "it is the document that sets this",
    "approved": "{other} {is} only a draft",
    "newer": "it is newer",
    "live": "{other} {is} archived",
    "you": "you chose it",
    "only_side_left": "{other} {is} no longer a type of document whose facts count",
}


def _note(conflict: Conflict, winner: str, losers: list[str]) -> str:
    """For example: On product naming, I'm following naming.md rather than old-guide.md, because it is newer."""
    many = len(losers) > 1
    reason = RULE_PHRASES.get(conflict.rule, "")
    reason = reason.format(other="the others" if many else "the other", **{"is": "are" if many else "is"}) if reason \
        else conflict.reason.strip().rstrip(".") or "it is the more reliable source"
    return (f"On {conflict.topic or 'this point'}, I'm following {_file_name(winner)} rather than "
            f"{_and_list([_file_name(p) for p in losers])}, because {reason}.")


def _and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _file_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _appears(value: str, written: str) -> bool:
    """True when a fact's value shows up in the agent's output. Very short values are too common to count."""
    value = normalize(value)
    return len(value) >= 4 and value in written


def channels_mentioned(text: str) -> list[str]:
    """The channels named in the text, as whole words: "x" in "context.md" is not the X channel, but "x" in
    "channels/x-playbook.md" is. All of them when none is named."""
    text = text.lower()
    used = [c for c, words in CHANNEL_WORDS.items()
            if any(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) for w in (*words, c.replace("_", " ")))]
    return used or list(CHANNEL_WORDS)


def plan_problem(cards: list[dict[str, Any]], channels: list[str]) -> str | None:
    """What is wrong with a plan's cards, or None. The same rules for every way a plan is saved or approved:
    at least one card, each id once, only allowed asset types, only channels the brand uses."""
    if not cards:
        return "A plan needs at least one asset."
    ids = [card.get("id") for card in cards]
    if len(set(ids)) != len(ids):
        return "Each plan card can appear only once."
    for card in cards:
        if card.get("type") not in prompts.CHANNEL_OF:
            return f"“{card.get('title', '')}” has an asset type the app can't write."
        if prompts.CHANNEL_OF[card["type"]] not in channels:
            return (f"The brand's documents don't cover the {prompts.CHANNEL_OF[card['type']].replace('_', ' ')} "
                    f"channel, so “{card.get('title', '')}” can't be planned.")
    return None


FOLLOW_BRIEF = "Follow the brief as written"


def used_card_ids(campaign) -> set[str]:
    """Every plan card id this campaign has had: current and removed cards, written assets and research."""
    plan = campaign.plan or {}
    return ({c["id"] for c in [*plan.get("assets", []), *plan.get("removed", [])]}
            | {a.plan_id for a in campaign.assets} | {i for f in campaign.research for i in f["asset_ids"]})


def new_card_id(taken: set[str]) -> str:
    """The next "aN" id above any used so far, never one used before."""
    numbers = [int(i[1:]) for i in taken if i[:1] == "a" and i[1:].isdigit()]
    return f"a{max(numbers, default=0) + 1}"


def _options(raw: list[str], follow_brief: bool = False) -> list[dict[str, str]]:
    """A clash pits the brief against the brand, so following the brief is always one of the choices; the
    marketer decides, rather than picking between two ways of overruling their own brief."""
    labels = [label.strip() for label in raw if label.strip()][:MAX_OPTIONS]
    if follow_brief and not any("brief" in label.lower() for label in labels):
        labels = [*labels[: MAX_OPTIONS - 1], FOLLOW_BRIEF]
    return [{"label": label, "value": label} for label in at_least_two(labels)]


def at_least_two(labels: list[str]) -> list[str]:
    """A question card always offers a real choice: two options at least, never the same one twice."""
    labels = list(dict.fromkeys(labels))
    for fallback in ("You decide", "Leave it as it is"):
        if len(labels) < 2 and fallback not in labels:
            labels.append(fallback)
    return labels


def _clean(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]
