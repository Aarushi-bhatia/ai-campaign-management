"""Brief, questions, push-back, plan and approval, through the chat API with a fake agent."""

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeTransport
from tests import brand_brain

CLEAR_BRIEF = "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."


@pytest.fixture(autouse=True)
def brain(fake_ai: FakeTransport) -> None:
    fake_ai._default = brand_brain.reply


def _brand(client: TestClient, extra: dict[str, str] | None = None) -> int:
    files = {**brand_brain.BRAND, **(extra or {})}
    response = client.post(
        "/api/brands", data={"name": "Acme", "exclude": ["briefs"]},
        files=[("files", (path, content.encode())) for path, content in files.items()],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _chat(client: TestClient) -> int:
    response = client.post("/api/chats")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _send(client: TestClient, chat_id: int, text: str) -> list[dict]:
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": text})
    assert response.status_code == 201, response.text
    return response.json()


def _campaign(client: TestClient, chat_id: int) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()["campaign"]


def _kinds(messages: list[dict]) -> list[str]:
    return [m["kind"] for m in messages]


def test_a_campaign_needs_a_brand(client: TestClient):
    response = client.post("/api/chats")

    assert response.status_code == 409
    assert "Add a brand" in response.json()["detail"]


def test_a_clear_brief_goes_straight_to_a_plan(client: TestClient):
    _brand(client)
    chat_id = _chat(client)

    messages = _send(client, chat_id, CLEAR_BRIEF)

    assert "question" not in _kinds(messages)
    assert messages[-1]["kind"] == "plan"
    campaign = _campaign(client, chat_id)
    assert campaign["stage"] == "plan_ready"
    assert [a["type"] for a in campaign["plan"]["assets"]] == ["email", "linkedin_post", "x_post"]
    assert "No paid media." in campaign["assumptions"]


def test_the_agent_looks_things_up_with_tools(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)

    calls = client.get("/api/ai-calls", params={"chat_id": chat_id}).json()
    steps = [c["step"] for c in calls]
    assert steps[:3] == ["Brief review (round 1)", "Brief review (round 2)", "Campaign plan (round 1)"]
    second = client.get(f"/api/ai-calls/{calls[1]['id']}").json()
    tool_output = next(item for item in second["request"]["input"] if item.get("type") == "function_call_output")
    assert "Acme is not certified." in tool_output["output"]
    assert "sales-notes" not in tool_output["output"]  # the internal note lost the conflict


def test_a_settled_conflict_the_agent_relied_on_is_noted_once(client: TestClient):
    _brand(client)
    chat_id = _chat(client)

    messages = _send(client, chat_id, CLEAR_BRIEF)

    notes = [m["content"] for m in messages if m["kind"] == "note"]
    assert notes == ["Certifications: two brand documents disagree. I used certifications.md, because it is the "
                     "document that sets this."]
    assert not [m for m in _send(client, chat_id, "Who gets the email first?") if m["kind"] == "note"]


def test_a_conflict_the_agent_saw_but_did_not_use_is_not_noted(client: TestClient, fake_ai: FakeTransport):
    def plan_without_the_fact(request):
        answer = brand_brain.reply(request)
        return answer.replace("Acme is not certified, so the copy never says it is.", "") if isinstance(answer, str) else answer

    fake_ai._default = plan_without_the_fact
    _brand(client)
    chat_id = _chat(client)

    messages = _send(client, chat_id, CLEAR_BRIEF)

    assert not [m for m in messages if m["kind"] == "note"]


def test_a_false_claim_in_the_brief_gets_push_back_with_proof(client: TestClient):
    _brand(client)
    chat_id = _chat(client)

    messages = _send(client, chat_id, "Lead with: Acme is certified. Email to security leaders.")

    card = messages[-1]
    assert card["kind"] == "question"
    assert card["data"]["kind"] == "clash"
    assert (card["data"]["source_path"], card["data"]["quote"]) == ("legal/certifications.md", "Acme is not certified.")
    assert card["data"]["options"][0]["label"] == "Say Acme is not certified"
    assert _campaign(client, chat_id)["stage"] == "asking"


def test_a_quote_that_isnt_in_the_document_is_dropped(client: TestClient):
    _brand(client)
    chat_id = _chat(client)

    card = _send(client, chat_id, "An invented claim.")[-1]

    assert (card["data"]["quote"], card["data"]["source_path"]) == ("", "")


def test_questions_come_one_at_a_time_then_the_plan(client: TestClient, fake_ai: FakeTransport):
    _brand(client)
    chat_id = _chat(client)

    first = _send(client, chat_id, "Do an awareness push.")[-1]
    assert (first["content"], first["data"]["remaining"]) == ("Who is it for?", 2)

    second = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 0, "answer": "Platform leads"}).json()
    assert second[-1]["kind"] == "question" and second[-1]["content"] == "When does it run?"

    done = _send(client, chat_id, "Late February")  # typing answers the open question
    assert done[-1]["kind"] == "plan"
    plan_prompt = fake_ai.requests[-1].prompt.campaign
    assert "A: Platform leads" in plan_prompt and "A: Late February" in plan_prompt
    first_card = next(m for m in client.get(f"/api/chats/{chat_id}").json()["messages"] if m["kind"] == "question")
    assert first_card["data"]["answer"] == "Platform leads"


