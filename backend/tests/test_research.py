"""Web research on the plan. Fake web search, fake AI."""

import time

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeTransport
from app.ai.transport import AiRequest
from app.research import notes
from app.research.client import FakeWebResearch, ResearchFailed, WebPage
from tests import brand_brain

BRIEF = "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."
PAGE = WebPage("https://example.org/widgets", "Widget report", "Intro. The widget market grew 12% in 2026. More text.",
               "2026-05-01")
OTHER = WebPage("https://other.example/report", "Another report", "The widget market grew 12% in 2026. Other text.",
                "2026-06-01")


@pytest.fixture(autouse=True)
def brand(client: TestClient, fake_ai: FakeTransport, fake_web: FakeWebResearch) -> int:
    fake_ai._default = brand_brain.reply
    fake_web._pages = lambda query: [PAGE]
    response = client.post("/api/brands", data={"name": "Acme"},
                           files=[("files", (p, c.encode())) for p, c in brand_brain.BRAND.items()])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _send(client: TestClient, chat_id: int, text: str) -> list[dict]:
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": text})
    assert response.status_code == 201, response.text
    return response.json()


def _planned(client: TestClient, brief: str = f"{BRIEF} Plan it with research.") -> tuple[int, list[dict]]:
    chat_id = client.post("/api/chats").json()["id"]
    return chat_id, _send(client, chat_id, brief)


def _campaign(client: TestClient, chat_id: int) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()["campaign"]


def _down(query: str) -> list[WebPage]:
    raise ResearchFailed("Web search failed: timed out")


# 1. A failed search is reported, not counted as done, and tried again


def test_a_failed_search_is_reported_and_tried_again_on_the_next_plan_change(client: TestClient,
                                                                             fake_web: FakeWebResearch):
    fake_web._pages = _down
    chat_id, messages = _planned(client)

    notes = [m["content"] for m in messages if m["kind"] == "note"]
    assert any("failed (Web search failed: timed out)" in n and "press Try again" in n for n in notes)  # was "no usable findings"
    assert _campaign(client, chat_id)["research"] == []

    fake_web._pages = lambda query: [PAGE]
    _send(client, chat_id, "Drop the X post.")

    assert fake_web.queries == ["widget market size", "widget market size"]
    assert [f["url"] for f in _campaign(client, chat_id)["research"]] == ["https://example.org/widgets"]


def test_a_failed_search_can_be_tried_again_from_its_card(client: TestClient, fake_web: FakeWebResearch):
    fake_web._pages = _down
    chat_id, _ = _planned(client)
    assert _campaign(client, chat_id)["plan"]["failed_searches"] == ["widget market size"]  # the card shows Try again

    fake_web._pages = lambda query: [PAGE]
    notes = client.post(f"/api/chats/{chat_id}/research/retry").json()

    assert "Searched the web for “widget market size”: 1 finding" in notes[-1]["content"]
    campaign = _campaign(client, chat_id)
    assert campaign["plan"]["failed_searches"] == []
    assert [f["asset_ids"] for f in campaign["research"]] == [["a2"]]


# 5. A failed notes call never breaks planning


def test_a_failed_research_notes_call_does_not_break_planning(client: TestClient, fake_ai: FakeTransport):
    def notes_fail(request: AiRequest):
        if request.output_schema and request.output_schema.name == "research_notes":
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = notes_fail
    chat_id, messages = _planned(client)

    assert messages[-1]["kind"] == "plan"  # the plan is still posted; the request used to fail halfway
    assert _campaign(client, chat_id)["stage"] == "plan_ready"
    assert any("failed" in m["content"] for m in messages if m["kind"] == "note")


# 2. "Find a better source" keeps the old finding unless something better turns up


def test_a_better_source_that_fails_keeps_the_finding(client: TestClient, fake_web: FakeWebResearch):
    chat_id, _ = _planned(client)
    finding = _campaign(client, chat_id)["research"][0]
    fake_web._pages = _down

    reply = client.post(f"/api/chats/{chat_id}/research/{finding['id']}/better").json()[-1]

    assert "The finding is kept" in reply["content"]
    assert [f["removed"] for f in _campaign(client, chat_id)["research"]] == [False]  # was removed, leaving nothing


