"""Runs a campaign chat: each user message or answer moves the campaign along its stages."""

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import exists, func, inspect, select, update
from sqlalchemy.orm import Session

from app.ai.models import AiCall
from app.ai.service import AiCallFailed, AiService
from app.brand.models import Brand, Entity
from app.brand.service import BadCorrection, save_correction
from app.campaign import editing, stages, writer
from app.campaign.agent import CampaignAgent, at_least_two, new_card_id, plan_problem, used_card_ids
from app.campaign.assets import AssetChanged, AssetWork, EmptyEdit
from app.campaign.models import Asset, Campaign
from app.campaign.prompts import ASSET_TYPES, CHANNEL_OF
from app.campaign.research import CampaignResearch, approved
from app.campaign.runtime import Runtime
from app.campaign.writing import full_note, memory_notes, remembered_note, write_campaign
from app.chat.models import Chat, Message
from app.config import ModelSize
from app.db import utc_now
from app.memory.service import Memory, MemoryFull, core, history_text

PLAN_FIELDS = ("id", "type", "title", "audience", "main_message", "date", "image_idea", "notes", "research_query",
               "draft_for")


class NoBrand(Exception):
    pass


class UnknownQuestion(ValueError):
    pass


class BadPlan(ValueError):
    pass


class UnknownAsset(ValueError):
    pass


class BadContent(ValueError):
    """Typed-in asset content of the wrong shape (a list where text goes, say)."""


class QuestionExpired(stages.WrongStage):
    """The question was asked at an earlier stage (before the plan was approved, say), so it no longer applies."""


class PlanChanged(stages.WrongStage):
    """The plan or its research changed since this was started (or since the user last saw it)."""


PLAN_CHANGED = ("The plan changed while I was working on this: it was approved, or changed somewhere else. So I "
                "left it as it is, and nothing from this step was kept. The plan shown now is the latest.")


def _expired(question: dict[str, Any], stage: str) -> bool:
    """A question only applies at the stage it was asked at. One from before questions recorded their stage, still
    open once the assets are written, was about the plan (only questions about assets carry "about")."""
    asked = question.get("stage") or (None if "about" in question or stage != stages.DONE else stages.PLAN_READY)
    return bool(question.get("expired")) or (asked is not None and asked != stage)


def _usd(amount: float) -> str:
    return f"${amount:.4f}" if amount < 0.01 else f"${amount:.2f}"


def _and_quoted(items: list[str]) -> str:
    quoted = [f"“{item}”" for item in items]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


