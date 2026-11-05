"""Memory across campaigns: core memory in every prompt, campaign history only at planning."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.fake import FakeTransport
from app.ai.service import AiService
from app.campaign import agent
from app.campaign.models import Campaign
from app.chat.models import Chat, Message
from app.campaign.writing.queue import remembered_note
from app.config import Settings
from app.db import SessionLocal
from app.brand.images.picking import AssetSpec, rank_prompt
from app.memory.models import CampaignRecord, MemoryItem
from app.memory.service import (HISTORY_IN_PLANNING, Memory, MemoryFull, changes_meaning, history, near_duplicate,
                                recent_images, undo_remembered)
from tests import brand_brain

BRIEF = "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."


@pytest.fixture(autouse=True)
def brain(fake_ai: FakeTransport) -> None:
    fake_ai._default = brand_brain.reply


@pytest.fixture
def brand(client: TestClient) -> int:
    response = client.post("/api/brands", data={"name": "Acme"},
                           files=[("files", (p, c.encode())) for p, c in brand_brain.BRAND.items()])
    return response.json()["id"]


def _send(client: TestClient, chat_id: int, text: str) -> list[dict]:
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": text})
    assert response.status_code == 201, response.text
    return response.json()


def _planned(client: TestClient) -> int:
    chat_id = client.post("/api/chats").json()["id"]
    _send(client, chat_id, BRIEF)
    return chat_id


def _requests(fake_ai: FakeTransport, schema: str) -> list:
    return [r for r in fake_ai.requests if r.output_schema and r.output_schema.name == schema]


def test_a_correction_is_remembered_with_a_note(client: TestClient, brand: int):
    chat_id = _planned(client)

    messages = _send(client, chat_id, "Never call it a platform.")

    note = messages[-1]
    assert (note["kind"], note["content"]) == ("memory", "Remembered: Never call Acme a platform.")
    memory = client.get(f"/api/brands/{brand}/memory").json()
    assert [(i["text"], i["kind"], i["source_chat_id"]) for i in memory["core"]] == [
        ("Never call Acme a platform.", "correction", chat_id)
    ]


def test_undo_removes_the_item_and_marks_the_note(client: TestClient, brand: int):
    chat_id = _planned(client)
    note = _send(client, chat_id, "Never call it a platform.")[-1]

    assert client.delete(f"/api/memory/{note['data']['item_id']}").status_code == 204

    assert client.get(f"/api/brands/{brand}/memory").json()["core"] == []
    saved = next(m for m in client.get(f"/api/chats/{chat_id}").json()["messages"] if m["id"] == note["id"])
    assert saved["data"]["undone"] is True


def test_the_brief_itself_is_not_mined_for_memory(client: TestClient, brand: int, fake_ai: FakeTransport):
    chat_id = client.post("/api/chats").json()["id"]
    _send(client, chat_id, f"{BRIEF} Never call it a platform.")
    client.post(f"/api/chats/{chat_id}/approve")

    assert client.get(f"/api/brands/{brand}/memory").json()["core"] == []


def test_core_memory_is_in_the_next_chats_fixed_part(client: TestClient, brand: int, fake_ai: FakeTransport):
    _send(client, _planned(client), "Never call it a platform.")
    fake_ai.requests.clear()

    chat_id = client.post("/api/chats").json()["id"]
    messages = _send(client, chat_id, BRIEF)

    assert messages[0]["content"] == "Using 1 thing you told me before: Never call Acme a platform."
    review = _requests(fake_ai, "brief_review")[0]
    assert "- Never call Acme a platform." in review.prompt.fixed


def test_an_answer_to_a_question_card_is_never_learned(client: TestClient, brand: int):
    chat_id = client.post("/api/chats").json()["id"]
    _send(client, chat_id, "Do an awareness push.")  # two question cards
    client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 0, "answer": "Never call it a platform."})
    client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 1, "answer": "Q1"})

    assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200  # memory is looked at when writing ends

    # was saved as a rule for every campaign; an answer settles this campaign only
    assert client.get(f"/api/brands/{brand}/memory").json()["core"] == []


def _rewrite_note(session, brand: int, old: dict, text: str) -> Message:
    """A "Remembered" note from before items were no longer rewritten in place: the item was rewritten, and the
    note kept its old text. Such notes are still in old chats, and their Undo still works."""
    item = session.get(MemoryItem, old["id"])
    item.text, item.kind = text, "correction"
    session.commit()
    return Message(role="assistant", kind="memory", content=f"Remembered: {text} (this replaces “{old['text']}”)",
                   data={"item_id": old["id"], "previous": {"text": old["text"], "kind": old["kind"],
                                                            "source_chat_id": old["source_chat_id"]}})


def test_undo_of_an_old_rewrite_note_brings_the_old_text_back(client: TestClient, brand: int):
    old = client.post(f"/api/brands/{brand}/memory", json={"text": "Hold the hero for Brand.", "kind": "decision"}).json()
    with SessionLocal() as session:
        note = _rewrite_note(session, brand, old, "Use working-room photos for heroes.")
        undo_remembered(session, note)

    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [(i["id"], i["text"], i["kind"]) for i in core] == [(old["id"], "Hold the hero for Brand.", "decision")]


def test_a_clash_question_always_offers_following_the_brief():
    clash = agent._options(["Hold the hero for Brand", "Use product UI"], follow_brief=True)
    full = agent._options(["A", "B", "C", "D"], follow_brief=True)
    already = agent._options(["Follow the brief: a working room", "Ask Brand"], follow_brief=True)

    assert [o["label"] for o in clash] == ["Hold the hero for Brand", "Use product UI", "Follow the brief as written"]
    assert [o["label"] for o in full][-1] == "Follow the brief as written" and len(full) == 4
    assert [o["label"] for o in already] == ["Follow the brief: a working room", "Ask Brand"]


def test_the_brief_comes_before_memory_in_every_prompt(client: TestClient, brand: int, fake_ai: FakeTransport):
    client.post(f"/api/brands/{brand}/memory", json={"text": "Hold the hero for Brand."})

    _planned(client)

    review = _requests(fake_ai, "brief_review")[0]
    assert "the current brief or the marketer's answers in this chat say otherwise: those always come first" in \
        review.prompt.fixed
    assert "follow it and never ask about it, even if earlier guidance" in review.prompt.task[-1].content


def test_the_memory_note_has_clean_punctuation(client: TestClient, brand: int):
    for text in ("Use owned channels first.", "Never call Acme a platform"):
        assert client.post(f"/api/brands/{brand}/memory", json={"text": text}).status_code == 201

    messages = _send(client, client.post("/api/chats").json()["id"], BRIEF)

    # was "Use owned channels first.; Never call Acme a platform", with no full stop at the end
    assert messages[0]["content"] == "Using 2 things you told me before: Use owned channels first; Never call Acme a platform."


def test_the_fixed_part_is_the_same_for_every_call_of_a_brand(client: TestClient, brand: int, fake_ai: FakeTransport):
    first = _planned(client)
    client.post(f"/api/chats/{first}/approve")
    second = _planned(client)
    client.post(f"/api/chats/{second}/approve")

    agent_and_writer = [r for r in fake_ai.requests if r.output_schema and (
        r.output_schema.name in ("brief_review", "campaign_plan", "edit_request") or r.output_schema.name.endswith("_asset"))]
    assert len(agent_and_writer) > 6
    assert len({r.prompt.fixed for r in agent_and_writer}) == 1


def test_a_finished_campaign_gets_a_history_record(client: TestClient, brand: int):
    chat_id = _planned(client)
    client.post(f"/api/chats/{chat_id}/approve")

    history = client.get(f"/api/brands/{brand}/memory").json()["history"]
    assert [(h["name"], h["chat_id"], h["dates"]) for h in history] == [("Widget launch", chat_id, "2027-01-26")]
    assert history[0]["assets"] == ["email: Launch email", "linkedin_post: Launch post", "x_post: X launch post"]


def test_campaign_history_is_only_used_when_planning(client: TestClient, brand: int, fake_ai: FakeTransport):
    first = _planned(client)
    client.post(f"/api/chats/{first}/approve")
    fake_ai.requests.clear()

    second = _planned(client)
    client.post(f"/api/chats/{second}/approve")

    with_history = [r for r in fake_ai.requests if "Past campaigns for this brand" in str(r.to_payload())]
    assert {r.output_schema.name for r in with_history} == {"campaign_plan"}
    assert "Widget launch" in with_history[0].prompt.task[-1].content


def test_items_can_be_edited_pinned_and_deleted(client: TestClient, brand: int):
    item = client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails short.", "kind": "preference"}).json()

    changed = client.put(f"/api/memory/{item['id']}", json={"text": "Keep emails under 150 words.", "pinned": True}).json()
    assert (changed["text"], changed["pinned"]) == ("Keep emails under 150 words.", True)
    assert client.post(f"/api/brands/{brand}/memory", json={"text": "keep emails under 150 words"}).status_code == 409

    client.delete(f"/api/memory/{item['id']}")
    assert client.get(f"/api/brands/{brand}/memory").json()["core"] == []


def test_memory_is_kept_per_brand(client: TestClient, brand: int):
    client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails short."})

    assert client.get(f"/api/brands/{brand + 1}/memory").json()["core"] == []


def test_core_memory_stays_small(client: TestClient, brand: int):
    pinned = client.post(f"/api/brands/{brand}/memory", json={"text": "Item zero."}).json()
    client.put(f"/api/memory/{pinned['id']}", json={"pinned": True})
    for n in range(1, 55):
        client.post(f"/api/brands/{brand}/memory", json={"text": f"Item {n}."})

    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert len(core) == 50
    assert core[0]["text"] == "Item zero." and core[-1]["text"] == "Item 54."


# Ticket 9 review

def _fill(client: TestClient, brand: int, pinned: bool) -> list[dict]:
    items = []
    for n in range(50):
        item = client.post(f"/api/brands/{brand}/memory", json={"text": f"Mind alpha{n} beta{n} gamma{n}."}).json()
        if pinned:
            client.put(f"/api/memory/{item['id']}", json={"pinned": True})
        items.append(item)
    return items


def test_adding_to_a_full_memory_of_pinned_items_is_refused(client: TestClient, brand: int):
    _fill(client, brand, pinned=True)

    response = client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails under 150 words."})

    assert response.status_code == 409  # was 201, then deleted at once
    assert "all 50 items are pinned" in response.json()["detail"]
    assert len(client.get(f"/api/brands/{brand}/memory").json()["core"]) == 50


def test_adding_to_a_full_memory_says_which_item_was_dropped(client: TestClient, brand: int):
    items = _fill(client, brand, pinned=False)

    added = client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails under 150 words."}).json()

    assert added["dropped"] == [items[0]["text"]]  # the oldest unpinned item, and the marketer is told
    texts = [i["text"] for i in client.get(f"/api/brands/{brand}/memory").json()["core"]]
    assert "Keep emails under 150 words." in texts and items[0]["text"] not in texts


def test_a_full_memory_is_reported_in_the_chat(client: TestClient, brand: int):
    _fill(client, brand, pinned=True)
    chat_id = _planned(client)

    messages = _send(client, chat_id, "Never call it a platform.")

    assert messages[-1]["kind"] == "note" and "Memory is full and every item is pinned" in messages[-1]["content"]


def test_a_clear_duplicate_is_not_added_and_the_original_stays_as_it_was(client: TestClient, brand: int):
    first = client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails short."}).json()

    same = client.post(f"/api/brands/{brand}/memory", json={"text": "Emails should be short."})
    other = client.post(f"/api/brands/{brand}/memory", json={"text": "Never call it a toolkit."})
    other_again = client.post(f"/api/brands/{brand}/memory", json={"text": "Never call it a platform."})

    assert same.status_code == 409  # already in memory: the original wording and source are kept
    assert other.status_code == other_again.status_code == 201  # different instructions stay apart
    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [i["text"] for i in core] == ["Keep emails short.", "Never call it a toolkit.", "Never call it a platform."]
    assert core[0]["id"] == first["id"]


@pytest.mark.parametrize("old, new, merged", [
    ("Keep emails short.", "Emails should be short.", True),
    ("Never mention pricing in social posts.", "Always mention pricing in social posts.", False),  # a contradiction
    ("Keep LinkedIn posts under 150 words.", "Keep X posts under 150 words.", False),
    ("Use British spelling in emails.", "Use British spelling in blog posts.", False),
    ("Never call it a platform.", "Never call it a toolkit.", False),
    ("Use British spelling.", "Use British spelling in emails.", False),  # a narrower rule, not the same one
    ("Emails go out on Tuesdays.", "On Tuesdays, emails go out.", True),  # the same words in another order
    ("Please keep the subject line short.", "The subject line must be short.", True),  # only trivial wording
    ("Say toolkit, not platform.", "Say platform, not toolkit.", False),  # same words, opposite meaning
])
def test_only_clear_duplicates_merge_on_their_own(old: str, new: str, merged: bool):
    assert near_duplicate(old, new) is merged


def test_the_ai_check_holds_the_copy_to_core_memory(client: TestClient, brand: int, fake_ai: FakeTransport):
    client.post(f"/api/brands/{brand}/memory", json={"text": "Never call it a platform."})
    chat_id = _planned(client)

    client.post(f"/api/chats/{chat_id}/approve")

    check = next(r for r in fake_ai.requests if r.output_schema and r.output_schema.name == "asset_check")
    assert "- Never call it a platform." in check.prompt.fixed  # the check had the brand summary only


def test_the_image_picker_gets_memory_and_recent_campaigns_images():
    spec = AssetSpec(channel="x", asset_type="x_post", message="Launch.", recent_paths=frozenset({"photos/hero.jpg"}),
                     memory=("Prefer photos of real teams.",))

    task = rank_prompt(spec, [], {"channels": {}, "general_rules": [], "alt_text_rules": []}).task[-1].content

    assert "Used by the brand's recent campaigns: photos/hero.jpg" in task
    assert "What the marketer told you before: Prefer photos of real teams." in task


def test_recent_images_and_history_are_limited_in_the_database(client: TestClient, brand: int):
    with SessionLocal() as session:
        for n in range(7):
            session.add(CampaignRecord(brand_id=brand, name=f"Campaign {n}", goal="", audience="", angle="",
                                       images=[f"photos/{n}.jpg"], dates=""))
        session.commit()

        newest = history(session, brand, limit=HISTORY_IN_PLANNING)
        images = recent_images(session, brand)

    assert [r.name for r in newest] == [f"Campaign {n}" for n in (6, 5, 4, 3, 2)]
    assert images == {f"photos/{n}.jpg" for n in (6, 5, 4, 3, 2)}


def test_a_campaign_record_can_be_edited(client: TestClient, brand: int):
    with SessionLocal() as session:
        record = CampaignRecord(brand_id=brand, name="Launch", goal="Old goal", audience="Leads", angle="Small",
                                images=[], dates="")
        session.add(record)
        session.commit()
        record_id = record.id

    changed = client.put(f"/api/campaign-records/{record_id}", json={"goal": "Book demos", "angle": " "}).json()

    assert (changed["goal"], changed["angle"]) == ("Book demos", "Small")  # a blank field is left as it is


def test_adding_memory_for_a_missing_brand_is_a_404(client: TestClient):
    assert client.post("/api/brands/999/memory", json={"text": "Anything."}).status_code == 404  # was a server error


# Group 3 of the design review: memory undo and history records keep the earlier state

def test_undo_after_memory_was_full_brings_back_the_dropped_item(client: TestClient, brand: int):
    """Undo used to remove the new item and lose the one dropped to make room for it, for good."""
    items = _fill(client, brand, pinned=False)
    chat_id = _planned(client)
    note = _send(client, chat_id, "Never call it a platform.")[-1]
    assert "was dropped" in note["content"] and note["data"]["dropped"][0]["text"] == items[0]["text"]

    assert client.post(f"/api/memory/notes/{note['id']}/undo").status_code == 204

    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [(i["id"], i["text"]) for i in core] == [(i["id"], i["text"]) for i in items]  # same ids, same order
    assert core[0]["created_at"] == items[0]["created_at"]


def test_undo_that_no_longer_fits_in_memory_changes_nothing(client: TestClient, brand: int, settings: Settings,
                                                           fake_ai: FakeTransport):
    items = _fill(client, brand, pinned=False)
    with SessionLocal() as session:
        new = Memory(session, AiService(session, fake_ai, settings)).add(brand, "Keep emails under 150 words.",
                                                                         "preference", None)
        note = remembered_note(new)
        # as if two items had made room for it: bringing both back would go over the limit
        note.data = {**note.data, "dropped": [*note.data["dropped"], {**note.data["dropped"][0], "id": 99999}]}
        with pytest.raises(MemoryFull):
            undo_remembered(session, note)

    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert "Keep emails under 150 words." in [i["text"] for i in core] and len(core) == 50
    assert items[0]["id"] not in [i["id"] for i in core]


def test_writing_a_campaign_record_again_keeps_the_marketers_corrections(client: TestClient, brand: int,
                                                                        fake_ai: FakeTransport, settings: Settings):
    """The record used to be deleted and written from scratch, after Write again or added assets, losing the
    goal the marketer had corrected on the Memory page."""
    chat_id = _planned(client)
    client.post(f"/api/chats/{chat_id}/approve")
    record = client.get(f"/api/brands/{brand}/memory").json()["history"][0]
    client.put(f"/api/campaign-records/{record['id']}", json={"goal": "Book 40 demos"})

    with SessionLocal() as session:
        chat = session.get_one(Chat, chat_id)
        campaign = session.scalars(select(Campaign).where(Campaign.chat_id == chat_id)).one()
        Memory(session, AiService(session, fake_ai, settings)).record(chat, campaign)

    again = client.get(f"/api/brands/{brand}/memory").json()["history"]
    assert len(again) == 1 and again[0]["id"] == record["id"]  # updated in place
    assert again[0]["goal"] == "Book 40 demos"
    assert (again[0]["name"], again[0]["assets"]) == (record["name"], record["assets"])  # the rest is written again


def test_undo_is_refused_after_the_item_was_edited_or_pinned(client: TestClient, brand: int):
    """Undo used to delete the item anyway, along with the marketer's later edit and pin."""
    note = _send(client, _planned(client), "Never call it a platform.")[-1]
    item_id = note["data"]["item_id"]
    client.put(f"/api/memory/{item_id}", json={"text": "Never call Acme a platform or a suite.", "pinned": True})

    refused = client.post(f"/api/memory/notes/{note['id']}/undo")

    assert refused.status_code == 409 and "changed after it was remembered" in refused.json()["detail"]
    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [(i["id"], i["text"], i["pinned"]) for i in core] == [(item_id, "Never call Acme a platform or a suite.", True)]