def test_a_better_source_that_finds_one_replaces_the_old_finding(client: TestClient, fake_web: FakeWebResearch):
    chat_id, _ = _planned(client)
    finding = _campaign(client, chat_id)["research"][0]
    fake_web._pages = lambda query: [PAGE, OTHER]

    client.post(f"/api/chats/{chat_id}/research/{finding['id']}/better")

    research = _campaign(client, chat_id)["research"]
    assert [(f["url"], f["removed"]) for f in research] == [
        ("https://example.org/widgets", True), ("https://other.example/report", False)]


# 3. A deleted plan card's findings stop counting


def test_a_deleted_cards_findings_are_not_approved_or_written(client: TestClient, fake_ai: FakeTransport):
    chat_id, _ = _planned(client)
    cards = _campaign(client, chat_id)["plan"]["assets"]
    assert client.put(f"/api/chats/{chat_id}/plan", json={"assets": [cards[0], cards[2]]}).status_code == 200

    note = client.post(f"/api/chats/{chat_id}/approve").json()[0]

    assert note["content"] == "Plan approved. Writing 2 assets, a few at a time."  # was "with 1 research finding"
    assert _campaign(client, chat_id)["research"][0]["asset_ids"] == []  # a later card reusing "a2" won't inherit it
    prompts = [r.prompt for r in fake_ai.requests if r.output_schema and r.output_schema.name.endswith("_asset")]
    assert prompts and not any("example.org" in p.campaign + p.task[-1].content for p in prompts)


# 4. A reworded search on a plan edit doesn't pay for a new one


def test_a_reworded_search_on_a_plan_edit_keeps_the_findings_and_searches_nothing(client: TestClient,
                                                                                   fake_web: FakeWebResearch):
    chat_id, _ = _planned(client)

    _send(client, chat_id, "Reword the search.")

    campaign = _campaign(client, chat_id)
    assert campaign["plan"]["assets"][1]["research_query"] == "Widget market size, 2026"
    assert fake_web.queries == ["widget market size"]  # was searched again, with both sets of findings on the card
    assert [(f["url"], f["asset_ids"]) for f in campaign["research"]] == [("https://example.org/widgets", ["a2"])]


def test_a_new_research_topic_by_chat_replaces_the_old_findings(client: TestClient, fake_web: FakeWebResearch):
    chat_id, _ = _planned(client)

    _send(client, chat_id, "For the post, research hiring stats instead.")

    assert fake_web.queries == ["widget market size", "hiring stats"]  # the new topic was never searched
    research = _campaign(client, chat_id)["research"]
    assert [(f["query"], f["asset_ids"]) for f in research] == [("widget market size", []), ("hiring stats", ["a2"])]


def test_a_new_subject_with_most_words_shared_still_searches_again(client: TestClient, fake_web: FakeWebResearch):
    chat_id, _ = _planned(client)

    notes = [m["content"] for m in _send(client, chat_id, "Research market share instead.") if m["kind"] == "note"]

    # word counting called "widget market size" and "widget market share" the same topic and kept the old findings
    assert fake_web.queries == ["widget market size", "widget market share"]
    research = _campaign(client, chat_id)["research"]
    assert [(f["query"], f["asset_ids"]) for f in research] == [("widget market size", []), ("widget market share", ["a2"])]
    assert "“Launch post”: its research moved to a new subject, so its earlier findings no longer count." in notes


def test_a_rewording_with_few_words_shared_keeps_the_findings(client: TestClient, fake_web: FakeWebResearch):
    chat_id, _ = _planned(client)

    _send(client, chat_id, "Ask it as a question.")

    assert fake_web.queries == ["widget market size"]  # word counting called this a new topic and searched again
    assert [f["asset_ids"] for f in _campaign(client, chat_id)["research"]] == [["a2"]]


def test_a_card_added_in_a_dropped_cards_place_does_not_inherit_its_findings(client: TestClient,
                                                                              fake_web: FakeWebResearch):
    chat_id, _ = _planned(client, f"{BRIEF} Plan it with three searches.")
    x_finding = next(f for f in _campaign(client, chat_id)["research"] if f["query"] == "x trends")

    _send(client, chat_id, "Swap the X post for a blog post.")

    campaign = _campaign(client, chat_id)
    blog = campaign["plan"]["assets"][-1]
    assert blog["id"] not in ("a1", "a2", "a3")  # was "a3", the dropped X post's id
    old = next(f for f in campaign["research"] if f["id"] == x_finding["id"])
    assert old["asset_ids"] == []
    assert "x trends 2026" in fake_web.queries  # the new card got its own search


