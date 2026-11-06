"""The assets part of a campaign chat: what a message asks for once they are written (edit, add, remove, a new
image), hand edits, Undo and Restore, and Check again."""

import json
from typing import Any

from app.ai.service import AiCallFailed
from app.campaign import editing, stages
from app.campaign.agent import at_least_two, new_card_id, used_card_ids
from app.campaign.conversation import Conversation, usd
from app.campaign.errors import BadContent, UnknownAsset
from app.campaign.models import Asset, Campaign
from app.campaign.planning import PLAN_FIELDS
from app.campaign.prompts import CHANNEL_OF
from app.campaign.writing import writer
from app.campaign.writing.assets import AssetChanged, AssetWork, EmptyEdit
from app.campaign.writing.queue import write_campaign
from app.chat.models import Chat, Message
from app.config import ModelSize


def _and_quoted(items: list[str]) -> str:
    quoted = [f"“{item}”" for item in items]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _warning_note(warnings: list[dict[str, Any]]) -> str:
    """What an edited asset's reply line adds about the checks."""
    if any(w["check"] == "not checked" for w in warnings):
        return "; its checks couldn't run, so press Check again on it"
    return f"; {len(warnings)} warning{'s' if len(warnings) > 1 else ''}" if warnings else ""



def _head(reply: str, all_saved: bool) -> str:
    """The first line of an edit's reply. The AI writes it before the edit runs, saying what it did; when an asset
    wasn't changed after all, that would claim too much, so the lines under it speak for themselves."""
    return (reply or "Done.") if all_saved else "Here's what happened:"


