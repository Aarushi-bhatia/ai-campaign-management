"""What every part of a campaign chat shares: finding the campaign, posting messages, costs, the agent and
research for it, and the steps that decide what is saved when an AI call fails or the campaign moves on."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from app.ai.models import AiCall
from app.ai.service import AiService
from app.brand.models import Brand, Entity
from app.campaign import stages
from app.campaign.agent import CampaignAgent
from app.campaign.errors import NoBrand, PlanChanged
from app.campaign.models import Campaign
from app.campaign.research import CampaignResearch
from app.campaign.runtime import Runtime
from app.campaign.writing.assets import AssetWork
from app.chat.models import Chat, Message

PLAN_CHANGED = ("The plan changed while I was working on this: it was approved, or changed somewhere else. So I "
                "left it as it is, and nothing from this step was kept. The plan shown now is the latest.")


def brand_of_its_time(session: Session, chat: Chat) -> int | None:
    """The brand a chat from before campaigns goes with: the newest one added by the time the chat was made, else
    the first brand; never one added since, which would move the chat into another brand's list."""
    ready = select(Brand.id).where(Brand.status == "ready")
    then = session.scalars(ready.where(Brand.created_at <= chat.created_at).order_by(Brand.id.desc())).first()
    return then or session.scalars(ready.order_by(Brand.id)).first()


def usd(amount: float) -> str:
    return f"${amount:.4f}" if amount < 0.01 else f"${amount:.2f}"


class Conversation:
    """The base of each part of a campaign chat (the plan, the assets, memory), and of the service that runs them."""

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
            raise NoBrand("That brand isn't ready yet." if brand_id is not None
                          else "Add a brand before starting a campaign.")
        campaign = Campaign(chat_id=chat.id, brand_id=brand.id)
        self._session.add(campaign)
        self._session.commit()
        return campaign

    def get(self, chat: Chat) -> Campaign:
        """The chat's campaign. Chats from before campaigns existed get one when first opened."""
        campaign = self._session.scalars(select(Campaign).where(Campaign.chat_id == chat.id)).first()
        return campaign or self.start(chat, brand_of_its_time(self._session, chat))

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

    def _cost(self, call_ids: list[int]) -> float:
        if not call_ids:
            return 0.0
        return self._session.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0))
                                    .where(AiCall.id.in_(call_ids)))

    def _agent(self, campaign: Campaign) -> CampaignAgent:
        return CampaignAgent(self._session, self._ai, self._session.get_one(Brand, campaign.brand_id), campaign)

    def _notes(self, chat: Chat, agent: CampaignAgent) -> list[Message]:
        return [self._post(chat, "assistant", "note", note) for note in agent.conflict_notes(agent.last_output)]

    def _question_card(self, chat: Chat, campaign: Campaign, index: int) -> Message:
        question = campaign.questions[index]
        open_count = sum(1 for q in campaign.questions if not q.get("answer"))
        return self._post(chat, "assistant", "question", question["question"],
                          {**question, "id": index, "remaining": open_count})

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
