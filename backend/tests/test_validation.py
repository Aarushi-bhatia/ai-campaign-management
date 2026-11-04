"""Inputs and stage changes are checked at the API, not only in the UI or on the AI's path, and rules are taken
from structured answers, not wording. Regression tests for Groups 6 and 7 of the design review. Fake AI and fake
web search only."""

from types import SimpleNamespace

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.fake import FakeTransport
from app.ai.transport import AiRequest
from app.brand.images import library
from app.brand.images.picking import PickResult
from app.campaign.agent import _options, at_least_two, channels_mentioned, plan_problem
from app.campaign.models import Campaign
from app.campaign.research import CampaignResearch
from app.db import SessionLocal
from app.research.client import FakeWebResearch, _iso_date
from tests import brand_brain

BRIEF = "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."


@pytest.fixture(autouse=True)
def brand(client: TestClient, fake_ai: FakeTransport) -> int:
    fake_ai._default = brand_brain.reply
    response = client.post("/api/brands", data={"name": "Acme"},
                           files=[("files", (p, c.encode())) for p, c in brand_brain.BRAND.items()])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _planned(client: TestClient) -> int:
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"content": BRIEF})
    return chat_id


def _campaign(client: TestClient, chat_id: int) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()["campaign"]


def _messages(client: TestClient, chat_id: int) -> list[dict]:
    return client.get(f"/api/chats/{chat_id}").json()["messages"]


# The plan: one set of rules for every path

def test_the_x_channel_is_not_found_inside_other_words():
    """A file named context.md used to add X posts to a brand with only email and LinkedIn playbooks (#7)."""
    text = "acme/channels/email-playbook.md acme/channels/linkedin.md acme/context.md index text example"

    assert channels_mentioned(text) == ["email", "linkedin"]
    assert "x" in channels_mentioned("acme/channels/x-playbook.md")
    assert "x" in channels_mentioned("Rules for X posts and the email newsletter")


def test_plan_cards_with_the_same_id_twice_are_refused(client: TestClient):
    """They used to be saved and then written as two assets with one plan id (#8)."""
    chat_id = _planned(client)
    campaign = _campaign(client, chat_id)
    first = campaign["plan"]["assets"][0]

    response = client.put(f"/api/chats/{chat_id}/plan", json={"assets": [first, first],
                                                              "base_version": campaign["plan_version"]})

    assert response.status_code == 400 and "only once" in response.json()["detail"]
    assert _campaign(client, chat_id)["plan"] == campaign["plan"]


def test_a_card_for_a_channel_the_brand_does_not_use_is_refused():
    cards = [{"id": "a1", "type": "email", "title": "Launch email"}, {"id": "a2", "type": "x_post", "title": "Post"}]

    assert plan_problem(cards, ["email", "linkedin"]) == (
        "The brand's documents don't cover the x channel, so “Post” can't be planned.")
    assert plan_problem(cards, ["email", "x"]) is None


def test_an_empty_plan_can_be_neither_saved_nor_approved(client: TestClient):
    """The UI disabled the button, but the API approved a plan with no assets, ending at done with nothing (#20)."""
    chat_id = _planned(client)
    version = _campaign(client, chat_id)["plan_version"]

    assert client.put(f"/api/chats/{chat_id}/plan", json={"assets": [], "base_version": version}).status_code == 400
    with SessionLocal() as session:  # as a plan from the model with no usable cards would be
        campaign = session.scalars(select(Campaign).where(Campaign.chat_id == chat_id)).one()
        campaign.plan = {**campaign.plan, "assets": []}
        session.commit()

    response = client.post(f"/api/chats/{chat_id}/approve")

    assert response.status_code == 400 and "at least one asset" in response.json()["detail"]
    assert _campaign(client, chat_id)["stage"] == "plan_ready"


# Questions: only answered at the stage they were asked at, always with a real choice

def test_a_plan_question_left_open_expires_when_the_plan_is_approved(client: TestClient):
    """It could be answered after approval, and the answer was then sent to the asset editor (#35)."""
    chat_id = _planned(client)
    card = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Make it better"}).json()[-1]
    assert card["kind"] == "question" and card["data"]["question"] == "Better how?"

    client.post(f"/api/chats/{chat_id}/approve")
    response = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": card["data"]["id"], "answer": "Shorter"})

    assert response.status_code == 409 and "no longer applies" in response.json()["detail"]
    shown = next(m for m in _messages(client, chat_id) if m["id"] == card["id"])
    assert shown["data"]["expired"] is True
    assert not any(m["kind"] == "edit" for m in _messages(client, chat_id))


def test_an_open_plan_question_from_before_questions_had_a_stage_also_expires(client: TestClient):
    chat_id = _planned(client)
    client.post(f"/api/chats/{chat_id}/approve")
    with SessionLocal() as session:  # an open plan-edit question saved before questions recorded their stage
        campaign = session.scalars(select(Campaign).where(Campaign.chat_id == chat_id)).one()
        campaign.questions = [*campaign.questions, {"kind": "unclear", "question": "Better how?", "why": "",
                                                    "source_path": "", "quote": "", "answer": None,
                                                    "options": [{"label": "Shorter", "value": "Shorter"}]}]
        session.commit()
        index = len(campaign.questions) - 1

    response = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": index, "answer": "Shorter"})

    assert response.status_code == 409


