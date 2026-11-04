"""Two actions on the same brand, campaign or asset at once: only one may win. Regression tests from the
race-condition review (H1 to H3)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeTransport
from app.ai.service import AiService
from app.ai.transport import AiRequest
from app.campaign.runtime import Runtime
from app.campaign.service import CampaignService
from app.campaign.stages import WrongStage
from app.chat.models import Chat
from app.config import Settings
from app.db import SessionLocal
from app.jobs import get_job_runner
from tests import brand_brain

BRIEF = "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."


class RecordingJobs:
    """Keeps background jobs instead of running them, so a test can see how many were started."""

    def __init__(self) -> None:
        self.jobs: list[Callable[[], None]] = []

    def submit(self, job: Callable[[], None]) -> None:
        self.jobs.append(job)


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


def _assets(client: TestClient, chat_id: int) -> list[dict]:
    return client.get(f"/api/chats/{chat_id}/assets").json()


def _versions(client: TestClient, chat_id: int, asset_id: int) -> list[dict]:
    return client.get(f"/api/chats/{chat_id}/assets/{asset_id}/versions").json()


# H1: brand reads


def test_a_second_read_of_a_brand_that_is_reading_is_refused(client: TestClient, brand: int):
    recorded = RecordingJobs()
    client.app.dependency_overrides[get_job_runner] = lambda: recorded  # the first read stays "running"

    first = client.post(f"/api/brands/{brand}/read")
    again = client.post(f"/api/brands/{brand}/read")
    summary = client.post(f"/api/brands/{brand}/summary/rebuild")
    files = client.post(f"/api/brands/{brand}/files", files=[("files", ("acme/new.md", b"# New\n\nMore.\n"))])

    assert first.status_code == 200, first.text
    assert again.status_code == summary.status_code == files.status_code == 409
    assert "already being read" in again.json()["detail"]
    assert len(recorded.jobs) == 1  # was one job per click, all reading the same brand side by side


def test_a_brand_can_be_read_again_once_the_first_read_finishes(client: TestClient, brand: int):
    assert client.get(f"/api/brands/{brand}").json()["status"] == "ready"
    assert client.post(f"/api/brands/{brand}/read").status_code == 200
    assert client.post(f"/api/brands/{brand}/summary/rebuild").status_code == 200


# H2: approving or writing twice


def _stale_service(chat_id: int, fake_ai: FakeTransport, settings: Settings, jobs: RecordingJobs):
    """A second request that loaded the campaign before the first one changed it, as another tab would."""
    session = SessionLocal()
    chat = session.get(Chat, chat_id)
    runtime = Runtime(SessionLocal, fake_ai, settings, jobs, None)
    service = CampaignService(session, AiService(session, fake_ai, settings), runtime)
    campaign = service.get(chat)  # loads the campaign as it is now; held, as a request holds it, so it stays stale
    list(campaign.assets)  # its assets too
    return session, service, chat, campaign


def test_a_second_approve_of_the_same_plan_is_refused(client: TestClient, fake_ai: FakeTransport, settings: Settings):
    chat_id = _planned(client)
    stale_jobs = RecordingJobs()
    session, stale, chat, seen = _stale_service(chat_id, fake_ai, settings, stale_jobs)
    try:
        assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200

        assert seen.stage == "plan_ready"
        with pytest.raises(WrongStage):
            stale.approve(chat)  # still sees "plan ready" in its copy
    finally:
        session.close()

    assert len(_assets(client, chat_id)) == 3  # one set of assets, not two
    assert stale_jobs.jobs == []  # no second writing job
    notes = [m for m in client.get(f"/api/chats/{chat_id}").json()["messages"] if m["content"].startswith("Plan approved")]
    assert len(notes) == 1


def test_a_second_write_again_is_refused(client: TestClient, fake_ai: FakeTransport, settings: Settings):
    chat_id = _planned(client)
    state = {"failed": False}

    def fail_once(request: AiRequest):
        if not state["failed"] and request.output_schema and request.output_schema.name == "writing_rules":
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = fail_once
    client.post(f"/api/chats/{chat_id}/approve")  # every asset fails; the campaign ends at done
    stale_jobs = RecordingJobs()
    session, stale, chat, seen = _stale_service(chat_id, fake_ai, settings, stale_jobs)
    try:
        assert client.post(f"/api/chats/{chat_id}/write").status_code == 200

        assert seen.stage == "done" and {a.state for a in seen.assets} == {"failed"}
        with pytest.raises(WrongStage):
            stale.begin_writing(chat)  # still sees "done" with failed assets in its copy
    finally:
        session.close()

    assert stale_jobs.jobs == []
    assert [a["state"] for a in _assets(client, chat_id)] == ["done", "done", "done"]


# H3: a slow chat edit and a change made while it ran


def _written(client: TestClient) -> tuple[int, dict]:
    chat_id = _planned(client)
    assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200
    return chat_id, _assets(client, chat_id)[1]  # the LinkedIn post


def _during_the_chat_edit(fake_ai: FakeTransport, action: Callable[[], None]) -> None:
    """Runs `action` while the chat edit's AI call is still out, as a user acting in the meantime would."""
    state = {"done": False}

    def reply(request: AiRequest):
        extra = request.output_schema.schema["properties"] if request.output_schema else {}
        if not state["done"] and "changed" in extra:
            state["done"] = True
            action()
        return brand_brain.reply(request)

    fake_ai._default = reply


