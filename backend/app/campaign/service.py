"""Runs a campaign chat: each user message or answer moves the campaign along its stages. The work of each
stage is in its own part: `plans` (planning.py), `assets` (asset_chat.py) and `memory` (remembering.py)."""

from typing import Any

from sqlalchemy.orm import Session

from app.ai.service import AiService
from app.campaign import stages
from app.campaign.asset_chat import AssetChat
from app.campaign.conversation import Conversation
from app.campaign.errors import QuestionExpired, UnknownQuestion
from app.campaign.models import Campaign
from app.campaign.planning import OVERRIDE, Planning, override_choice
from app.campaign.remembering import Remembering
from app.campaign.runtime import Runtime
from app.chat.models import Chat, Message


def _expired(question: dict[str, Any], stage: str) -> bool:
    """A question only applies at the stage it was asked at. One from before questions recorded their stage, still
    open once the assets are written, was about the plan (only questions about assets carry "about")."""
    asked = question.get("stage") or (None if "about" in question or stage != stages.DONE else stages.PLAN_READY)
    return bool(question.get("expired")) or (asked is not None and asked != stage)


def _option_for(question: dict[str, Any], answer: str) -> dict[str, str] | None:
    """The option the answer picks: one sent by a button, or typed as its label. For an override question, a
    typed yes or no counts too."""
    option = next((o for o in question["options"] if answer in (o["value"], o["label"])), None)
    if option is None and question.get("brief_rule"):
        value = override_choice(answer)
        option = next((o for o in question["options"] if o["value"] == value), None)
    return option


class CampaignService(Conversation):
    def __init__(self, session: Session, ai: AiService, runtime: Runtime | None = None) -> None:
        super().__init__(session, ai, runtime)
        self.memory = Remembering(session, ai, runtime)
        self.plans = Planning(session, ai, runtime, self.memory)
        self.assets = AssetChat(session, ai, runtime)

    def on_message(self, chat: Chat, text: str) -> list[Message]:
        """The user's message, then whatever the campaign's stage calls for."""
        campaign = self.get(chat)
        self._post(chat, "user", "text", text)
        self._session.commit()  # the message is kept even when the step after it fails
        if campaign.stage == stages.BRIEF:
            return self._guarded_step(chat, campaign, lambda: self.plans.review(chat, campaign, text))
        if campaign.stage == stages.ASKING:
            if self._next_open(campaign) is None:
                # Every question is answered but planning didn't finish (it failed): plan again.
                return self._guarded_step(chat, campaign, lambda: self.plans.plan(chat, campaign))
            return self.answer(chat, self._current_question(campaign), text, typed=True)
        if campaign.stage == stages.PLAN_READY:
            return (self._guarded_step(chat, campaign, lambda: self.plans.edit(chat, campaign, text))
                    + self._step(lambda: self.memory.remember(chat, campaign)))
        if campaign.stage == stages.DONE:
            return (self._step(lambda: self.assets.edit(chat, campaign, text))
                    + self._step(lambda: self.memory.remember(chat, campaign)))
        return self._step(lambda: [self._post(chat, "assistant", "note",
                                              "The assets are being written. "
                                              "Changes can be asked for once they're done.")])

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
        option = _option_for(question, answer)
        if option is None and question.get("brief_rule"):
            return self._ask_again(chat, campaign, question_id, answer, typed)
        question["answer"] = option["label"] if option else answer
        campaign.questions = [*campaign.questions[:question_id], question, *campaign.questions[question_id + 1:]]
        if not typed:
            # A button shows its label; words typed into the card's box show as typed, and the card says what
            # they counted as.
            clicked = option is not None and answer in (option["value"], option["label"])
            self._post(chat, "user", "text", question["answer"] if clicked else answer)
        self._mark_card_answered(chat, question_id, question["answer"])
        new = []
        if question.get("conflict_target") and option:
            new += self.plans.settle_conflict(chat, campaign, question["conflict_target"], option["value"])
        if question.get("brief_rule") and option and option["value"] == OVERRIDE:
            campaign.brief_rules = [*campaign.brief_rules, question["brief_rule"]]
            new.append(self._post(chat, "assistant", "note",
                                  f"Your brief changes a brand rule, for this campaign only: {question['brief_rule']}"))
        self._session.commit()  # the answer is kept even when the step after it fails
        if campaign.stage == stages.PLAN_READY:
            return new + self._guarded_step(chat, campaign, lambda: self.plans.edit(
                chat, campaign, f"{question['question']} {question['answer']}"))
        if campaign.stage == stages.DONE:
            return new + self._step(lambda: self.assets.edit(
                chat, campaign, f"{question.get('about', '')} {question['question']} {question['answer']}".strip()))
        nxt = self._next_open(campaign)
        if nxt is not None:
            return new + self._step(lambda: [self._question_card(chat, campaign, nxt)])
        return new + self._guarded_step(chat, campaign, lambda: self.plans.plan(chat, campaign))

    def _ask_again(self, chat: Chat, campaign: Campaign, question_id: int, answer: str, typed: bool) -> list[Message]:
        """A brand rule only changes on a clear yes, so an answer that is neither yes nor no leaves the question
        open and shows it again."""
        if not typed:
            self._post(chat, "user", "text", answer)
        # The card above the unclear answer says so, and stays as it is: only the card shown again below takes
        # the answer, so the chat never reads as if the unclear one counted.
        for message in chat.messages:
            if (message.kind == "question" and (message.data or {}).get("id") == question_id
                    and not message.data.get("answer") and not message.data.get("asked_again")):
                message.data = {**message.data, "asked_again": answer}
        new = [self._post(chat, "assistant", "text", "I need a clear yes or no here, so a brand rule isn't changed "
                          "by mistake. Pick one of the two answers."),
               self._question_card(chat, campaign, question_id)]
        self._session.commit()
        return new

    def retry_review(self, chat: Chat) -> list[Message]:
        """The Try again button after a brief review failed: reviews the brief that was sent, which is still the
        last message, so the marketer doesn't have to type "try again" (that would become the brief)."""
        campaign = self.get(chat)
        stages.require(campaign.stage, stages.BRIEF, action="review the brief again")
        last = chat.messages[-1] if chat.messages else None
        if last is None or last.role != "user":
            raise UnknownQuestion("There is no brief waiting to be reviewed; paste it in the chat.")
        return self._guarded_step(chat, campaign, lambda: self.plans.review(chat, campaign, last.content))

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
            if (message.kind == "question" and (message.data or {}).get("id") == question_id
                    and not message.data.get("answer") and not message.data.get("asked_again")):
                message.data = {**message.data, "answer": answer}
