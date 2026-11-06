import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import AiService
from app.campaign.conversation import brand_of_its_time
from app.campaign.models import Campaign
from app.campaign.runtime import Runtime
from app.campaign.service import CampaignService
from app.chat.models import Chat

TITLE_LENGTH = 60


class ChatNotFound(Exception):
    pass


class ChatService:
    """Chats, each holding one campaign. What a message does depends on the campaign's stage."""

    def __init__(self, session: Session, ai: AiService, runtime: Runtime | None = None) -> None:
        self._session = session
        self.campaigns = CampaignService(session, ai, runtime)

    def create(self, brand_id: int | None = None) -> Chat:
        chat = Chat()
        self._session.add(chat)
        self._session.flush()
        self.campaigns.start(chat, brand_id)
        return chat

    def list(self) -> list[tuple[Chat, int | None]]:
        """Every chat, newest first, with the brand its campaign uses. A chat from before campaigns shows with the
        brand it will get when opened; None only when there is no brand at all."""
        query = (select(Chat, Campaign.brand_id).outerjoin(Campaign, Campaign.chat_id == Chat.id)
                 .order_by(Chat.id.desc()))
        return [(chat, brand_id if brand_id is not None else brand_of_its_time(self._session, chat))
                for chat, brand_id in self._session.execute(query)]

    def get(self, chat_id: int) -> Chat:
        chat = self._session.get(Chat, chat_id)
        if chat is None:
            raise ChatNotFound(chat_id)
        return chat

    def send(self, chat_id: int, content: str):
        chat = self.get(chat_id)
        if not chat.messages:
            chat.title = title_from(content)
        return self.campaigns.on_message(chat, content)


def title_from(text: str) -> str:
    """The first line of the first message, without markdown marks."""
    first = next((line for line in text.splitlines() if line.strip()), "New campaign")
    return re.sub(r"[*_`]+", "", re.sub(r"^[#>\s-]+", "", first)).strip()[:TITLE_LENGTH] or "New campaign"