def test_brief_overrides_are_kept_for_this_campaign(client: TestClient):
    _brand(client)
    chat_id = _chat(client)

    messages = _send(client, chat_id, f"{CLEAR_BRIEF} The early access label comes off.")

    assert _campaign(client, chat_id)["brief_rules"] == ["The early access label comes off for these assets only."]
    assert "Your brief changes a brand rule, for this campaign only: The early access label comes off for these assets only." in [
        m["content"] for m in messages if m["kind"] == "note"
    ]


def test_answering_a_conflict_question_settles_it_for_the_brand(client: TestClient):
    brand_id = _brand(client, {"acme/colors/a.md": "# Colors\n\nOur color is red.\n", "acme/colors/b.md": "# Colors\n\nOur color is blue.\n"})
    conflict = next(c for c in client.get(f"/api/brands/{brand_id}").json()["conflicts"] if c["subject"] == "brand color")
    assert conflict["rule"] == "needs_human"
    chat_id = _chat(client)

    card = _send(client, chat_id, "Use our brand color everywhere.")[-1]
    assert sorted(o["label"] for o in card["data"]["options"]) == ["blue", "red"]
    messages = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 0, "answer": "colors/b.md"}).json()

    assert any("Saved for the brand" in m["content"] for m in messages)
    settled = next(c for c in client.get(f"/api/brands/{brand_id}").json()["conflicts"] if c["subject"] == "brand color")
    assert (settled["winner"], settled["rule"]) == ("colors/b.md", "you")
    # The decision lives on the Brand page only: a copy in memory went stale when the conflict was decided again,
    # leaving "a wins" and "b wins" side by side.
    assert not any(m["kind"] == "memory" for m in messages)
    assert client.get(f"/api/brands/{brand_id}/memory").json()["core"] == []


def test_the_plan_changes_by_chat_and_untouched_assets_stay(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)
    before = _campaign(client, chat_id)["plan"]["assets"]

    messages = _send(client, chat_id, "Drop the X post.")

    assert messages[-1]["kind"] == "plan"
    after = _campaign(client, chat_id)
    assert after["plan"]["assets"] == before[:2]
    assert after["plan_version"] == 2


def test_a_question_about_the_plan_gets_an_answer_and_no_change(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)

    reply = _send(client, chat_id, "Who gets the email first?")[-1]

    assert (reply["kind"], reply["content"]) == ("text", "The email goes to customers first.")
    assert _campaign(client, chat_id)["plan_version"] == 1


def test_an_unclear_plan_message_gets_a_question_card(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)

    card = _send(client, chat_id, "Make it better")[-1]

    assert card["kind"] == "question"
    assert [o["label"] for o in card["data"]["options"]] == ["Shorter", "More technical"]