class AssetChat(Conversation):
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
                                  f"You've made this change by hand more than once. Remember it? {offer}",
                                  {"text": offer}))
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
        found = (f"{len(draft.warnings)} warning{'s' if len(draft.warnings) != 1 else ''}" if draft.warnings
                 else "no problems")
        note = self._post(chat, "assistant", "note",
                          f"Checked “{asset.title}” again: {found}. Cost {usd(self._cost(draft.call_ids))}.")
        self._session.commit()
        return asset, [note]

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

    def edit(self, chat: Chat, campaign: Campaign, message: str) -> list[Message]:
        """A chat message once the assets are written: works out what it asks for, then does only that."""
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
        if route.action == "ask":
            return [self._ask_about_edit(chat, campaign, route, message)]
        if route.action == "edit":
            return self._edit_texts(chat, campaign, work, route, reply.call_id)
        act = {"add": self._add_assets, "remove": self._remove_assets, "image": self._change_images}[route.action]
        return act(chat, campaign, route, reply.call_id)

    def _ask_about_edit(self, chat: Chat, campaign: Campaign, route: editing.Route, message: str) -> Message:
        """The edit was unclear: a question card, answered like any other, then the edit runs with the answer."""
        # The model's own questions keep to four choices; "Which asset?" lists every asset, so none is missing.
        options = [o.strip() for o in route.ask["options"] if o.strip()]
        options = at_least_two(options if route.ask.get("every_asset") else options[:4])
        campaign.questions = [*campaign.questions, {
            "kind": "unclear", "question": route.ask["question"], "why": "", "source_path": "", "quote": "",
            "options": [{"label": o, "value": o} for o in options], "about": message, "answer": None,
            "stage": stages.DONE,
        }]
        return self._question_card(chat, campaign, len(campaign.questions) - 1)

    def _edit_texts(self, chat: Chat, campaign: Campaign, work: AssetWork, route: editing.Route,
                    call_id: int) -> list[Message]:
        """Rewrites only the assets and fields meant, and replies with a line and the cost for each."""
        new = []
        if route.research_query:
            research = self._research(campaign)
            new += [self._post(chat, "assistant", "note", line)
                    for line in research.on_request(route.research_query, [a.plan_id for a, _ in route.targets])]
        # Every call the edit made, so the Costs tab sums the same calls as the "Edit cost" line.
        lines, call_ids, all_saved = [], [call_id], True
        total = self._cost(call_ids)
        for asset, field_name in route.targets:
            line, ids, cost, saved = self._edit_one(work, asset, field_name, route.instruction)
            lines.append(line)
            call_ids += ids
            total += cost
            all_saved &= saved
        head = _head(route.reply, all_saved)
        body = "\n".join(f"- {line}" for line in lines)
        return new + [self._post(chat, "assistant", "edit", f"{head}\n{body}\nEdit cost: {usd(total)}.",
                                 {"asset_ids": [a.id for a, _ in route.targets], "cost_usd": total,
                                  "call_ids": [i for i in call_ids if i is not None]},
                                 call_id=call_id)]

    def _edit_one(self, work: AssetWork, asset: Asset, field_name: str,
                  instruction: str) -> tuple[str, list[int], float, bool]:
        """One asset's edit: the reply's line for it, the calls it made (a failed one's too), their cost, and
        whether a new version was saved.
        A failure here leaves the other assets' edits standing, since each is saved as it finishes."""
        name = f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”{f' ({field_name})' if field_name else ''}"
        try:
            draft = work.edit(asset, instruction, field_name)
        except AiCallFailed as failure:
            cost = self._cost([failure.call_id])
            return (f"{name}: couldn't be edited ({failure}), so it is as it was. "
                    f"Ask again to retry it ({usd(cost)}).", [failure.call_id], cost, False)
        except AssetChanged:
            return (f"{name}: it changed while I was editing it, so I left your newer version as it is. "
                    "Ask again to apply this change to it.", [], 0.0, False)
        except EmptyEdit as empty:
            cost = self._cost([empty.args[0]])
            return (f"{name}: the edit would have left it with no text, so I left it as it is ({usd(cost)}).",
                    [empty.args[0]], cost, False)
        cost = self._cost(draft.call_ids)
        if not draft.saved:
            changed = f". {draft.changed}" if draft.changed else ""
            return f"{name}: not changed, so no new version{changed} ({usd(cost)})", draft.call_ids, cost, False
        return (f"{name}: {draft.changed or 'changed'} ({usd(cost)}{_warning_note(draft.warnings)})",
                draft.call_ids, cost, True)

    def _change_images(self, chat: Chat, campaign: Campaign, route: editing.Route, call_id: int) -> list[Message]:
        """A different image (or none) for the assets meant. The reply says what each now uses, or that it kept
        its image because nothing else fits; it never claims a change that wasn't made."""
        work = self._work(campaign)
        lines, call_ids, all_saved = [], [call_id], True
        total = self._cost(call_ids)
        for asset, _ in route.targets:
            label = f"{writer.TYPE_LABELS[asset.type]} “{asset.title}”"
            try:
                draft = work.new_image(asset, route.instruction)
            except AiCallFailed as failure:
                cost = self._cost([failure.call_id])
                total += cost
                call_ids.append(failure.call_id)
                lines.append(f"{label}: the image couldn't be picked ({failure}), so it keeps the one it has. Ask "
                             f"again to retry it ({usd(cost)}).")
                all_saved = False
                continue
            except AssetChanged:
                lines.append(f"{label}: it changed while I was picking, so I left your newer version as it is. Ask "
                             "again to change its image.")
                all_saved = False
                continue
            cost = self._cost(draft.call_ids)
            total += cost
            call_ids += draft.call_ids
            done = draft.changed if draft.saved else f"not changed. {draft.changed}"
            all_saved &= draft.saved
            lines.append(f"{label}: {done} ({usd(cost)})")
        body = "\n".join(f"- {line}" for line in lines)
        head = _head(route.reply, all_saved)
        return [self._post(chat, "assistant", "edit", f"{head}\n{body}\nEdit cost: {usd(total)}.",
                           {"asset_ids": [a.id for a, _ in route.targets], "cost_usd": total,
                            "call_ids": [i for i in call_ids if i is not None]}, call_id=call_id)]

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
        what = (f"{len(added)} {kinds.pop()}{'s' if len(added) > 1 else ''}" if len(kinds) == 1
                else f"{len(added)} assets")
        summary = f"{campaign.plan.get('summary', '').strip()} Added after writing: {what} ({titles}).".strip()
        campaign.plan = {**campaign.plan, "summary": summary, "assets": [*campaign.plan["assets"], *added]}
        campaign.plan_version += 1
        start = len(campaign.assets)
        campaign.assets.extend(Asset(plan_id=card["id"], position=start + i, type=card["type"], title=card["title"])
                               for i, card in enumerate(added))
        self._session.flush()  # the new assets get their ids
        lines ="\n".join(f"- {writer.TYPE_LABELS[card['type']]} “{card['title']}”" for card in added)
        note = self._post(chat, "assistant", "edit",
                          f"{route.reply or 'Adding them now.'}\n{lines}\nWriting "
                          f"{'it' if len(added) == 1 else 'them'} now; the assets already written stay as they are.",
                          {"asset_ids": [a.id for a in campaign.assets[start:]], "call_ids": [call_id]},
                          call_id=call_id)
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
        hidden = ("It is hidden, not deleted: press Undo to bring it back." if len(removing) == 1
                  else "They are hidden, not deleted: press Undo to bring them back.")
        return [self._post(chat, "assistant", "removed", f"{route.reply or 'Removed.'}\n{lines}\n{hidden}",
                           {"asset_ids": [a.id for a in removing]}, call_id=call_id)]

    @staticmethod
    def _sync_plan(campaign: Campaign) -> None:
        """The plan shows the cards of the assets still in the campaign; removed ones wait in "removed"."""
        cards = {card["id"]: card for card in [*campaign.plan["assets"], *campaign.plan.get("removed", [])]}
        order = sorted(campaign.assets, key=lambda a: a.position)
        live = [cards[a.plan_id] for a in order if a.state != "removed" and a.plan_id in cards]
        gone = [cards[a.plan_id] for a in order if a.state == "removed" and a.plan_id in cards]
        campaign.plan = {**campaign.plan, "assets": live, "removed": gone}

    def _ready_asset(self, chat: Chat, asset_id: int) -> Asset:
        asset = self.asset(chat, asset_id)
        if asset.state != "done" or not asset.content:
            raise stages.WrongStage("That asset isn't written yet.")
        return asset
