"""Two actions on the same brand, campaign or asset at once: only one may win. Regression tests from the
race-condition review (H1 to H3)."""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

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
from app.research.client import FakeWebResearch, WebPage
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


# Group 2 of the design review: a slow plan step, and a change made while it ran

PAGE = WebPage("https://example.org/widgets", "Widget report", "Intro. The widget market grew 12% in 2026. More text.",
               "2026-05-01")
OTHER = WebPage("https://other.example/report", "Another report", "The widget market grew 12% in 2026. Other text.",
                "2026-06-01")


def _campaign(client: TestClient, chat_id: int) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()["campaign"]


def _researched(client: TestClient, fake_web: FakeWebResearch) -> int:
    fake_web._pages = lambda query: [PAGE]
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"content": f"{BRIEF} Plan it with research."})
    return chat_id


def test_a_better_source_that_finishes_after_approval_changes_nothing(client: TestClient, fake_web: FakeWebResearch):
    """The reviewer's probe: the old finding ended up removed while an asset cited it, and the new one was never
    used, because Better source saved its result on a campaign that was already approved."""
    chat_id = _researched(client, fake_web)
    before = _campaign(client, chat_id)["research"]

    def approve_meanwhile(query: str) -> list[WebPage]:
        assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200
        return [PAGE, OTHER]

    fake_web._pages = approve_meanwhile
    reply = client.post(f"/api/chats/{chat_id}/research/{before[0]['id']}/better")

    assert reply.status_code < 300, reply.text
    assert "The plan changed while I was working" in reply.json()[-1]["content"]
    campaign = _campaign(client, chat_id)
    assert campaign["research"] == before  # was: old finding removed, new one added
    cited = {url for asset in _assets(client, chat_id) for url in asset["content"]["sources"]}
    assert cited <= {f["url"] for f in campaign["research"] if not f["removed"]}


def test_a_chat_plan_edit_that_finishes_after_approval_changes_nothing(client: TestClient, fake_ai: FakeTransport):
    chat_id = _planned(client)
    before = _campaign(client, chat_id)["plan"]

    def approve_during_the_edit(request: AiRequest):
        if request.output_schema and request.output_schema.name == "plan_edit":
            fake_ai._default = brand_brain.reply
            assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200
        return brand_brain.reply(request)

    fake_ai._default = approve_during_the_edit
    reply = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Swap the X post for a blog post"})

    assert "The plan changed while I was working" in reply.json()[-1]["content"]
    assert _campaign(client, chat_id)["plan"] == before
    assert [a["type"] for a in _assets(client, chat_id)] == [card["type"] for card in before["assets"]]


def test_a_card_change_made_on_an_older_plan_is_refused(client: TestClient):
    """The cards send the whole list: saving one shown before a chat edit added a card used to delete it."""
    chat_id = _planned(client)
    shown = _campaign(client, chat_id)
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Swap the X post for a blog post"})
    edited = _campaign(client, chat_id)["plan"]
    assert "blog_post" in [card["type"] for card in edited["assets"]]

    stale = client.put(f"/api/chats/{chat_id}/plan", json={"assets": shown["plan"]["assets"][:2],
                                                           "base_version": shown["plan_version"]})

    assert stale.status_code == 409
    assert _campaign(client, chat_id)["plan"] == edited
    fresh = client.put(f"/api/chats/{chat_id}/plan", json={"assets": edited["assets"][:2],
                                                           "base_version": _campaign(client, chat_id)["plan_version"]})
    assert fresh.status_code == 200


def test_a_plan_whose_research_changed_since_it_was_shown_is_not_approved(client: TestClient, fake_web: FakeWebResearch):
    chat_id = _researched(client, fake_web)
    shown = _campaign(client, chat_id)
    client.delete(f"/api/chats/{chat_id}/research/{shown['research'][0]['id']}")  # moves the plan version on

    stale = client.post(f"/api/chats/{chat_id}/approve?base_version={shown['plan_version']}")

    assert stale.status_code == 409
    assert _campaign(client, chat_id)["stage"] == "plan_ready"
    latest = _campaign(client, chat_id)["plan_version"]
    assert client.post(f"/api/chats/{chat_id}/approve?base_version={latest}").status_code == 200


def test_two_answers_to_the_same_question_at_once_make_one_plan(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Do an awareness push."})  # two questions
    client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 0, "answer": "Platform leads"})
    mark = CampaignService._mark_card_answered

    def slow_mark(self, *args):  # widens the gap between reading the question and saving the answer
        time.sleep(0.3)
        mark(self, *args)

    monkeypatch.setattr(CampaignService, "_mark_card_answered", slow_mark)
    answer = lambda: client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 1, "answer": "Q1"}).status_code
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(answer)
        time.sleep(0.1)
        second = pool.submit(answer)
        codes = sorted([first.result(), second.result()])

    assert codes == [201, 400]  # both used to pass, posting two plans
    plans = [m for m in client.get(f"/api/chats/{chat_id}").json()["messages"] if m["kind"] == "plan"]
    assert len(plans) == 1


def test_check_again_does_not_put_old_warnings_on_a_newer_hand_edit(client: TestClient, fake_ai: FakeTransport):
    chat_id, linkedin = _written(client)
    url = f"/api/chats/{chat_id}/assets/{linkedin['id']}"
    typed = {**linkedin["content"], "text": "Typed by hand while the check ran."}

    def hand_edit_during_the_check(request: AiRequest):
        if request.output_schema and request.output_schema.name == "asset_check":
            fake_ai._default = brand_brain.reply
            assert client.put(url, json={"content": typed, "base_version": linkedin["version"]}).status_code == 200
        return brand_brain.reply(request)

    fake_ai._default = hand_edit_during_the_check
    checked = client.post(f"{url}/check")
    hand_edited = _assets(client, chat_id)[1]

    assert checked.status_code == 409
    assert "changed while it was being checked" in checked.json()["detail"]
    assert hand_edited["content"]["text"] == "Typed by hand while the check ran."
    assert hand_edited["warnings"] == _versions(client, chat_id, linkedin["id"])[-1]["warnings"]
