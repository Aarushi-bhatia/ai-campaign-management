"""A failed AI call mid-campaign must never leave the campaign stuck. Regression tests from the code review."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.fake import FakeTransport
from app.ai.models import AiCall
from app.ai.prompt import Prompt
from app.ai.service import AiCallFailed, AiService
from app.ai.transport import AiRequest
from app.campaign.models import Campaign
from app.chat.models import Chat
from app.config import ModelSize
from app.db import SessionLocal
from tests import brand_brain


@pytest.fixture(autouse=True)
def brand(client: TestClient, fake_ai: FakeTransport) -> int:
    fake_ai._default = brand_brain.reply
    response = client.post("/api/brands", data={"name": "Acme"},
                           files=[("files", (p, c.encode())) for p, c in brand_brain.BRAND.items()])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _fail_once(fake_ai: FakeTransport, schema: str) -> None:
    """The next call with this output shape fails, as a timeout or outage would."""
    state = {"failed": False}

    def reply(request: AiRequest):
        if not state["failed"] and request.output_schema and request.output_schema.name == schema:
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = reply


def _campaign(client: TestClient, chat_id: int) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()["campaign"]


def test_planning_that_fails_after_the_last_answer_can_be_retried(client: TestClient, fake_ai: FakeTransport):
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Do an awareness push."})  # two questions
    client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 0, "answer": "Platform leads"})
    _fail_once(fake_ai, "campaign_plan")

    failed = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 1, "answer": "Q1"})
    assert failed.status_code == 502
    assert _campaign(client, chat_id)["stage"] == "asking"  # every question answered, but no plan

    retry = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Try again"})

    assert retry.status_code == 201, retry.text  # was 400 "There is no open question." for good
    assert retry.json()[-1]["kind"] == "plan"
    assert _campaign(client, chat_id)["stage"] == "plan_ready"


def _planned(client: TestClient) -> int:
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages",
                json={"content": "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."})
    return chat_id


def test_a_failure_before_any_asset_is_written_does_not_leave_the_campaign_writing(client: TestClient,
                                                                                   fake_ai: FakeTransport):
    chat_id = _planned(client)
    _fail_once(fake_ai, "writing_rules")  # the first AI call of the writing job, outside any one asset

    client.post(f"/api/chats/{chat_id}/approve")

    assert _campaign(client, chat_id)["stage"] == "done"  # was stuck at "writing", with the chat locked
    assets = client.get(f"/api/chats/{chat_id}/assets").json()
    assert [a["state"] for a in assets] == ["failed", "failed", "failed"]
    last = client.get(f"/api/chats/{chat_id}").json()["messages"][-1]
    assert "Writing stopped: The AI service is down" in last["content"]


def test_write_again_recovers_after_such_a_failure(client: TestClient, fake_ai: FakeTransport):
    chat_id = _planned(client)
    _fail_once(fake_ai, "writing_rules")
    client.post(f"/api/chats/{chat_id}/approve")

    assert client.post(f"/api/chats/{chat_id}/write").status_code == 200

    assert [a["state"] for a in client.get(f"/api/chats/{chat_id}/assets").json()] == ["done", "done", "done"]
    assert _campaign(client, chat_id)["stage"] == "done"


def test_a_document_with_a_very_long_path_is_read(client: TestClient):
    """The bug: the step label holds the file path, the log column holds 200 characters, and a longer label
    made the log insert fail, which failed the whole brand read."""
    deep = "acme/" + "/".join(["a-very-long-folder-name-for-regional-campaigns"] * 6) + "/partner-guide.md"
    assert len(deep) > 250
    files = {**brand_brain.BRAND, deep: "# Partner guide\n\nWrite short sentences for partners.\n"}

    response = client.post("/api/brands", data={"name": "Deep"},
                           files=[("files", (path, text.encode())) for path, text in files.items()])

    brand = client.get(f"/api/brands/{response.json()['id']}").json()
    assert brand["status"] == "ready"
    steps = [c["step"] for c in client.get("/api/ai-calls").json()]
    long_one = next(s for s in steps if s.startswith("Brand reading: document card") and "partner-guide.md" in s)
    assert len(long_one) <= 200 and "…" in long_one  # the end of the path is kept, so it's still recognisable


# Group 1 of the design review: logging an AI call must not save, or roll back, the caller's work.

def test_logging_an_ai_call_does_not_save_the_callers_unfinished_work(client: TestClient, settings):
    chat_id = client.post("/api/chats").json()["id"]
    with SessionLocal() as session:
        chat = session.get_one(Chat, chat_id)
        chat.title = "Not saved yet"
        reply = AiService(session, FakeTransport(default="Hi"), settings, SessionLocal).complete(
            step="Probe", size=ModelSize.SMALL, prompt=Prompt(fixed="Say hi."), chat_id=chat_id)
        with SessionLocal() as other:
            assert other.get_one(Chat, chat_id).title != "Not saved yet"  # the log's commit used to save it
            assert other.get_one(AiCall, reply.call_id).response_text == "Hi"
        session.rollback()


def test_a_failed_ai_call_is_still_logged_when_the_caller_rolls_back(client: TestClient, settings):
    chat_id = client.post("/api/chats").json()["id"]
    broken = FakeTransport(default=lambda request: (_ for _ in ()).throw(RuntimeError("The AI service is down")))
    with SessionLocal() as session:
        session.get_one(Chat, chat_id).title = "Rolled back"
        with pytest.raises(AiCallFailed) as failed:
            AiService(session, broken, settings, SessionLocal).complete(
                step="Probe", size=ModelSize.SMALL, prompt=Prompt(fixed="Say hi."), chat_id=chat_id)
        session.rollback()
    with SessionLocal() as session:
        call = session.get_one(AiCall, failed.value.call_id)
        assert "The AI service is down" in call.error
        assert session.get_one(Chat, chat_id).title != "Rolled back"


def test_a_failed_brief_review_saves_nothing_but_the_message(client: TestClient, fake_ai: FakeTransport, brand: int):
    """With a core memory, the review step used to save the brief and its "Using 1 thing you told me" note
    before the review call, so a failed review left them behind."""
    client.post(f"/api/brands/{brand}/memory", json={"text": "Keep emails short.", "kind": "preference"})
    chat_id = client.post("/api/chats").json()["id"]
    _fail_once(fake_ai, "brief_review")

    failed = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Launch the widget."})

    assert failed.status_code == 502
    chat = client.get(f"/api/chats/{chat_id}").json()
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [("user", "Launch the widget.")]
    with SessionLocal() as session:
        campaign = session.scalars(select(Campaign).where(Campaign.chat_id == chat_id)).one()
        assert (campaign.stage, campaign.brief, campaign.memories_used, campaign.questions) == ("brief", "", [], [])
    with SessionLocal() as session:  # the failed review call itself is logged
        assert session.scalar(select(AiCall).where(AiCall.chat_id == chat_id, AiCall.error.is_not(None))) is not None

    retry = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Launch the widget."})
    assert retry.status_code == 201, retry.text
