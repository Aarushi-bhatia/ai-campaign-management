from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.deps import get_ai_service, get_ai_transport
from app.ai.service import AiCallFailed, AiService
from app.ai.transport import AiTransport
from app.brand.views import file_url
from app.campaign import costs
from app.campaign.assets import AssetChanged, NothingToUndo
from app.campaign.models import Asset, Campaign
from app.campaign.research import UnknownFinding
from app.campaign.runtime import Runtime
from app.campaign.service import BadPlan, NoBrand, UnknownAsset, UnknownQuestion
from app.campaign.stages import WrongStage
from app.chat.models import Chat
from app.chat.schemas import (
    AnswerIn, AssetChange, AssetOut, AssetVersionOut, CampaignOut, ChatOut, ChatSummary, HandEditIn, MessageOut, NewChatIn,
    PlanIn,
    SendMessage,
)
from app.chat.service import ChatNotFound, ChatService
from app.config import Settings, get_settings
from app.db import SessionLocal, get_session
from app.jobs import JobRunner, get_job_runner
from app.research.client import WebResearch
from app.research.deps import get_web_research

router = APIRouter(prefix="/api/chats", tags=["chats"])


def get_runtime(
    transport: Annotated[AiTransport, Depends(get_ai_transport)],
    settings: Annotated[Settings, Depends(get_settings)],
    jobs: Annotated[JobRunner, Depends(get_job_runner)],
    web: Annotated[WebResearch | None, Depends(get_web_research)],
) -> Runtime:
    return Runtime(SessionLocal, transport, settings, jobs, web)


def get_chat_service(
    session: Annotated[Session, Depends(get_session)],
    ai: Annotated[AiService, Depends(get_ai_service)],
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> ChatService:
    return ChatService(session, ai, runtime)


Chats = Annotated[ChatService, Depends(get_chat_service)]


def _chat(chats: ChatService, chat_id: int) -> Chat:
    try:
        return chats.get(chat_id)
    except ChatNotFound:
        raise HTTPException(404, "Chat not found")


def _chat_out(chats: ChatService, chat: Chat) -> ChatOut:
    return ChatOut(
        id=chat.id, title=chat.title, created_at=chat.created_at,
        messages=[MessageOut.model_validate(m) for m in chat.messages],
        campaign=CampaignOut.model_validate(chats.campaigns.get(chat)),
    )


def _run(action):
    """Turns campaign errors into the right HTTP answers."""
    try:
        return action()
    except (WrongStage, AssetChanged) as error:
        raise HTTPException(409, str(error))
    except (UnknownQuestion, BadPlan, NothingToUndo) as error:
        raise HTTPException(400, str(error))
    except (UnknownFinding, UnknownAsset) as error:
        raise HTTPException(404, str(error))
    except AiCallFailed as failure:
        raise HTTPException(502, f"The AI request failed: {failure}")


@router.post("", response_model=ChatOut, status_code=201)
def create_chat(chats: Chats, body: NewChatIn | None = None):
    """A new chat is a new campaign, for the chosen brand, or the most recently read one."""
    try:
        chat = chats.create(body.brand_id if body else None)
    except NoBrand as error:
        raise HTTPException(409, str(error))
    return _chat_out(chats, chat)


@router.get("", response_model=list[ChatSummary])
def list_chats(chats: Chats):
    return chats.list()


@router.get("/{chat_id}", response_model=ChatOut)
def get_chat(chat_id: int, chats: Chats):
    return _chat_out(chats, _chat(chats, chat_id))


@router.post("/{chat_id}/messages", response_model=list[MessageOut], status_code=201)
def send_message(chat_id: int, body: SendMessage, chats: Chats):
    """The user's message and everything the agent says back."""
    _chat(chats, chat_id)
    return _run(lambda: chats.send(chat_id, body.content))


@router.post("/{chat_id}/answer", response_model=list[MessageOut], status_code=201)
def answer(chat_id: int, body: AnswerIn, chats: Chats):
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.answer(chat, body.question_id, body.answer))


@router.put("/{chat_id}/plan", response_model=CampaignOut)
def update_plan(chat_id: int, body: PlanIn, chats: Chats):
    """Direct edits on the plan cards: delete, reorder, change a field."""
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.update_plan(chat, body.assets))


@router.post("/{chat_id}/approve", response_model=list[MessageOut])
def approve(chat_id: int, chats: Chats):
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.approve(chat))


@router.post("/{chat_id}/write", response_model=CampaignOut)
def begin_writing(chat_id: int, chats: Chats):
    """Starts writing the assets. Refused until the plan is approved."""
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.begin_writing(chat))


