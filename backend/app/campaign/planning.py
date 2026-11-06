"""The plan part of a campaign chat: reviewing the brief, planning, changing the plan by chat or on its cards,
its research, and approving it, which starts the writing."""

import re
from typing import Any

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.ai.service import AiService
from app.brand.service import BadCorrection, save_correction
from app.campaign import stages
from app.campaign.agent import plan_problem
from app.campaign.conversation import Conversation
from app.campaign.errors import BadPlan, PlanChanged
from app.campaign.models import Asset, Campaign
from app.campaign.prompts import ASSET_TYPES
from app.campaign.remembering import Remembering
from app.campaign.research import approved
from app.campaign.runtime import Runtime
from app.campaign.writing.queue import write_campaign
from app.chat.models import Chat, Message
from app.db import utc_now
from app.memory.service import core, history_text

PLAN_FIELDS = ("id", "type", "title", "audience", "main_message", "date", "image_idea", "notes", "research_query",
               "draft_for")

OVERRIDE = "override"


def override_question(rule: str) -> dict[str, Any]:
    """Asks before the brief beats a brand rule. The rule is in the question itself, so the answer reads on its
    own wherever answers are shown to the model."""
    return {"kind": "clash", "question": f"Your brief would change a brand rule: {rule.rstrip('.')}. Allow that for "
            "this campaign?", "why": "", "source_path": "", "quote": "", "conflict_id": 0, "brief_rule": rule,
            "options": [{"label": "No, keep the brand rule", "value": "keep"},
                        {"label": "Yes, for this campaign only", "value": OVERRIDE}],
            "answer": None, "stage": stages.ASKING}


_YES = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "allow", "override"}
_NO = {"no", "n", "nope", "keep", "don't", "dont", "never"}
_AGAINST_YES = {"no", "not", "don't", "dont", "keep", "never"}


def override_choice(text: str) -> str | None:
    """A typed answer to an override question, read as one of its options: OVERRIDE for a plain yes, "keep" for a
    plain no, None when it is neither or both ("yes, keep the rule"), so it is asked again rather than guessed."""
    words = re.findall(r"[a-z']+", text.lower().replace("’", "'"))
    if not words:
        return None
    if words[0] in _YES and not _AGAINST_YES & set(words):
        return OVERRIDE
    if words[0] in _NO:
        return "keep"
    return None