def test_a_chat_edit_does_not_overwrite_a_hand_edit_made_while_it_ran(client: TestClient, fake_ai: FakeTransport):
    chat_id, linkedin = _written(client)
    typed = {**linkedin["content"], "text": "Typed by hand while the AI was busy."}
    url = f"/api/chats/{chat_id}/assets/{linkedin['id']}"
    _during_the_chat_edit(fake_ai, lambda: client.put(url, json={"content": typed, "base_version": linkedin["version"]}))

    reply = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Shorten the second post"}).json()[-1]

    after = _assets(client, chat_id)[1]
    assert after["content"]["text"] == "Typed by hand while the AI was busy."  # was replaced by the chat edit
    assert [v["reason"] for v in _versions(client, chat_id, linkedin["id"])][-1] == "hand edit"
    assert "changed while I was editing it" in reply["content"]


def test_a_chat_edit_does_not_undo_an_undo_made_while_it_ran(client: TestClient, fake_ai: FakeTransport):
    chat_id, linkedin = _written(client)
    url = f"/api/chats/{chat_id}/assets/{linkedin['id']}"
    client.put(url, json={"content": {**linkedin["content"], "text": "A hand edit."}, "base_version": linkedin["version"]})
    edited = _assets(client, chat_id)[1]
    _during_the_chat_edit(fake_ai, lambda: client.post(f"{url}/undo?base_version={edited['version']}"))

    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Shorten the second post"})

    assert _assets(client, chat_id)[1]["content"] == linkedin["content"]  # the undo stands
    numbers = [v["number"] for v in _versions(client, chat_id, linkedin["id"])]
    assert len(numbers) == len(set(numbers))


def test_saving_a_hand_edit_started_before_a_newer_version_is_refused(client: TestClient):
    chat_id, linkedin = _written(client)
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Shorten the second post"})  # a newer version lands
    url = f"/api/chats/{chat_id}/assets/{linkedin['id']}"

    stale_save = client.put(url, json={"content": {**linkedin["content"], "text": "Old draft."},
                                       "base_version": linkedin["version"]})
    stale_undo = client.post(f"{url}/undo?base_version={linkedin['version']}")
    stale_restore = client.post(f"{url}/versions/{linkedin['version']}/restore?base_version={linkedin['version']}")

    assert stale_save.status_code == stale_undo.status_code == stale_restore.status_code == 409
    assert "changed while this was being done" in stale_save.json()["detail"]
    assert _assets(client, chat_id)[1]["content"]["text"] == "Short."  # the chat edit was kept
