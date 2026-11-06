"""The memory part of a campaign chat: what it saves from the marketer's messages, the "Remember this?" offer,
and the note saying which saved items a brief review used."""

from app.campaign.conversation import Conversation
from app.campaign.errors import UnknownQuestion
from app.campaign.models import Campaign
from app.campaign.writing.queue import full_note, memory_notes, remembered_note
from app.chat.models import Chat, Message
from app.memory.service import Memory, MemoryFull


class Remembering(Conversation):
    def remember_offer(self, chat: Chat, message_id: int) -> list[Message]:
        """The marketer accepted a "Remember this?" offer."""
        campaign = self.get(chat)
        offer = next((m for m in chat.messages if m.id == message_id and m.kind == "remember_offer"), None)
        if offer is None or (offer.data or {}).get("done"):
            raise UnknownQuestion("That offer isn't open.")
        offer.data = {**offer.data, "done": True}
        return self._add_memory(chat, campaign, offer.data["text"], "preference")

    def remember(self, chat: Chat, campaign: Campaign) -> list[Message]:
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

    def memories_used(self, chat: Chat, campaign: Campaign, items: list) -> list[Message]:
        if not items:
            return []
        campaign.memories_used = [i.id for i in items]
        return [self._post(chat, "assistant", "note",
                           f"Using {len(items)} thing{'s' if len(items) > 1 else ''} you told me before: "
                           + "; ".join(i.text.strip().rstrip(".;") for i in items) + ".",
                           {"memory_ids": campaign.memories_used})]

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