def test_undo_of_a_rewrite_is_refused_after_a_later_hand_edit(client: TestClient, brand: int, fake_ai: FakeTransport,
                                                             settings: Settings):
    chat_id = client.post("/api/chats").json()["id"]
    old = client.post(f"/api/brands/{brand}/memory", json={"text": "Hold the hero for Brand.", "kind": "decision"}).json()
    with SessionLocal() as session:
        note = _rewrite_note(session, brand, old, "Use working-room photos for heroes.")
        note.chat_id = chat_id
        session.add(note)
        session.commit()
        note_id = note.id
    client.put(f"/api/memory/{old['id']}", json={"text": "Use working-room photos for every hero, never stock."})

    assert client.post(f"/api/memory/notes/{note_id}/undo").status_code == 409  # used to bring back the old text

    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [i["text"] for i in core] == ["Use working-room photos for every hero, never stock."]


def test_undo_does_not_bring_back_wording_memory_holds_again(client: TestClient, brand: int):
    items = _fill(client, brand, pinned=False)
    chat_id = _planned(client)
    note = _send(client, chat_id, "Never call it a platform.")[-1]
    client.post(f"/api/brands/{brand}/memory", json={"text": items[0]["text"]})  # the dropped wording, added again

    assert client.post(f"/api/memory/notes/{note['id']}/undo").status_code == 204

    texts = [i["text"] for i in client.get(f"/api/brands/{brand}/memory").json()["core"]]
    assert texts.count(items[0]["text"]) == 1  # was 2
    assert "Never call Acme a platform." not in texts
    last = client.get(f"/api/chats/{chat_id}").json()["messages"][-1]
    assert last["content"].startswith("Undone. Not brought back, as memory already holds it again")