def test_plan_cards_can_be_reordered_edited_and_removed(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)
    assets = _campaign(client, chat_id)["plan"]["assets"]

    edited = [{**assets[1], "date": "2027-02-01"}, assets[0]]
    response = client.put(f"/api/chats/{chat_id}/plan", json={"assets": edited})

    assert response.status_code == 200, response.text
    plan = response.json()["plan"]["assets"]
    assert [a["id"] for a in plan] == ["a2", "a1"]
    assert plan[0]["date"] == "2027-02-01"


def test_new_assets_cant_be_added_on_the_cards(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)

    response = client.put(f"/api/chats/{chat_id}/plan", json={"assets": [{"id": "new", "type": "email"}]})

    assert response.status_code == 400


def test_writing_waits_for_approval_and_an_approved_plan_is_locked(client: TestClient):
    _brand(client)
    chat_id = _chat(client)
    _send(client, chat_id, CLEAR_BRIEF)

    assert client.post(f"/api/chats/{chat_id}/write").status_code == 409
    assert client.get(f"/api/chats/{chat_id}/assets").json() == []
    assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200
    assert _campaign(client, chat_id)["stage"] == "done"  # writing ran straight after approval
    assert client.put(f"/api/chats/{chat_id}/plan", json={"assets": []}).status_code == 409
    assert client.post(f"/api/chats/{chat_id}/write").status_code == 409  # nothing left to write


def test_every_agent_call_starts_with_the_same_fixed_part(client: TestClient, fake_ai: FakeTransport):
    _brand(client)
    _send(client, _chat(client), CLEAR_BRIEF)
    _send(client, _chat(client), "Do an awareness push.")

    agent_calls = [r for r in fake_ai.requests if r.output_schema and r.output_schema.name in ("brief_review", "campaign_plan")]
    fixed = {r.prompt.fixed for r in agent_calls}
    assert len(fixed) == 1
    assert "=== BRAND SUMMARY ===\n# Acme brand summary" in fixed.pop()
    assert all(r.cache_key == agent_calls[0].cache_key for r in agent_calls)


COLORS = {"acme/colors/a.md": "# Colors\n\nOur color is red.\n", "acme/colors/b.md": "# Colors\n\nOur color is blue.\n"}


def test_a_conflict_question_is_tied_to_the_exact_conflict_the_agent_looked_up(client: TestClient):
    brand_id = _brand(client, COLORS)
    color = next(c for c in client.get(f"/api/brands/{brand_id}").json()["conflicts"] if c["subject"] == "brand color")
    chat_id = _chat(client)

    card = _send(client, chat_id, "Use our brand color everywhere.")[-1]

    assert card["data"]["conflict_target"] == color["target"]


def test_a_conflict_question_with_an_id_the_agent_was_never_shown_settles_nothing(client: TestClient):
    """The bug: a loose word match tied the question to some other unsettled conflict, and the answer was
    saved as a brand decision on it. Now only an exact, looked-up conflict can be settled from chat."""
    brand_id = _brand(client, COLORS)
    chat_id = _chat(client)

    card = _send(client, chat_id, "Use our brand color everywhere, an unknown conflict.")[-1]
    assert "conflict_target" not in card["data"]
    assert [o["label"] for o in card["data"]["options"]] == ["one", "two"]  # the model's own options, nothing linked

    messages = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": 0, "answer": "one"}).json()

    assert not any("Saved for the brand" in m["content"] for m in messages)
    brand = client.get(f"/api/brands/{brand_id}").json()
    assert brand["decisions"] == []
    assert next(c for c in brand["conflicts"] if c["subject"] == "brand color")["rule"] == "needs_human"
    assert client.get(f"/api/brands/{brand_id}/memory").json()["core"] == []


def test_a_new_chat_can_name_its_brand(client: TestClient):
    first = _brand(client)
    _brand(client)  # the newest brand, which a chat gets by default

    chosen = client.post("/api/chats", json={"brand_id": first}).json()
    default = client.post("/api/chats").json()

    assert chosen["campaign"]["brand_id"] == first  # was always the newest brand
    assert default["campaign"]["brand_id"] != first
