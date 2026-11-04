"""Memory across campaigns: core memory in every prompt, campaign history only at planning."""

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeTransport
from app.ai.service import AiService
from app.campaign import agent
from app.campaign.writing import remembered_note
from app.config import Settings
from app.db import SessionLocal
from app.brand.images.picking import AssetSpec, rank_prompt
from app.memory.models import CampaignRecord
from app.memory.service import HISTORY_IN_PLANNING, Memory, history, near_duplicate, recent_images, undo_remembered
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


def test_a_rewritten_item_keeps_its_old_text_and_undo_brings_it_back(client: TestClient, brand: int,
                                                                      fake_ai: FakeTransport, settings: Settings):
    old = client.post(f"/api/brands/{brand}/memory", json={"text": "Hold the hero for Brand.", "kind": "decision"}).json()
    with SessionLocal() as session:
        memory = Memory(session, AiService(session, fake_ai, settings))
        item = memory.add(brand, "Use working-room photos for heroes.", "correction", None, replaces=old["id"])
        note = remembered_note(item)

        assert note.content == "Remembered: Use working-room photos for heroes. (this replaces “Hold the hero for Brand.”)"
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


def test_a_near_duplicate_updates_the_item_instead_of_adding_one(client: TestClient, brand: int):
    client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails short."})

    same = client.post(f"/api/brands/{brand}/memory", json={"text": "Emails should be short."}).json()
    other = client.post(f"/api/brands/{brand}/memory", json={"text": "Never call it a toolkit."})
    other_again = client.post(f"/api/brands/{brand}/memory", json={"text": "Never call it a platform."})

    assert same["replaced"] == "Keep emails short."
    assert other.status_code == other_again.status_code == 201  # different instructions stay apart
    texts = [i["text"] for i in client.get(f"/api/brands/{brand}/memory").json()["core"]]
    assert texts == ["Emails should be short.", "Never call it a toolkit.", "Never call it a platform."]


@pytest.mark.parametrize("old, new, merged", [
    ("Keep emails short.", "Emails should be short.", True),
    ("Never mention pricing in social posts.", "Always mention pricing in social posts.", True),
    ("Keep LinkedIn posts under 150 words.", "Keep X posts under 150 words.", False),
    ("Use British spelling in emails.", "Use British spelling in blog posts.", False),
    ("Never call it a platform.", "Never call it a toolkit.", False),
])
def test_only_added_or_dropped_words_count_as_a_near_duplicate(old: str, new: str, merged: bool):
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