# Group 4 of the design review: memory keeps an item's identity; a change never overwrites it

@pytest.mark.parametrize("old, new, changed", [
    ("Keep LinkedIn posts under 150 words.", "Keep LinkedIn posts under 200 words.", True),
    ("Mention pricing in emails.", "Never mention pricing in emails.", True),
    ("Use British spelling in emails.", "Use British spelling in blog posts.", True),
    ("Keep emails brief.", "Emails should be short.", False),  # a real rewording: the model's call
])
def test_a_change_of_number_negation_or_channel_is_never_the_same(old: str, new: str, changed: bool):
    assert changes_meaning(old, new) is changed


def _memory(session, fake_ai: FakeTransport, settings: Settings) -> Memory:
    return Memory(session, AiService(session, fake_ai, settings))


def test_an_item_the_model_calls_the_same_is_not_added_and_the_original_is_untouched(
        client: TestClient, brand: int, fake_ai: FakeTransport, settings: Settings):
    old = client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails brief.", "kind": "preference"}).json()
    with SessionLocal() as session:
        added = _memory(session, fake_ai, settings).add(brand, "Emails should be short.", "preference", 9, same_as=old["id"])

    assert added is None
    core = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [(i["id"], i["text"], i["source_chat_id"]) for i in core] == [(old["id"], "Keep emails brief.", None)]