# 6. Searches run at the same time


def test_several_searches_run_at_the_same_time(client: TestClient, fake_web: FakeWebResearch):
    def slow(query: str) -> list[WebPage]:
        time.sleep(0.6)
        return [PAGE]

    fake_web._pages = slow
    started = time.monotonic()
    chat_id, _ = _planned(client, f"{BRIEF} Plan it with three searches.")
    elapsed = time.monotonic() - started

    assert sorted(fake_web.queries) == ["email trends", "widget market size", "x trends"]
    assert elapsed < 1.5  # one after another took at least 1.8 seconds
    calls = client.get("/api/ai-calls", params={"chat_id": chat_id}).json()
    assert len([c for c in calls if c["step"].startswith("Research notes")]) == 3  # each logged and priced


# 7. Dates come from the page only


def test_a_page_without_a_date_shows_date_unknown(client: TestClient, fake_web: FakeWebResearch):
    fake_web._pages = lambda query: [WebPage(PAGE.url, PAGE.title, PAGE.text, "")]

    chat_id, _ = _planned(client)

    assert [f["date"] for f in _campaign(client, chat_id)["research"]] == ["date unknown"]


# 9. A web finding about the brand or its products is dropped in code


def test_a_web_finding_about_the_brand_is_dropped(client: TestClient, fake_ai: FakeTransport, fake_web: FakeWebResearch):
    text = "Acme Widget costs $5 a month. The widget market grew 12% in 2026."
    fake_web._pages = lambda query: [WebPage(PAGE.url, PAGE.title, text, PAGE.date)]

    def notes(request: AiRequest):
        if request.output_schema and request.output_schema.name == "research_notes":
            return ('{"findings": [{"finding": "Acme Widget costs $5 a month.", "quote": "Acme Widget costs $5 a '
                    'month.", "page": 1}, {"finding": "The widget market grew 12% in 2026.", "quote": "The widget '
                    'market grew 12% in 2026.", "page": 1}]}')
        return brand_brain.reply(request)

    fake_ai._default = notes
    chat_id, _ = _planned(client)

    assert [f["finding"] for f in _campaign(client, chat_id)["research"]] == ["The widget market grew 12% in 2026."]


def test_the_brand_filter_matches_names_as_the_brand_writes_them():
    assert notes._mentions("Square raised its prices.", ("Square",))
    assert not notes._mentions("The square footage of offices grew.", ("Square",))  # an everyday word stays
    assert notes._mentions("ACME WIDGET COSTS $5 A MONTH.", ("Acme Widget",))  # capitals are caught too
    assert not notes._mentions("acme widget costs $5 a month.", ("Acme Widget",))  # lower case is left to the prompt


# 8. Each writer sees only its own asset's findings


def test_the_shared_prompt_part_carries_no_research(client: TestClient, fake_ai: FakeTransport):
    chat_id, _ = _planned(client)

    client.post(f"/api/chats/{chat_id}/approve")

    writes = {r.output_schema.name: r.prompt for r in fake_ai.requests
              if r.output_schema and r.output_schema.name.endswith("_asset")}
    assert all("example.org" not in p.campaign for p in writes.values())  # was in every asset's shared part
    assert "example.org" in writes["linkedin_post_asset"].task[-1].content
    assert "example.org" not in writes["email_asset"].task[-1].content


# 10. A removed finding can be brought back


def test_a_removed_finding_can_be_brought_back(client: TestClient):
    chat_id, _ = _planned(client)
    finding = _campaign(client, chat_id)["research"][0]
    client.delete(f"/api/chats/{chat_id}/research/{finding['id']}")

    assert client.post(f"/api/chats/{chat_id}/research/{finding['id']}/restore").status_code == 200

    assert [f["removed"] for f in _campaign(client, chat_id)["research"]] == [False]
    note = client.post(f"/api/chats/{chat_id}/approve").json()[0]
    assert note["content"].startswith("Plan approved with 1 research finding.")