class CampaignService:
    def __init__(self, session: Session, ai: AiService, runtime: Runtime | None = None) -> None:
        self._session = session
        self._ai = ai
        self._runtime = runtime

    def start(self, chat: Chat, brand_id: int | None = None) -> Campaign:
        """A campaign for the brand chosen in the sidebar, or the most recently read one."""
        query = select(Brand).where(Brand.status == "ready").order_by(Brand.id.desc())
        if brand_id is not None:
            query = query.where(Brand.id == brand_id)
        brand = self._session.scalars(query).first()
        if brand is None:
            raise NoBrand("That brand isn't ready yet." if brand_id is not None else "Add a brand before starting a campaign.")
        campaign = Campaign(chat_id=chat.id, brand_id=brand.id)
        self._session.add(campaign)
        self._session.commit()
        return campaign

    def get(self, chat: Chat) -> Campaign:
        """The chat's campaign. Chats from before campaigns existed get one when first opened."""
        campaign = self._session.scalars(select(Campaign).where(Campaign.chat_id == chat.id)).first()
        return campaign or self.start(chat)

    def on_message(self, chat: Chat, text: str) -> list[Message]:
        """The user's message, then whatever the campaign's stage calls for."""
        campaign = self.get(chat)
        self._post(chat, "user", "text", text)
        self._session.commit()  # the message is kept even when the step after it fails
        if campaign.stage == stages.BRIEF:
            return self._guarded_step(chat, campaign, lambda: self._review(chat, campaign, text))
        if campaign.stage == stages.ASKING:
            if self._next_open(campaign) is None:
                # Every question is answered but planning didn't finish (it failed): plan again.
                return self._guarded_step(chat, campaign, lambda: self._plan(chat, campaign))
            return self.answer(chat, self._current_question(campaign), text, typed=True)
        if campaign.stage == stages.PLAN_READY:
            return (self._guarded_step(chat, campaign, lambda: self._edit(chat, campaign, text))
                    + self._step(lambda: self._remember(chat, campaign)))
        if campaign.stage == stages.DONE:
            return (self._step(lambda: self._edit_assets(chat, campaign, text))
                    + self._step(lambda: self._remember(chat, campaign)))
        return self._step(lambda: [self._post(chat, "assistant", "note",
                                              "The assets are being written. Changes can be asked for once they're done.")])

    def answer(self, chat: Chat, question_id: int, answer: str, typed: bool = False) -> list[Message]:
        """Records an answer to a question card, then asks the next question or moves on."""
        campaign = self.get(chat)
        # Locked, then read again, until the answer is saved: a second answer to the same card, sent at the same
        # moment, waits here and then finds the card answered, so it can't plan a second time.
        self._session.refresh(campaign, with_for_update=True)
        stages.require(campaign.stage, stages.ASKING, stages.PLAN_READY, stages.DONE, action="answer a question")
        if not 0 <= question_id < len(campaign.questions) or campaign.questions[question_id].get("answer"):
            raise UnknownQuestion("That question isn't open.")
        question = dict(campaign.questions[question_id])
        if _expired(question, campaign.stage):
            raise QuestionExpired("That question was asked before the plan was approved, so it no longer applies. "
                                  "Ask for the change in the chat instead.")
        option = next((o for o in question["options"] if answer in (o["value"], o["label"])), None)
        question["answer"] = option["label"] if option else answer
        campaign.questions = [*campaign.questions[:question_id], question, *campaign.questions[question_id + 1:]]
        if not typed:
            self._post(chat, "user", "text", question["answer"])
        self._mark_card_answered(chat, question_id, question["answer"])
        new = []
        if question.get("conflict_target") and option:
            new += self._settle_conflict(chat, campaign, question["conflict_target"], option["value"])
        self._session.commit()  # the answer is kept even when the step after it fails
        if campaign.stage == stages.PLAN_READY:
            return new + self._guarded_step(chat, campaign,
                                            lambda: self._edit(chat, campaign, f"{question['question']} {question['answer']}"))
        if campaign.stage == stages.DONE:
            return new + self._step(lambda: self._edit_assets(
                chat, campaign, f"{question.get('about', '')} {question['question']} {question['answer']}".strip()))
        nxt = self._next_open(campaign)
        if nxt is not None:
            return new + self._step(lambda: [self._question_card(chat, campaign, nxt)])
        return new + self._guarded_step(chat, campaign, lambda: self._plan(chat, campaign))

    def retry_review(self, chat: Chat) -> list[Message]:
        """The Try again button after a brief review failed: reviews the brief that was sent, which is still the
        last message, so the marketer doesn't have to type "try again" (that would become the brief)."""
        campaign = self.get(chat)
        stages.require(campaign.stage, stages.BRIEF, action="review the brief again")
        last = chat.messages[-1] if chat.messages else None
        if last is None or last.role != "user":
            raise UnknownQuestion("There is no brief waiting to be reviewed; paste it in the chat.")
        return self._guarded_step(chat, campaign, lambda: self._review(chat, campaign, last.content))

    def update_plan(self, chat: Chat, assets: list[dict[str, Any]], base: int | None = None) -> Campaign:
        """Changes made on the plan cards: delete, reorder, edit a field. No AI. The cards send the whole list, so
        `base` is the plan version they show: if the plan has moved on since (a chat edit added a card, say),
        saving would undo that, so nothing is saved."""
        campaign = self._locked(chat)
        stages.require(campaign.stage, stages.PLAN_READY, action="change the plan")
        if base is not None and base != campaign.plan_version:
            raise PlanChanged("The plan changed since these cards were shown (by a chat edit, say), so this card change "
                              "wasn't saved. The latest plan is shown now; make the change again.")
        known = {asset["id"]: asset for asset in campaign.plan["assets"]}
        checked = []
        for asset in assets:
            if asset.get("id") not in known or asset.get("type") not in ASSET_TYPES:
                raise BadPlan("Plan cards can be edited, reordered or removed here; add new assets in the chat.")
            checked.append({key: str(asset.get(key, known[asset["id"]].get(key, ""))) for key in PLAN_FIELDS})
        problem = plan_problem(checked, self._agent(campaign).channels_in_use())
        if problem:
            raise BadPlan(problem)
        campaign.plan = {**campaign.plan, "assets": checked}
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
        self._claim_stage(campaign, (Campaign.stage == stages.APPROVED) | ((Campaign.stage == stages.DONE) & failed_asset),
                          stages.WRITING)
        for asset in campaign.assets:
            if asset.state == "failed":
                asset.state, asset.error = "waiting", None
        self._session.commit()
        runtime = self._runtime
        if runtime is not None:
            runtime.jobs.submit(lambda: write_campaign(runtime, campaign.id))
        return campaign

    # Research on the plan

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

    # Assets

    def asset(self, chat: Chat, asset_id: int) -> Asset:
        asset = self._session.get(Asset, asset_id)
        if asset is None or asset.campaign_id != self.get(chat).id:
            raise UnknownAsset("No such asset in this campaign.")
        return asset

    def hand_edit(self, chat: Chat, asset_id: int, content: dict[str, Any],
                  base: int | None = None) -> tuple[Asset, list[Message]]:
        asset = self._ready_asset(chat, asset_id)
        problem = writer.content_problem(asset.type, content)
        if problem:
            raise BadContent(f"Not saved: {problem}")
        _, offer = self._work(self.get(chat)).hand_edit(asset, content, base)
        new = []
        if offer:
            new.append(self._post(chat, "assistant", "remember_offer",
                                  f"You've made this change by hand more than once. Remember it? {offer}", {"text": offer}))
            self._session.commit()
        return asset, new

    def undo(self, chat: Chat, asset_id: int, base: int | None = None) -> Asset:
        asset = self._ready_asset(chat, asset_id)
        self._work(self.get(chat)).undo(asset, base)
        return asset

    def restore(self, chat: Chat, asset_id: int, number: int, base: int | None = None) -> Asset:
        asset = self._ready_asset(chat, asset_id)
        self._work(self.get(chat)).restore(asset, number, base)
        return asset

    def check_again(self, chat: Chat, asset_id: int) -> tuple[Asset, list[Message]]:
        asset = self._ready_asset(chat, asset_id)
        draft = self._work(self.get(chat)).check_again(asset)
        found = f"{len(draft.warnings)} warning{'s' if len(draft.warnings) != 1 else ''}" if draft.warnings else "no problems"
        note = self._post(chat, "assistant", "note", f"Checked “{asset.title}” again: {found}. Cost {_usd(self._cost(draft.call_ids))}.")
        self._session.commit()
        return asset, [note]

    def remember_offer(self, chat: Chat, message_id: int) -> list[Message]:
        """The marketer accepted a "Remember this?" offer."""
        campaign = self.get(chat)
        offer = next((m for m in chat.messages if m.id == message_id and m.kind == "remember_offer"), None)
        if offer is None or (offer.data or {}).get("done"):
            raise UnknownQuestion("That offer isn't open.")
        offer.data = {**offer.data, "done": True}
        return self._add_memory(chat, campaign, offer.data["text"], "preference")

    # Steps

    def _review(self, chat: Chat, campaign: Campaign, brief: str) -> list[Message]:
        campaign.brief = brief
        remembered = core(self._session, campaign.brand_id)
        agent = self._agent(campaign)
        review = agent.review_brief()
        new = self._memories_used(chat, campaign, remembered)
        campaign.questions = [{**q, "answer": None, "stage": stages.ASKING} for q in review.questions]
        campaign.brief_rules, campaign.assumptions = review.brief_rules, review.assumptions
        new += self._notes(chat, agent)
        for rule in campaign.brief_rules:
            new.append(self._post(chat, "assistant", "note", f"For this campaign only, the brief overrides the brand: {rule}"))
        if campaign.questions:
            campaign.stage = stages.ASKING
            count = len(campaign.questions)
            new.append(self._post(chat, "assistant", "text",
                                  f"Before I plan, I need {count} answer{'s' if count > 1 else ''}. One at a time:",
                                  call_id=agent.last_call_id))
            return new + [self._question_card(chat, campaign, 0)]
        return new + self._plan(chat, campaign)

    def _plan(self, chat: Chat, campaign: Campaign) -> list[Message]:
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

    def _edit(self, chat: Chat, campaign: Campaign, message: str) -> list[Message]:
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

    def _settle_conflict(self, chat: Chat, campaign: Campaign, target: str, path: str) -> list[Message]:
        """An answer to a conflict question becomes a brand decision, so it isn't asked again, and a memory."""
        try:
            save_correction(self._session, campaign.brand_id, "conflict_winner", target, path)
        except BadCorrection:
            return []
        new = [self._post(chat, "assistant", "note", f"Saved for the brand: {path} wins this conflict from now on.")]
        topic = target.split("|", 1)[0].replace("_", " ")
        return new + self._add_memory(chat, campaign, f"On {topic}, {path} is the one to follow.", "decision")

    def _add_memory(self, chat: Chat, campaign: Campaign, text: str, kind: str) -> list[Message]:
        """Saves one item and posts its note: what was saved, what made room, or that memory is full."""
        try:
            item = Memory(self._session, self._ai).add(campaign.brand_id, text, kind, chat.id)
        except MemoryFull:
            note = full_note([text])
        else:
            if item is None:
                return []
            note = remembered_note(item)
        chat.messages.append(note)
        self._session.commit()
        return [note]

    def _edit_assets(self, chat: Chat, campaign: Campaign, message: str) -> list[Message]:
        """A chat edit of written assets: only the assets and fields meant are rewritten."""
        assets = [a for a in campaign.live_assets if a.content]
        work = self._work(campaign)
        task = editing.ROUTE_TASK.format(assets=editing.assets_text(assets), message=message)
        reply = self._ai.complete(
            step="Edit request", size=ModelSize.MEDIUM, prompt=writer.prompt(work.fixed_part(), campaign, task),
            output_schema=editing.ROUTE_SCHEMA, chat_id=chat.id, brand_id=campaign.brand_id,
            cache_key=f"brand-{campaign.brand_id}",
        )
        route = editing.route_from(json.loads(reply.text), assets)
        if route.action == "answer":
            return [self._post(chat, "assistant", "text", route.reply, call_id=reply.call_id)]
        if route.action == "add":
            return self._add_assets(chat, campaign, route, reply.call_id)
        if route.action == "remove":
            return self._remove_assets(chat, campaign, route, reply.call_id)
        if route.action == "ask":
            # The model's own questions keep to four choices; "Which asset?" lists every asset, so none is missing.
            options = [o.strip() for o in route.ask["options"] if o.strip()]
            options = at_least_two(options if route.ask.get("every_asset") else options[:4])
            campaign.questions = [*campaign.questions, {
                "kind": "unclear", "question": route.ask["question"], "why": "", "source_path": "", "quote": "",
                "options": [{"label": o, "value": o} for o in options], "about": message, "answer": None,
                "stage": stages.DONE,
            }]
            return [self._question_card(chat, campaign, len(campaign.questions) - 1)]
        new = []
        if route.research_query:
            research = self._research(campaign)
            new += [self._post(chat, "assistant", "note", line)
                    for line in research.on_request(route.research_query, [a.plan_id for a, _ in route.targets])]
        lines, total = [], self._cost([reply.call_id])
        for asset, field_name in route.targets:
            part = f" ({field_name})" if field_name else ""
            try:
                draft = work.edit(asset, route.instruction, field_name)
            except AiCallFailed as failure:
                # The other assets' edits still stand (each saved as it finished), so the reply lists them all.
                cost = self._cost([failure.call_id])
                total += cost
                lines.append(f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”{part}: couldn't be edited ({failure}), "
                             f"so it is as it was. Ask again to retry it ({_usd(cost)}).")
                continue
            except AssetChanged:
                lines.append(f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”{part}: it changed while I was editing it, "
                             "so I left your newer version as it is. Ask again to apply this change to it.")
                continue
            except EmptyEdit as empty:
                cost = self._cost([empty.args[0]])
                total += cost
                lines.append(f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”{part}: the edit would have left it with "
                             f"no text, so I left it as it is ({_usd(cost)}).")
                continue
            cost = self._cost(draft.call_ids)
            total += cost
            warn = f"; {len(draft.warnings)} warning{'s' if len(draft.warnings) > 1 else ''}" if draft.warnings else ""
            if any(w["check"] == "not checked" for w in draft.warnings):
                warn = "; its checks couldn't run, so press Check again on it"
            if not draft.saved:
                lines.append(f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”{part}: not changed, so no new version"
                             f"{f'. {draft.changed}' if draft.changed else ''} ({_usd(cost)})")
                continue
            lines.append(f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”{part}: {draft.changed or 'changed'}"
                         f" ({_usd(cost)}{warn})")
        head = route.reply or "Done."
        body = "\n".join(f"- {line}" for line in lines)
        return new + [self._post(chat, "assistant", "edit", f"{head}\n{body}\nEdit cost: {_usd(total)}.",
                                 {"asset_ids": [a.id for a, _ in route.targets], "cost_usd": total},
                                 call_id=reply.call_id)]

    def _add_assets(self, chat: Chat, campaign: Campaign, route: editing.Route, call_id: int) -> list[Message]:
        """New assets asked for after writing: added to the plan as cards, then only they are written, in the
        background, with the same rules, facts and checks. The assets already written stay as they are."""
        channels = set(self._agent(campaign).channels_in_use())
        cards = [c for c in route.new_assets if CHANNEL_OF[c["type"]] in channels]
        if not cards:
            return [self._post(chat, "assistant", "text", "The brand's documents don't cover that channel, so I didn't "
                               "add it.", call_id=call_id)]
        used = used_card_ids(campaign)
        added = []
        for card in cards:
            card_id = new_card_id(used)
            used.add(card_id)
            added.append({**{key: str(card.get(key, "")).strip() for key in PLAN_FIELDS}, "id": card_id,
                          "research_query": ""})
        self._claim_stage(campaign, Campaign.stage == stages.DONE, stages.WRITING)
        titles = _and_quoted([card["title"] for card in added])
        kinds = {writer.TYPE_LABELS[card["type"]] for card in added}
        what = f"{len(added)} {kinds.pop()}{'s' if len(added) > 1 else ''}" if len(kinds) == 1 else f"{len(added)} assets"
        summary = f"{campaign.plan.get('summary', '').strip()} Added after writing: {what} ({titles}).".strip()
        campaign.plan = {**campaign.plan, "summary": summary, "assets": [*campaign.plan["assets"], *added]}
        campaign.plan_version += 1
        start = len(campaign.assets)
        campaign.assets.extend(Asset(plan_id=card["id"], position=start + i, type=card["type"], title=card["title"])
                               for i, card in enumerate(added))
        self._session.flush()  # the new assets get their ids
        lines ="\n".join(f"- {writer.TYPE_LABELS[card['type']]} “{card['title']}”" for card in added)
        note = self._post(chat, "assistant", "edit",
                          f"{route.reply or 'Adding them now.'}\n{lines}\nWriting {'it' if len(added) == 1 else 'them'} "
                          "now; the assets already written stay as they are.",
                          {"asset_ids": [a.id for a in campaign.assets[start:]]}, call_id=call_id)
        self._session.commit()  # the writer works in its own session, so the new assets must be saved first
        runtime = self._runtime
        if runtime is not None:
            runtime.jobs.submit(lambda: write_campaign(runtime, campaign.id))
        return [note]

    def _remove_assets(self, chat: Chat, campaign: Campaign, route: editing.Route, call_id: int) -> list[Message]:
        """Takes assets out of the campaign, by chat. They are hidden, not deleted: the note in the chat has an
        Undo, and each keeps its versions."""
        removing = [asset for asset, _ in route.targets]
        if len(removing) >= len(campaign.live_assets):
            return [self._post(chat, "assistant", "text", "I can't remove every asset; at least one has to stay.",
                               call_id=call_id)]
        for asset in removing:
            asset.state = "removed"
        self._sync_plan(campaign)
        lines = "\n".join(f"- {writer.TYPE_LABELS[a.type]} “{a.title}”" for a in removing)
        return [self._post(chat, "assistant", "removed",
                           f"{route.reply or 'Removed.'}\n{lines}\nThey are hidden, not deleted: press Undo to bring "
                           "them back.", {"asset_ids": [a.id for a in removing]}, call_id=call_id)]

    def bring_back(self, chat: Chat, message_id: int) -> list[Message]:
        """Undoes a removal: the assets come back as they were, at their old place in the plan."""
        campaign = self.get(chat)
        stages.require(campaign.stage, stages.DONE, action="bring assets back")
        message = self._session.get(Message, message_id)
        if message is None or message.chat_id != chat.id or message.kind != "removed":
            raise UnknownAsset("No such removal in this chat.")
        if (message.data or {}).get("undone"):
            return []
        ids = set(message.data["asset_ids"])
        for asset in campaign.assets:
            if asset.id in ids and asset.state == "removed":
                asset.state = "done" if asset.content else "failed"
        self._sync_plan(campaign)
        message.data = {**message.data, "undone": True}
        self._session.commit()
        return []

    @staticmethod
    def _sync_plan(campaign: Campaign) -> None:
        """The plan shows the cards of the assets still in the campaign; removed ones wait in "removed"."""
        cards = {card["id"]: card for card in [*campaign.plan["assets"], *campaign.plan.get("removed", [])]}
        order = sorted(campaign.assets, key=lambda a: a.position)
        live = [cards[a.plan_id] for a in order if a.state != "removed" and a.plan_id in cards]
        gone = [cards[a.plan_id] for a in order if a.state == "removed" and a.plan_id in cards]
        campaign.plan = {**campaign.plan, "assets": live, "removed": gone}

    def _remember(self, chat: Chat, campaign: Campaign) -> list[Message]:
        """After the marketer corrects the agent, saves anything worth keeping for later campaigns."""
        memory = Memory(self._session, self._ai)
        try:
            items = memory.suggest(chat, campaign)
        except Exception:
            self._session.rollback()
            return []
        new = memory_notes(memory, items)
        chat.messages.extend(new)
        self._session.commit()
        return new

    def _memories_used(self, chat: Chat, campaign: Campaign, items: list) -> list[Message]:
        if not items:
            return []
        campaign.memories_used = [i.id for i in items]
        return [self._post(chat, "assistant", "note",
                           f"Using {len(items)} thing{'s' if len(items) > 1 else ''} you told me before: "
                           + "; ".join(i.text.strip().rstrip(".;") for i in items) + ".",
                           {"memory_ids": campaign.memories_used})]

    # Helpers

    def _work(self, campaign: Campaign) -> AssetWork:
        return AssetWork(self._session, self._ai, self._session.get_one(Brand, campaign.brand_id), campaign)

    def _research(self, campaign: Campaign) -> CampaignResearch:
        web = self._runtime.web if self._runtime else None
        # Full product names only: a short form can be an ordinary word ("Widget"), which would drop real findings.
        names = tuple(self._session.scalars(select(Entity.name).where(Entity.brand_id == campaign.brand_id,
                                                                      Entity.kind == "product")))
        return CampaignResearch(self._ai, web, self._session.get_one(Brand, campaign.brand_id).name, campaign,
                                runtime=self._runtime, off_limits=names)

    def _claim_stage(self, campaign: Campaign, allowed, stage: str, **values: Any) -> None:
        """Moves the campaign on in one step that only one request can win: a second approve or Write again,
        from another tab or a repeated request, finds the stage already changed and is refused."""
        claimed = self._session.execute(
            update(Campaign).where(Campaign.id == campaign.id, allowed).values(stage=stage, **values)
            .execution_options(synchronize_session=False)
        ).rowcount
        if claimed == 0:
            self._session.rollback()
            raise stages.WrongStage("That already started; refresh to see where the campaign is now.")
        campaign.stage = stage
        for key, value in values.items():
            setattr(campaign, key, value)

    def _ready_asset(self, chat: Chat, asset_id: int) -> Asset:
        asset = self.asset(chat, asset_id)
        if asset.state != "done" or not asset.content:
            raise stages.WrongStage("That asset isn't written yet.")
        return asset

    def _cost(self, call_ids: list[int]) -> float:
        if not call_ids:
            return 0.0
        return self._session.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0)).where(AiCall.id.in_(call_ids)))

    def _agent(self, campaign: Campaign) -> CampaignAgent:
        return CampaignAgent(self._session, self._ai, self._session.get_one(Brand, campaign.brand_id), campaign)

    def _notes(self, chat: Chat, agent: CampaignAgent) -> list[Message]:
        return [self._post(chat, "assistant", "note", note) for note in agent.conflict_notes(agent.last_output)]

    def _question_card(self, chat: Chat, campaign: Campaign, index: int) -> Message:
        question = campaign.questions[index]
        open_count = sum(1 for q in campaign.questions if not q.get("answer"))
        return self._post(chat, "assistant", "question", question["question"],
                          {**question, "id": index, "remaining": open_count})

    def _current_question(self, campaign: Campaign) -> int:
        index = self._next_open(campaign)
        if index is None:
            raise UnknownQuestion("There is no open question.")
        return index

    @staticmethod
    def _next_open(campaign: Campaign) -> int | None:
        return next((i for i, q in enumerate(campaign.questions) if not q.get("answer")), None)

    def _mark_card_answered(self, chat: Chat, question_id: int, answer: str) -> None:
        for message in chat.messages:
            if message.kind == "question" and (message.data or {}).get("id") == question_id and not message.data.get("answer"):
                message.data = {**message.data, "answer": answer}

    def _step(self, run: Callable[[], list[Message]]) -> list[Message]:
        """Runs one step of the campaign and saves what it changed together, at the end. While its AI calls run,
        nothing is written, so no row stays locked meanwhile. When one fails, the step's changes are dropped,
        except what it saved on purpose on the way: an asset's new version, a memory item, a brand correction."""
        with self._session.no_autoflush:
            new = run()
        self._session.commit()
        return new

    def _guarded_step(self, chat: Chat, campaign: Campaign, run: Callable[[], list[Message]]) -> list[Message]:
        """A step that can change the plan or its research. Its AI calls and web searches take a while, and the
        campaign can move on meanwhile (approved, or its plan or research changed from another tab or button).
        So it is saved only if the campaign is still at the stage and plan version it started from; otherwise
        nothing from it is kept, and the chat says so. Saving it moves the plan version on when it changed the
        plan or research. Such a step must not commit on the way, or it would find its own change."""
        stage, version = campaign.stage, campaign.plan_version

        def checked() -> list[Message]:
            new = run()
            now = self._session.execute(select(Campaign.stage, Campaign.plan_version)
                                        .where(Campaign.id == campaign.id).with_for_update()).one()
            if tuple(now) != (stage, version):
                raise PlanChanged(PLAN_CHANGED)
            state = inspect(campaign)
            if campaign.plan_version == version and any(state.attrs[name].history.has_changes()
                                                         for name in ("plan", "research", "searches")):
                campaign.plan_version += 1
            return new

        try:
            return self._step(checked)
        except PlanChanged:
            self._session.rollback()
            note = self._post(chat, "assistant", "note", PLAN_CHANGED)
            self._session.commit()
            return [note]

    def _expire_open_questions(self, chat: Chat, campaign: Campaign) -> None:
        """Questions still open when the plan is approved were about the plan, so they no longer apply; their
        cards say so."""
        if not any(not q.get("answer") for q in campaign.questions):
            return
        campaign.questions = [q if q.get("answer") else {**q, "expired": True} for q in campaign.questions]
        for message in chat.messages:
            if message.kind == "question" and not (message.data or {}).get("answer"):
                message.data = {**message.data, "expired": True}

    def _locked(self, chat: Chat) -> Campaign:
        """The campaign, locked and read again, for a quick change that must not overwrite a newer one. The lock
        lasts until the change is saved."""
        campaign = self.get(chat)
        self._session.refresh(campaign, with_for_update=True)
        return campaign

    def _post(self, chat: Chat, role: str, kind: str, content: str, data: dict | None = None,
              call_id: int | None = None) -> Message:
        """Adds a message to the chat. It is saved with the rest of the step, not on its own."""
        message = Message(role=role, kind=kind, content=content, data=data, ai_call_id=call_id)
        chat.messages.append(message)
        return message