class Planning(Conversation):
    def __init__(self, session: Session, ai: AiService, runtime: Runtime | None, remembering: Remembering) -> None:
        super().__init__(session, ai, runtime)
        self._remembering = remembering

    def update_plan(self, chat: Chat, assets: list[dict[str, Any]], base: int | None = None,
                    image_exclusions: list[str] | None = None, brief_rules: list[str] | None = None) -> Campaign:
        """Changes made on the plan cards: delete, reorder, edit a field, remove an image exclusion or a campaign
        rule. No AI. The
        cards send the whole list, so `base` is the plan version they show: if the plan has moved on since (a chat
        edit added a card, say), saving would undo that, so nothing is saved."""
        campaign = self._locked(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="change the plan")
        if base is not None and base != campaign.plan_version:
            raise PlanChanged("Someone changed the plan (in another tab or in the chat), so your change wasn't saved. "
                              "You're now seeing the latest plan. Make your change again.")
        known = {asset["id"]: asset for asset in campaign.plan["assets"]}
        checked = []
        for asset in assets:
            if asset.get("id") not in known or asset.get("type") not in ASSET_TYPES:
                raise BadPlan("Plan cards can be edited, reordered or removed here; add new assets in the chat.")
            checked.append({key: str(asset.get(key, known[asset["id"]].get(key, ""))) for key in PLAN_FIELDS})
        problem = plan_problem(checked, self._agent(campaign).channels_in_use())
        if problem:
            raise BadPlan(problem)
        kept = {}
        if image_exclusions is not None and "image_exclusions" in campaign.plan:
            kept = {"image_exclusions": [e for e in campaign.plan["image_exclusions"]
                                         if e["image_type"] in image_exclusions]}
        if brief_rules is not None:
            campaign.brief_rules = [r for r in campaign.brief_rules if r in brief_rules]
        campaign.plan = {**campaign.plan, "assets": checked, **kept}
        campaign.plan_version += 1
        self._research(campaign).relink()  # a deleted card's findings stop counting
        self._session.commit()
        return campaign

    def approve(self, chat: Chat, base: int | None = None) -> list[Message]:
        """Locks the plan and its research, then starts writing every asset in the background. `base` is the plan
        version the marketer saw: a plan or research that changed since then isn't approved unseen."""
        campaign = self.get(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="approve the plan")
        allowed = Campaign.stage == stages.PLAN_READY
        if base is not None:
            if base != campaign.plan_version:
                raise PlanChanged("The plan changed since you last saw it, so it wasn't approved. Look at the latest "
                                  "plan, then approve it.")
            allowed &= Campaign.plan_version == base
        problem = plan_problem((campaign.plan or {}).get("assets", []), self._agent(campaign).channels_in_use())
        if problem:
            raise BadPlan(f"This plan can't be approved: {problem}")
        self._claim_stage(campaign, allowed, stages.APPROVED, approved_at=utc_now())
        self._expire_open_questions(chat, campaign)
        campaign.assets = [
            Asset(plan_id=card["id"], position=i, type=card["type"], title=card["title"])
            for i, card in enumerate(campaign.plan["assets"])
        ]
        kept = len(approved(campaign))
        research = f" with {kept} research finding{'s' if kept != 1 else ''}" if kept else ""
        note = self._post(chat, "assistant", "note",
                          f"Plan approved{research}. " + (f"Writing {len(campaign.assets)} assets, a few at a time."
                                                          if len(campaign.assets) > 1 else "Writing it now."))
        self.begin_writing(chat)
        return [note]

    def begin_writing(self, chat: Chat) -> Campaign:
        """Writes the assets not yet done. After a failure, it writes just the ones that failed."""
        campaign = self.get(chat)
        failed = any(a.state == "failed" for a in campaign.assets)
        if not (campaign.stage == stages.APPROVED or (campaign.stage == stages.DONE and failed)):
            stages.require(campaign.stage, stages.APPROVED, action="start writing")
        failed_asset = exists().where(Asset.campaign_id == Campaign.id, Asset.state == "failed")
        self._claim_stage(campaign,
                          (Campaign.stage == stages.APPROVED) | ((Campaign.stage == stages.DONE) & failed_asset),
                          stages.WRITING)
        for asset in campaign.assets:
            if asset.state == "failed":
                asset.state, asset.error = "waiting", None
        self._session.commit()
        runtime = self._runtime
        if runtime is not None:
            runtime.jobs.submit(lambda: write_campaign(runtime, campaign.id))
        return campaign

    def remove_finding(self, chat: Chat, finding_id: str) -> Campaign:
        campaign = self._locked(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="change the research")
        self._research(campaign).remove(finding_id)
        campaign.plan_version += 1
        self._session.commit()
        return campaign

    def retry_research(self, chat: Chat) -> list[Message]:
        """The Try again button on a plan card whose search failed: runs the plan's searches that haven't run."""
        campaign = self.get(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="search again")
        return self._guarded_step(chat, campaign, lambda: [
            self._post(chat, "assistant", "note", line)
            for line in self._research(campaign).for_plan() or ["Nothing left to search for."]])

    def bring_back_finding(self, chat: Chat, finding_id: str) -> Campaign:
        campaign = self._locked(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="change the research")
        self._research(campaign).bring_back(finding_id)
        campaign.plan_version += 1
        self._session.commit()
        return campaign

    def better_source(self, chat: Chat, finding_id: str) -> list[Message]:
        campaign = self.get(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="change the research")
        return self._guarded_step(chat, campaign, lambda: [
            self._post(chat, "assistant", "note", self._research(campaign).better_source(finding_id))])

    def review(self, chat: Chat, campaign: Campaign, brief: str) -> list[Message]:
        campaign.brief = brief
        remembered = core(self._session, campaign.brand_id)
        agent = self._agent(campaign)
        review = agent.review_brief()
        new = self._remembering.memories_used(chat, campaign, remembered)
        # A point where the brief would beat a brand rule is never decided for the marketer: it becomes a
        # question, with keeping the brand's rule first, and only a yes makes it a rule for this campaign.
        campaign.questions = [{**q, "answer": None, "stage": stages.ASKING} for q in review.questions] + [
            override_question(rule) for rule in review.brief_rules]
        campaign.brief_rules, campaign.assumptions = [], review.assumptions
        new += self._notes(chat, agent)
        if campaign.questions:
            campaign.stage = stages.ASKING
            count = len(campaign.questions)
            new.append(self._post(chat, "assistant", "text",
                                  f"Before I plan, I need {count} answer{'s' if count > 1 else ''}. One at a time:",
                                  call_id=agent.last_call_id))
            return new + [self._question_card(chat, campaign, 0)]
        return new + self.plan(chat, campaign)

    def plan(self, chat: Chat, campaign: Campaign) -> list[Message]:
        agent = self._agent(campaign)
        plan, assumptions = agent.make_plan(history_text(self._session, campaign.brand_id, skip_campaign=campaign.id))
        campaign.plan, campaign.plan_version = plan, campaign.plan_version + 1
        campaign.assumptions = list(dict.fromkeys([*campaign.assumptions, *assumptions]))
        campaign.stage = stages.PLAN_READY
        new = self._notes(chat, agent)
        new += [self._post(chat, "assistant", "note", line) for line in self._research(campaign).for_plan()]
        new.append(self._post(chat, "assistant", "plan", plan["summary"],
                              {"version": campaign.plan_version, "assets": len(plan["assets"])},
                              call_id=agent.last_call_id))
        return new

    def edit(self, chat: Chat, campaign: Campaign, message: str) -> list[Message]:
        agent = self._agent(campaign)
        edit = agent.edit_plan(message)
        new = self._notes(chat, agent)
        if edit.ask:
            campaign.questions = [*campaign.questions, {**edit.ask, "answer": None, "stage": stages.PLAN_READY}]
            if edit.reply:
                new.append(self._post(chat, "assistant", "text", edit.reply, call_id=agent.last_call_id))
            return new + [self._question_card(chat, campaign, len(campaign.questions) - 1)]
        if edit.plan:
            campaign.plan, campaign.plan_version = edit.plan, campaign.plan_version + 1
            new += [self._post(chat, "assistant", "note", line)
                    for line in self._research(campaign).for_plan(edit.research_changed)]
            return new + [self._post(chat, "assistant", "plan", edit.reply,
                                     {"version": campaign.plan_version, "assets": len(edit.plan["assets"])},
                                     call_id=agent.last_call_id)]
        return new + [self._post(chat, "assistant", "text", edit.reply, call_id=agent.last_call_id)]

    def settle_conflict(self, chat: Chat, campaign: Campaign, target: str, path: str) -> list[Message]:
        """An answer to a conflict question becomes a brand decision, so it isn't asked again. It is not also kept
        as a memory item: the decision is the one place it lives (shown and undone on the Brand page, applied by
        the conflict rules), and a copy in memory would go stale when the conflict is decided again."""
        try:
            save_correction(self._session, campaign.brand_id, "conflict_winner", target, path)
        except BadCorrection:
            return []
        return [self._post(chat, "assistant", "note", f"Saved for the brand: {path} wins this conflict from now on.")]

    def _expire_open_questions(self, chat: Chat, campaign: Campaign) -> None:
        """Questions still open when the plan is approved were about the plan, so they no longer apply; their
        cards say so."""
        if not any(not q.get("answer") for q in campaign.questions):
            return
        campaign.questions = [q if q.get("answer") else {**q, "expired": True} for q in campaign.questions]
        for message in chat.messages:
            if message.kind == "question" and not (message.data or {}).get("answer"):
                message.data = {**message.data, "expired": True}