@router.delete("/{chat_id}/research/{finding_id}", response_model=CampaignOut)
def remove_finding(chat_id: int, finding_id: str, chats: Chats):
    """Takes a research finding out of the plan. It won't be used when writing."""
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.remove_finding(chat, finding_id))


@router.post("/{chat_id}/research/retry", response_model=list[MessageOut])
def retry_research(chat_id: int, chats: Chats):
    """Runs again the plan's web searches that failed."""
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.retry_research(chat))


@router.post("/{chat_id}/research/{finding_id}/restore", response_model=CampaignOut)
def bring_back_finding(chat_id: int, finding_id: str, chats: Chats):
    """Undoes a removal: the finding is used in the writing again."""
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.bring_back_finding(chat, finding_id))


@router.post("/{chat_id}/research/{finding_id}/better", response_model=list[MessageOut])
def better_source(chat_id: int, finding_id: str, chats: Chats):
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.better_source(chat, finding_id))


def _asset_out(asset: Asset, campaign: Campaign) -> AssetOut:
    out = AssetOut.model_validate(asset)
    if asset.image and asset.image.get("path"):
        out.image_url = file_url(campaign.brand_id, asset.image["path"])
    cards = [*(campaign.plan or {}).get("assets", []), *(campaign.plan or {}).get("removed", [])]
    out.draft_for = next((c.get("draft_for", "") for c in cards if c["id"] == asset.plan_id), "")
    return out


@router.get("/{chat_id}/assets", response_model=list[AssetOut])
def list_assets(chat_id: int, chats: Chats):
    campaign = chats.campaigns.get(_chat(chats, chat_id))
    return [_asset_out(a, campaign) for a in campaign.live_assets]


@router.get("/{chat_id}/assets/{asset_id}/versions", response_model=list[AssetVersionOut])
def asset_versions(chat_id: int, asset_id: int, chats: Chats):
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.asset(chat, asset_id).versions)


@router.put("/{chat_id}/assets/{asset_id}", response_model=AssetChange)
def hand_edit(chat_id: int, asset_id: int, body: HandEditIn, chats: Chats):
    """Typed straight into the asset. Free checks only; no AI, no cost."""
    chat = _chat(chats, chat_id)
    asset, messages = _run(lambda: chats.campaigns.hand_edit(chat, asset_id, body.content, body.base_version))
    return AssetChange(asset=_asset_out(asset, chats.campaigns.get(chat)),
                       messages=[MessageOut.model_validate(m) for m in messages])


@router.post("/{chat_id}/assets/{asset_id}/undo", response_model=AssetOut)
def undo(chat_id: int, asset_id: int, chats: Chats, base_version: int | None = None):
    chat = _chat(chats, chat_id)
    asset = _run(lambda: chats.campaigns.undo(chat, asset_id, base_version))
    return _asset_out(asset, chats.campaigns.get(chat))


@router.post("/{chat_id}/assets/{asset_id}/versions/{number}/restore", response_model=AssetOut)
def restore(chat_id: int, asset_id: int, number: int, chats: Chats, base_version: int | None = None):
    """Brings back any earlier version as a new one. Free; no AI."""
    chat = _chat(chats, chat_id)
    asset = _run(lambda: chats.campaigns.restore(chat, asset_id, number, base_version))
    return _asset_out(asset, chats.campaigns.get(chat))


@router.post("/{chat_id}/assets/{asset_id}/check", response_model=AssetChange)
def check_again(chat_id: int, asset_id: int, chats: Chats):
    """The full check, AI included, on demand."""
    chat = _chat(chats, chat_id)
    asset, messages = _run(lambda: chats.campaigns.check_again(chat, asset_id))
    return AssetChange(asset=_asset_out(asset, chats.campaigns.get(chat)),
                       messages=[MessageOut.model_validate(m) for m in messages])


@router.post("/{chat_id}/removed/{message_id}/undo", response_model=list[MessageOut])
def bring_back(chat_id: int, message_id: int, chats: Chats):
    """Undoes a removal made by chat: the assets come back as they were. Free; no AI."""
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.bring_back(chat, message_id))


@router.post("/{chat_id}/remember/{message_id}", response_model=list[MessageOut])
def accept_remember_offer(chat_id: int, message_id: int, chats: Chats):
    chat = _chat(chats, chat_id)
    return _run(lambda: chats.campaigns.remember_offer(chat, message_id))


@router.get("/{chat_id}/costs")
def campaign_costs(chat_id: int, chats: Chats, session: Annotated[Session, Depends(get_session)]):
    """Totals per stage, per asset and per edit, with cache hit rates. The brand's reading cost is apart."""
    campaign = chats.campaigns.get(_chat(chats, chat_id))
    return costs.report(session, campaign)