def test_a_question_card_always_offers_two_choices():
    """With no usable options it used to offer only "You decide" (#36)."""
    assert [o["label"] for o in _options(["  ", ""])] == ["You decide", "Leave it as it is"]
    assert [o["label"] for o in _options(["Shorter"])] == ["Shorter", "You decide"]
    assert at_least_two(["All of them"]) == ["All of them", "You decide"]
    assert at_least_two(["You decide"]) == ["You decide", "Leave it as it is"]


# A failed brief review can be tried again without typing

def test_try_again_reviews_the_brief_already_sent(client: TestClient, fake_ai: FakeTransport):
    """Typing "try again" used to become the brief (#34)."""
    chat_id = client.post("/api/chats").json()["id"]
    state = {"failed": False}

    def review_fails_once(request: AiRequest):
        if not state["failed"] and request.output_schema and request.output_schema.name == "brief_review":
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = review_fails_once
    assert client.post(f"/api/chats/{chat_id}/messages", json={"content": BRIEF}).status_code == 502

    retried = client.post(f"/api/chats/{chat_id}/review")

    assert retried.status_code == 201, retried.text
    campaign = _campaign(client, chat_id)
    assert campaign["stage"] == "plan_ready" and campaign["brief"] == BRIEF
    assert [m["content"] for m in _messages(client, chat_id) if m["role"] == "user"] == [BRIEF]
    assert client.post(f"/api/chats/{chat_id}/review").status_code == 409  # nothing left to retry


# Research, dates, typed content, hand fixes, uploads

def test_research_asked_for_no_asset_is_not_searched(fake_web: FakeWebResearch):
    """Its findings would have counted for no asset, yet the chat said "N findings" (#31)."""
    searched = []
    fake_web._pages = lambda query: searched.append(query) or []
    campaign = SimpleNamespace(research=[], searches=[], chat_id=1, brand_id=1)

    lines = CampaignResearch(None, fake_web, "Acme", campaign).on_request("widget market", [])

    assert searched == [] and campaign.research == []
    assert lines == ["I didn't search for “widget market”: say which asset the research is for."]


@pytest.mark.parametrize("written, shown", [
    ("2026-05-15T09:30:00Z", "2026-05-15"),
    ("May 15, 2026", "2026-05-15"),  # was "May 15, 20"
    ("15 May 2026", "2026-05-15"),
    ("Fri, 15 May 2026 09:30:00 GMT", "2026-05-15"),
    ("Spring 2026", "Spring 2026"),  # unreadable: kept whole
])
def test_page_dates_are_read_or_kept_whole(written: str, shown: str):
    assert _iso_date(written) == shown


def _written(client: TestClient) -> tuple[int, dict]:
    chat_id = _planned(client)
    client.post(f"/api/chats/{chat_id}/approve")
    return chat_id, client.get(f"/api/chats/{chat_id}/assets").json()


@pytest.mark.parametrize("index, change, problem", [
    (1, {"sources": None}, "sources must be a list"),  # was a 500
    (0, {"sections": ["Just a string"]}, "sections 1 must have the fields heading, body"),
    (1, {"hashtags": "launch"}, "hashtags must be a list"),
])
def test_typed_content_of_the_wrong_shape_is_refused(client: TestClient, index: int, change: dict, problem: str):
    """A hand edit with a field of the wrong shape used to crash the free checks with a 500 (#40)."""
    chat_id, assets = _written(client)
    asset = assets[index]

    response = client.put(f"/api/chats/{chat_id}/assets/{asset['id']}",
                          json={"content": {**asset["content"], **change}, "base_version": asset["version"]})

    assert response.status_code == 422 and problem in response.json()["detail"]
    assert client.get(f"/api/chats/{chat_id}/assets").json()[index]["version"] == asset["version"]


def test_the_same_swap_twice_in_one_save_counts_once(client: TestClient):
    """It counted as two, so "Remember this?" came after a single hand edit (#41)."""
    chat_id, assets = _written(client)
    post = assets[1]
    url = f"/api/chats/{chat_id}/assets/{post['id']}"
    client.put(url, json={"content": {**post["content"], "text": "Our platform is the best platform for teams."},
                          "base_version": post["version"]})
    post = client.get(f"/api/chats/{chat_id}/assets").json()[1]

    saved = client.put(url, json={"content": {**post["content"], "text": "Our toolkit is the best toolkit for teams."},
                                  "base_version": post["version"]}).json()

    assert not any(m["kind"] == "remember_offer" for m in saved["messages"])
    with SessionLocal() as session:
        campaign = session.scalars(select(Campaign).where(Campaign.chat_id == chat_id)).one()
        assert campaign.hand_fixes["platform → toolkit"] == 1


