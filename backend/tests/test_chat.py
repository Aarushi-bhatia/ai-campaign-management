import json

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeTransport
from app.config import Settings
from tests import brand_brain


@pytest.fixture(autouse=True)
def brand(client: TestClient, fake_ai: FakeTransport) -> None:
    fake_ai._default = brand_brain.reply
    response = client.post(
        "/api/brands", data={"name": "Acme"},
        files=[("files", (path, content.encode())) for path, content in brand_brain.BRAND.items()],
    )
    assert response.status_code == 201


def _new_chat(client: TestClient) -> int:
    response = client.post("/api/chats")
    assert response.status_code == 201
    return response.json()["id"]


def _chat_calls(client: TestClient, chat_id: int) -> list[dict]:
    return client.get("/api/ai-calls", params={"chat_id": chat_id}).json()


def test_the_users_message_is_kept_and_the_agent_replies(client: TestClient):
    chat_id = _new_chat(client)

    replies = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Plan a launch"}).json()

    assert all(m["role"] == "assistant" for m in replies)
    messages = client.get(f"/api/chats/{chat_id}").json()["messages"]
    assert (messages[0]["role"], messages[0]["content"]) == ("user", "Plan a launch")


def test_first_message_becomes_the_chat_title(client: TestClient):
    chat_id = _new_chat(client)
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Widget launch\nmore detail"})

    chats = client.get("/api/chats").json()

    assert chats[0]["title"] == "Widget launch"


def test_every_call_is_logged_with_tokens_cost_and_exact_prompt(client: TestClient, fake_ai: FakeTransport):
    chat_id = _new_chat(client)
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Plan a launch"})

    calls = _chat_calls(client, chat_id)
    assert calls
    assert all(c["tokens_in"] > 0 and c["cost_usd"] is not None for c in calls)
    first = client.get(f"/api/ai-calls/{calls[0]['id']}").json()
    review_request = next(r for r in fake_ai.requests if r.output_schema and r.output_schema.name == "brief_review")
    assert first["request"] == review_request.to_payload(for_log=True)
    assert first["model"] == "gpt-6.1-sol"


def test_calls_are_written_to_the_log_file(client: TestClient, settings: Settings):
    chat_id = _new_chat(client)
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "Plan a launch"})

    entries = [json.loads(line) for line in settings.ai_log_file.read_text().splitlines()]

    chat_entries = [e for e in entries if e["chat_id"] == chat_id]
    assert chat_entries[0]["step"] == "Brief review (round 1)"
    assert "Plan a launch" in json.dumps(chat_entries[0]["request"])


def test_failed_ai_call_is_reported_and_still_logged(client: TestClient, fake_ai: FakeTransport):
    def fail(_request):
        raise RuntimeError("rate limited")

    fake_ai._default = fail
    chat_id = _new_chat(client)

    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": "hi"})

    assert response.status_code == 502
    assert "rate limited" in _chat_calls(client, chat_id)[0]["error"]


def test_unknown_chat_is_not_found(client: TestClient):
    assert client.get("/api/chats/999").status_code == 404
    assert client.post("/api/chats/999/messages", json={"content": "hi"}).status_code == 404


def test_markdown_marks_are_left_out_of_the_title(client: TestClient):
    chat_id = _new_chat(client)
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "\n# Campaign brief: **Widget** launch\nmore"})

    assert client.get("/api/chats").json()[0]["title"] == "Campaign brief: Widget launch"