def test_a_model_same_that_changes_a_number_keeps_both(client: TestClient, brand: int, fake_ai: FakeTransport,
                                                      settings: Settings):
    """The model's "same" used to rewrite the item: 150 became 200 with nothing kept but the note's Undo."""
    old = client.post(f"/api/brands/{brand}/memory", json={"text": "Keep LinkedIn posts under 150 words."}).json()
    with SessionLocal() as session:
        item = _memory(session, fake_ai, settings).add(brand, "Keep LinkedIn posts under 200 words.", "preference", None,
                                                        same_as=old["id"])
        note = remembered_note(item)

    assert item is not None and item.id != old["id"]
    assert "This changes “Keep LinkedIn posts under 150 words.”, which is still in memory" in note.content
    texts = [i["text"] for i in client.get(f"/api/brands/{brand}/memory").json()["core"]]
    assert texts == ["Keep LinkedIn posts under 150 words.", "Keep LinkedIn posts under 200 words."]


def test_a_change_is_kept_beside_the_old_item_until_the_marketer_replaces_it(client: TestClient, brand: int,
                                                                           fake_ai: FakeTransport, settings: Settings):
    chat_id = client.post("/api/chats").json()["id"]
    old = client.post(f"/api/brands/{brand}/memory", json={"text": "Mention pricing in emails."}).json()
    with SessionLocal() as session:
        item = _memory(session, fake_ai, settings).add(brand, "Never mention pricing in emails.", "correction", chat_id,
                                                        changes=old["id"])
        note = remembered_note(item)
        note.chat_id = chat_id
        session.add(note)
        session.commit()
        note_id, new_id = note.id, item.id
    core = lambda: [i["text"] for i in client.get(f"/api/brands/{brand}/memory").json()["core"]]  # noqa: E731
    assert core() == ["Mention pricing in emails.", "Never mention pricing in emails."]  # both, nothing lost

    assert client.post(f"/api/memory/notes/{note_id}/replace").status_code == 204
    assert core() == ["Never mention pricing in emails."]
    assert client.post(f"/api/memory/notes/{note_id}/replace").status_code == 409  # once only

    assert client.post(f"/api/memory/notes/{note_id}/undo").status_code == 204
    after = client.get(f"/api/brands/{brand}/memory").json()["core"]
    assert [(i["id"], i["text"]) for i in after] == [(old["id"], "Mention pricing in emails.")]  # as before
    assert new_id not in [i["id"] for i in after]


def test_the_memory_step_asks_the_model_for_same_and_changes(client: TestClient, brand: int, fake_ai: FakeTransport):
    chat_id = _planned(client)
    _send(client, chat_id, "Never call it a platform.")

    request = _requests(fake_ai, "memory_items")[-1]
    properties = request.output_schema.schema["properties"]["items"]["items"]["properties"]
    assert set(properties) == {"text", "kind", "same_as", "changes"}
    assert "keeping two items is safer than losing one" in request.prompt.fixed