def test_an_upload_with_a_file_that_is_also_a_folder_is_refused_before_anything_is_saved(client: TestClient,
                                                                                         brand: int, settings):
    """It used to fail halfway with a 500, after some files were already written (#37)."""
    files = [("files", ("acme/aaa-first.md", b"# First\n\nWritten first.\n")), ("files", ("acme/a.md", b"# A\n")),
             ("files", ("acme/a.md/b.md", b"# B\n"))]

    created = client.post("/api/brands", data={"name": "Clash"}, files=files)
    updated = client.post(f"/api/brands/{brand}/files", files=files)

    assert created.status_code == 400 and "both a file and a folder" in created.json()["detail"]
    assert updated.status_code == 400
    assert [b["name"] for b in client.get("/api/brands").json()].count("Clash") == 0
    assert client.get(f"/api/brands/{brand}").json()["status"] == "ready"  # not left stuck reading
    assert not list(settings.data_dir.rglob("aaa-first.md"))  # nothing was written


# Rules from structured answers, not from wording (Group 7)

def test_the_image_types_a_brief_rules_out_are_on_the_plan_and_block_those_images(client: TestClient,
                                                                                 monkeypatch: pytest.MonkeyPatch):
    """The brief's image rules used to be only a hint to the ranking model, so a screenshot could still be
    picked (#16). An exclusion whose quote isn't in the brief is dropped: it would hide images unseen."""
    specs = []
    monkeypatch.setattr(library, "pick", lambda session, ai, brand, spec, **kwargs: specs.append(spec) or PickResult())
    chat_id = _planned_with(client, f"{BRIEF} No screenshots.")

    assert _campaign(client, chat_id)["plan"]["image_exclusions"] == [
        {"image_type": "product_screenshot", "quote": "No screenshots"}]
    client.post(f"/api/chats/{chat_id}/approve")
    assert specs and all(spec.excluded_types == {"product_screenshot"} for spec in specs)


def test_a_wrong_image_exclusion_can_be_removed_on_the_plan(client: TestClient):
    chat_id = _planned_with(client, f"{BRIEF} No screenshots.")
    campaign = _campaign(client, chat_id)

    response = client.put(f"/api/chats/{chat_id}/plan", json={
        "assets": campaign["plan"]["assets"], "base_version": campaign["plan_version"], "image_exclusions": []})

    assert response.status_code == 200, response.text
    assert response.json()["plan"]["image_exclusions"] == []
    again = response.json()
    client.put(f"/api/chats/{chat_id}/plan", json={  # one can't be added this way
        "assets": again["plan"]["assets"], "base_version": again["plan_version"], "image_exclusions": ["logo"]})
    assert _campaign(client, chat_id)["plan"]["image_exclusions"] == []


def test_a_chat_edit_keeps_the_image_exclusions(client: TestClient):
    chat_id = _planned_with(client, f"{BRIEF} No screenshots.")

    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Drop the X post"})

    assert [e["image_type"] for e in _campaign(client, chat_id)["plan"]["image_exclusions"]] == ["product_screenshot"]


@pytest.mark.parametrize("allowed, warned", [(2, False), (0, True), (None, False)])
def test_the_hashtag_limit_is_the_number_the_writing_rules_give(client: TestClient, fake_ai: FakeTransport,
                                                                allowed: int | None, warned: bool):
    """A wording regex used to decide, and fired on rules that allow hashtags (#14)."""
    def reply(request: AiRequest):
        if request.output_schema and request.output_schema.name == "writing_rules":
            limits = [] if allowed is None else [{"channel": "x", "max": allowed, "quote": "Write short sentences."}]
            return json.dumps({"banned": [], "old_names": [], "limits": [], "hashtags": limits})
        return brand_brain.reply(request)

    fake_ai._default = reply
    chat_id, assets = _written(client)
    post = next(a for a in assets if a["type"] == "x_post")

    saved = client.put(f"/api/chats/{chat_id}/assets/{post['id']}", json={
        "content": {**post["content"], "hashtags": ["launch", "widget"]}, "base_version": post["version"]})

    assert saved.status_code == 200, saved.text
    after = next(a for a in client.get(f"/api/chats/{chat_id}/assets").json() if a["id"] == post["id"])
    assert any(w["check"] == "hashtags" for w in after["warnings"]) is warned


def _planned_with(client: TestClient, brief: str) -> int:
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"content": brief})
    return chat_id


def test_a_hashtag_limit_is_kept_only_with_its_quote():
    from app.brand.writing_rules import checked
    source = "=== LENGTH AND HASHTAG RULES ===\nX | hashtags: 0–2, at the end | x"
    raw = {"banned": [], "old_names": [], "limits": [], "hashtags": [
        {"channel": "x", "max": 2, "quote": "hashtags: 0–2, at the end"},
        {"channel": "linkedin", "max": 0, "quote": "No hashtags on LinkedIn."}]}  # not in the source

    assert checked(raw, source)["hashtags"] == [{"channel": "x", "max": 2}]
