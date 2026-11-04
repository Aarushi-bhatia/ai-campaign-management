"""Writing, checking and editing assets after approval, through the chat API with a fake AI."""

import json

import pytest
from fastapi.testclient import TestClient

import time
from types import SimpleNamespace

from sqlalchemy import func, select

from app.ai.fake import FakeTransport
from app.ai.transport import AiRequest
from app.ai.models import AiCall
from app.ai.prompt import Prompt, Turn
from app.brand.images.picking import AssetSpec, Choice, PickResult, rank_prompt
from app.campaign import assets as assets_module
from app.campaign.brand_tools import CHANNEL_WORDS, _channel_score
from app.campaign.runtime import Runtime
from app.campaign.writing import resume_interrupted
from app.config import ModelSize, Settings
from app.db import SessionLocal
from app.jobs import InlineJobRunner
from app.brand.models import Conflict
from app.campaign import agent, checker, editing, writer
from app.campaign.checks import CheckRules, free_checks
from app.campaign.models import Asset, Campaign
from app.research.client import FakeWebResearch, WebPage
from tests import brand_brain

BRIEF = "Launch Acme Widget to platform leads on January 26. One email, one LinkedIn post, one X post."


@pytest.fixture(autouse=True)
def brain(fake_ai: FakeTransport, fake_web: FakeWebResearch) -> None:
    fake_ai._default = brand_brain.reply
    fake_web._pages = lambda query: [WebPage("https://example.org/widgets", "Widget report",
                                             "Intro. The widget market grew 12% in 2026. More text.", "2026-05-01")]


def _brand(client: TestClient) -> int:
    response = client.post("/api/brands", data={"name": "Acme"},
                           files=[("files", (p, c.encode())) for p, c in brand_brain.BRAND.items()])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _send(client: TestClient, chat_id: int, text: str) -> list[dict]:
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": text})
    assert response.status_code == 201, response.text
    return response.json()


def _planned(client: TestClient, brief: str = BRIEF) -> int:
    chat_id = client.post("/api/chats").json()["id"]
    _send(client, chat_id, brief)
    return chat_id


def _written(client: TestClient, brief: str = BRIEF) -> int:
    chat_id = _planned(client, brief)
    assert client.post(f"/api/chats/{chat_id}/approve").status_code == 200
    return chat_id


def _assets(client: TestClient, chat_id: int) -> list[dict]:
    return client.get(f"/api/chats/{chat_id}/assets").json()


def _fake(client: TestClient) -> FakeTransport:
    from app.ai.deps import get_ai_transport
    return client.app.dependency_overrides[get_ai_transport]()


def _messages(client: TestClient, chat_id: int) -> list[dict]:
    return client.get(f"/api/chats/{chat_id}").json()["messages"]


def _schema_requests(fake_ai: FakeTransport, suffix: str) -> list:
    return [r for r in fake_ai.requests if r.output_schema and r.output_schema.name.endswith(suffix)]


@pytest.fixture
def brand(client: TestClient) -> int:
    return _brand(client)


# Writing

def test_approving_writes_every_asset_with_its_fixed_fields(client: TestClient, brand: int):
    chat_id = _written(client)

    assets = _assets(client, chat_id)
    assert [(a["type"], a["state"]) for a in assets] == [("email", "done"), ("linkedin_post", "done"), ("x_post", "done")]
    assert set(assets[0]["content"]) == {"sender", "subject", "preview_text", "sections", "button_text", "button_link", "sources"}
    assert set(assets[1]["content"]) == {"author", "text", "hashtags", "sources"}
    assert all(a["call_id"] for a in assets)
    assert client.get(f"/api/chats/{chat_id}").json()["campaign"]["stage"] == "done"


def test_each_asset_is_written_in_its_own_call_with_the_fixed_prompt_order(client: TestClient, brand: int,
                                                                           fake_ai: FakeTransport):
    _written(client)

    writes = [r for r in _schema_requests(fake_ai, "_asset") if "fixed" not in r.output_schema.schema["properties"]
              and "changed" not in r.output_schema.schema["properties"]]
    assert len(writes) == 3
    first = writes[0].to_payload(for_log=True)["input"]
    assert "=== BRAND SUMMARY ===" in first[0]["content"][0]["text"]
    assert "=== APPROVED PLAN ===" in first[1]["content"][0]["text"]
    assert "=== CHANNEL RULES ===" in first[2]["content"]
    assert len({r.prompt.campaign for r in writes}) == 1  # the campaign part is shared, so it is cached


def test_the_chat_gets_a_status_line_per_asset(client: TestClient, brand: int):
    chat_id = _written(client)

    lines = [m["content"] for m in _messages(client, chat_id) if m["kind"] == "note" and "written" in m["content"]]
    assert len(lines) == 3
    assert any("Looked up email rules" in line for line in lines)  # in the order they finish


def test_a_failed_check_is_fixed_once_and_noted(client: TestClient, brand: int):
    chat_id = _written(client)

    x_post = _assets(client, chat_id)[2]
    assert "Gizmo" not in x_post["content"]["text"]
    assert x_post["fixed"] == ["Removed the retired name Gizmo."]
    versions = client.get(f"/api/chats/{chat_id}/assets/{x_post['id']}/versions").json()
    assert [v["reason"] for v in versions] == ["written", "auto fix"]
    assert "Gizmo" in versions[0]["content"]["text"]


def test_approving_produces_every_asset_type_with_its_fixed_fields(client: TestClient, brand: int):
    chat_id = _written(client, "Launch Acme Widget on January 26 with every asset type.")

    assets = _assets(client, chat_id)

    assert [a["type"] for a in assets] == ["email", "linkedin_post", "x_post", "blog_post", "landing_page"]
    assert all(a["state"] == "done" for a in assets)
    for asset in assets:
        assert set(asset["content"]) == {*writer.FIELDS[asset["type"]], "sources"}, asset["type"]
    section = assets[4]["content"]["sections"][0]
    assert set(section) == set(writer.FIELDS["landing_page"]["sections"]["items"]["properties"])
    assert set(assets[0]["content"]["sections"][0]) == {"heading", "body"}


def test_a_failed_check_keeps_the_draft_and_check_again_finishes_it(client: TestClient, brand: int,
                                                                     fake_ai: FakeTransport):
    state = {"failed": False}

    def check_fails_once(request):
        if not state["failed"] and request.output_schema and request.output_schema.name == "asset_check":
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = check_fails_once
    chat_id = _written(client)

    email = _assets(client, chat_id)[0]
    assert email["state"] == "done" and email["content"]  # was "failed", with the draft hidden
    assert [w["check"] for w in email["warnings"]] == ["not checked"]
    assert [v["reason"] for v in client.get(f"/api/chats/{chat_id}/assets/{email['id']}/versions").json()] == ["written"]
    notes = [m["content"] for m in _messages(client, chat_id) if m["kind"] == "note"]
    assert any("written, but its checks couldn't run" in n for n in notes)

    assert client.post(f"/api/chats/{chat_id}/assets/{email['id']}/check").status_code == 200
    assert _assets(client, chat_id)[0]["warnings"] == []
    assert len(_schema_requests(fake_ai, "email_asset")) == 1  # written once; never paid for again


def test_a_hand_edit_keeps_the_not_checked_warning(client: TestClient, brand: int, fake_ai: FakeTransport):
    state = {"failed": False}

    def check_fails_once(request):
        if not state["failed"] and request.output_schema and request.output_schema.name == "asset_check":
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = check_fails_once
    chat_id = _written(client)
    email = _assets(client, chat_id)[0]
    content = {**email["content"], "subject": "Meet Acme Widget today"}

    changed = client.put(f"/api/chats/{chat_id}/assets/{email['id']}",
                         json={"content": content, "base_version": email["version"]}).json()["asset"]

    assert [w["check"] for w in changed["warnings"]] == ["not checked"]  # was cleared, showing "Passed the checks"


RANKING = "Rank the images."


def test_assets_written_at_the_same_time_get_different_images(client: TestClient, brand: int, fake_ai: FakeTransport,
                                                              monkeypatch: pytest.MonkeyPatch):
    """The ranking is a real (fake) AI call, so it is logged. Logging used to commit the asset's session, which
    let go of the campaign lock before the choice was saved, and the two assets written together both took
    the top-ranked image."""
    default = fake_ai._default
    fake_ai._default = lambda request: "ranked" if request.prompt.fixed == RANKING else default(request)
    ranked: list[tuple[float, float]] = []

    def pick(session, ai, brand, spec, chat_id=None, step=None):
        started = time.monotonic()
        reply = ai.complete(step=step, size=ModelSize.SMALL, prompt=Prompt(fixed=RANKING, task=[Turn("user", "Rank.")]),
                            chat_id=chat_id, brand_id=brand.id)
        time.sleep(0.3)  # long enough for the assets written together to overlap
        ranked.append((started, time.monotonic()))
        # every asset gets the same ranking, so only the reservation can keep them apart
        return PickResult(choices=[Choice(f"photos/{name}.jpg", "Fits.", "A photo.") for name in ("a", "b", "c")],
                          call_id=reply.call_id)

    monkeypatch.setattr(assets_module.library, "pick", pick)
    chat_id = _written(client)

    assert sorted(a["image"]["path"] for a in _assets(client, chat_id)) == ["photos/a.jpg", "photos/b.jpg", "photos/c.jpg"]
    # the two written together ranked at the same time: no lock is held while the AI ranks
    (_, _), (start_2, end_2), (start_3, end_3) = sorted(ranked)
    assert start_3 < end_2
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(AiCall).where(AiCall.step.like("Image choice asset %"))) == 3


def test_assets_share_an_image_only_when_no_other_ranked_choice_is_free(client: TestClient, brand: int,
                                                                       monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(assets_module.library, "pick", lambda *args, **kwargs: PickResult(
        choices=[Choice("photos/only.jpg", "Fits.", "A photo.")]))

    chat_id = _written(client)

    assert {a["image"]["path"] for a in _assets(client, chat_id)} == {"photos/only.jpg"}


def test_writing_progress_is_visible_while_the_ai_works(client: TestClient, brand: int, fake_ai: FakeTransport):
    """The asset cards poll the asset's state during the job, so "writing" and "checking" must be saved before
    the slow calls, not only at the end."""
    seen: dict[str, set[str]] = {"write": set(), "check": set()}
    default = fake_ai._default

    def answer(request):
        schema = request.output_schema.name if request.output_schema else ""
        step = "write" if schema == "email_asset" and "Write asset 1 " in request.prompt.task[-1].content else \
            "check" if schema == "asset_check" and not seen["check"] else None  # the email is written and checked first
        if step:
            with SessionLocal() as other:  # what the polling UI would read
                seen[step] |= {a.state for a in other.scalars(select(Asset).where(Asset.type == "email"))}
        return default(request)

    fake_ai._default = answer
    _written(client)

    assert seen == {"write": {"writing"}, "check": {"checking"}}


def test_writing_cut_off_while_checking_only_checks_on_restart(client: TestClient, brand: int, fake_ai: FakeTransport,
                                                              settings: Settings):
    chat_id = _written(client)
    with SessionLocal() as session:
        campaign = session.scalars(select(Campaign).where(Campaign.chat_id == chat_id)).one()
        campaign.stage = "writing"
        campaign.assets[0].state = "checking"  # a restart came while its checks ran
        session.commit()
    writes_before = len(_schema_requests(fake_ai, "email_asset"))

    resume_interrupted(Runtime(SessionLocal, fake_ai, settings, InlineJobRunner(), None))

    email = _assets(client, chat_id)[0]
    assert email["state"] == "done"
    assert len(_schema_requests(fake_ai, "email_asset")) == writes_before  # was written again from scratch
    assert client.get(f"/api/chats/{chat_id}").json()["campaign"]["stage"] == "done"


def test_channel_rules_from_the_channels_own_playbook_come_first():
    rule = SimpleNamespace(subject="Subject lines", attribute="length", scope="email")
    mention = SimpleNamespace(subject="Launch", attribute="also sent by email", scope="")
    playbook = SimpleNamespace(path="channels/email-playbook.md")
    elsewhere = SimpleNamespace(path="internal/meeting-notes.md")
    words = CHANNEL_WORDS["email"]

    assert _channel_score("email", words, rule, playbook) > _channel_score("email", words, mention, elsewhere) > 0
    assert _channel_score("email", words, SimpleNamespace(subject="Pricing", attribute="tier", scope=""), elsewhere) == 0


def test_the_image_picker_is_told_which_images_the_campaign_already_uses():
    spec = AssetSpec(channel="linkedin", asset_type="linkedin_post", message="Launch.",
                     used_paths=frozenset({"photos/team-rack.jpg"}))

    task = rank_prompt(spec, [], {"channels": {}, "general_rules": [], "alt_text_rules": []}).task[-1].content

    assert "Already used by other assets of this campaign: photos/team-rack.jpg" in task
    assert "Prefer a different image" in task


# Ticket 8 review

def test_undo_to_the_first_draft_brings_back_its_problems(client: TestClient, brand: int):
    chat_id = _written(client)
    x_post = _assets(client, chat_id)[2]  # its first draft used the retired name Gizmo; the auto fix removed it

    undone = client.post(f"/api/chats/{chat_id}/assets/{x_post['id']}/undo?base_version={x_post['version']}").json()

    assert "Gizmo" in undone["content"]["text"]
    assert [w["check"] for w in undone["warnings"]] == ["old name"]  # was [], shown as "Passed the checks"
    first = client.get(f"/api/chats/{chat_id}/assets/{x_post['id']}/versions").json()[0]
    assert [w["check"] for w in first["warnings"]] == ["old name"]  # the first check's result is kept on version 1


def test_a_chat_edit_uses_the_numbers_on_the_tabs(client: TestClient, brand: int):
    chat_id = _written(client)
    _send(client, chat_id, "Drop the second post")  # the tabs now read 1 and 3

    _send(client, chat_id, "Shorten asset 3")

    email, x_post = _assets(client, chat_id)
    assert (email["version"], x_post["version"]) == (1, 3)  # the X post (tab 3) was edited, after its auto fix
    route = [r for r in _schema_requests(_fake(client), "edit_request")][-1]
    assert "\n3. X post" in route.prompt.task[-1].content


def test_checks_on_one_channel_share_a_cached_start_up_to_its_rules():
    class Ai:
        def __init__(self):
            self.prompts = []

        def complete(self, **kwargs):
            self.prompts.append(kwargs["prompt"])
            return SimpleNamespace(text='{"problems": []}', call_id=1)

    ai = Ai()
    for rules, text in (("X rules", "First post."), ("X rules", "Second post."), ("Email rules", "Hello.")):
        checker.ai_check(ai, brand_name="Acme", summary="Summary", campaign="Campaign", asset_label="X post",
                         content={"text": text}, facts="Facts", step="Check asset", chat_id=1, brand_id=1, rules=rules)
    first, second, email = (p.to_input() for p in ai.prompts)

    assert first[:3] == second[:3]  # fixed, campaign and the X rules: read from the cache the second time
    assert first[3] != second[3]  # only the asset itself differs
    assert first[:2] == email[:2] and first[2] != email[2]  # another channel shares the start up to its rules
    assert all("prompt_cache_breakpoint" in m["content"][0] for m in first[:3])
    assert "X rules" not in first[3]["content"]


def test_the_ai_check_and_the_fix_see_the_channel_rules_and_facts(client: TestClient, brand: int,
                                                                  fake_ai: FakeTransport):
    _written(client)

    check = next(r for r in fake_ai.requests if r.output_schema and r.output_schema.name == "asset_check")
    assert check.prompt.channel.startswith("=== CHANNEL RULES THE WRITER HAD ===\n{")  # was facts only
    assert "=== FACTS THE WRITER HAD ===" in check.prompt.task[-1].content
    fix = _schema_requests(fake_ai, "x_post_asset")[1]  # the auto fix of the X post
    assert "=== CHANNEL RULES ===\n{" in fix.prompt.task[-1].content
    assert "=== FACTS FOR THIS ASSET ===" in fix.prompt.task[-1].content


def test_a_hand_edit_drops_an_ai_warning_once_its_words_are_gone(client: TestClient, brand: int):
    chat_id = _written(client)
    email = _assets(client, chat_id)[0]
    claim = {"check": "claim", "quote": "Acme Widget is here", "problem": "Unsupported."}
    with SessionLocal() as session:
        session.get(Asset, email["id"]).warnings = [claim]
        session.commit()
    url = f"/api/chats/{chat_id}/assets/{email['id']}"
    sections = email["content"]["sections"]

    kept = client.put(url, json={"content": {**email["content"], "subject": "New subject"},
                                 "base_version": email["version"]}).json()["asset"]
    gone = client.put(url, json={"content": {**email["content"], "sections": [{**sections[0], "body": "Rewritten."}]},
                                 "base_version": kept["version"]}).json()["asset"]

    assert kept["warnings"] == [claim]  # its words are still there
    assert gone["warnings"] == []  # was kept after the quoted words were deleted


def test_the_which_asset_question_offers_every_asset():
    assets = [Asset(type="x_post", title=f"Post {n}", position=n - 1) for n in range(1, 7)]
    unclear = {"action": "edit", "targets": [], "instruction": "Shorten it.", "research_query": "", "reply": "",
               "ask": {"question": "", "options": []}, "new_assets": []}

    route = editing.route_from(unclear, assets)

    assert route.ask["options"] == [f"{n}. Post {n}" for n in range(1, 7)]  # was the first 4 only


def test_the_which_asset_card_in_the_chat_lists_every_asset(client: TestClient, brand: int):
    chat_id = _written(client, "Launch Acme Widget on January 26 with every asset type.")

    card = _send(client, chat_id, "Shorten one of them")[-1]

    assert card["kind"] == "question"
    assert [o["label"] for o in card["data"]["options"]] == [
        "1. Launch email", "2. Launch post", "3. X launch post", "4. Launch blog", "5. Launch page"]  # was cut to 4


def test_a_citation_not_in_the_approved_research_is_a_warning(client: TestClient, brand: int):
    chat_id = _written(client, f"{BRIEF} Invent a source.")

    warnings = [w for a in _assets(client, chat_id) for w in a["warnings"]]
    assert any(w["check"] == "citation" and "made-up.example" in w["problem"] for w in warnings)


# Research

def test_research_findings_show_on_the_plan_with_source_and_date(client: TestClient, brand: int,
                                                                fake_web: FakeWebResearch):
    chat_id = _planned(client, f"{BRIEF} Plan it with research.")

    research = client.get(f"/api/chats/{chat_id}").json()["campaign"]["research"]
    assert fake_web.queries == ["widget market size"]
    assert [(f["finding"], f["url"], f["date"], f["asset_ids"]) for f in research] == [
        ("The widget market grew 12% in 2026.", "https://example.org/widgets", "2026-05-01", ["a2"])
    ]  # the finding whose sentence isn't on the page was dropped
    calls = client.get("/api/ai-calls", params={"chat_id": chat_id}).json()
    assert any(c["step"].startswith("Research notes") for c in calls)


def test_a_removed_finding_stays_out_of_writing(client: TestClient, brand: int, fake_ai: FakeTransport):
    chat_id = _planned(client, f"{BRIEF} Plan it with research.")
    finding = client.get(f"/api/chats/{chat_id}").json()["campaign"]["research"][0]

    assert client.delete(f"/api/chats/{chat_id}/research/{finding['id']}").status_code == 200
    client.post(f"/api/chats/{chat_id}/approve")

    writes = _schema_requests(fake_ai, "linkedin_post_asset")
    assert "example.org" not in writes[0].prompt.campaign + writes[0].prompt.task[-1].content


def test_kept_findings_reach_only_their_assets_and_searches_run_once(client: TestClient, brand: int,
                                                                     fake_ai: FakeTransport, fake_web: FakeWebResearch):
    chat_id = _planned(client, f"{BRIEF} Plan it with research.")
    _send(client, chat_id, "Drop the X post.")
    client.post(f"/api/chats/{chat_id}/approve")

    assert fake_web.queries == ["widget market size"]
    linkedin = _assets(client, chat_id)[1]
    assert linkedin["content"]["sources"] == ["https://example.org/widgets"]
    assert not any(w["check"] == "citation" for w in linkedin["warnings"])
    email_task = _schema_requests(fake_ai, "email_asset")[0].prompt.task[-1].content
    assert "example.org" not in email_task.split("=== APPROVED RESEARCH FOR THIS ASSET ===")[1]


def test_asking_for_a_better_source_searches_again_without_the_old_page(client: TestClient, brand: int,
                                                                        fake_web: FakeWebResearch):
    chat_id = _planned(client, f"{BRIEF} Plan it with research.")
    finding = client.get(f"/api/chats/{chat_id}").json()["campaign"]["research"][0]

    messages = client.post(f"/api/chats/{chat_id}/research/{finding['id']}/better").json()

    assert "nothing new turned up, so the finding is kept" in messages[-1]["content"]
    research = client.get(f"/api/chats/{chat_id}").json()["campaign"]["research"]
    assert [f["removed"] for f in research] == [False]  # the only page was the old one; was removed anyway
    assert len(fake_web.queries) == 2


# Editing

def test_a_chat_edit_changes_one_asset_and_saves_a_version(client: TestClient, brand: int, fake_web: FakeWebResearch):
    chat_id = _written(client)
    before = _assets(client, chat_id)

    reply = _send(client, chat_id, "Shorten the second post")[-1]

    after = _assets(client, chat_id)
    assert after[1]["content"]["text"] == "Short."
    assert after[0] == before[0] and after[2] == before[2]
    assert after[1]["version"] == before[1]["version"] + 1
    assert reply["kind"] == "edit" and "Edit cost: $" in reply["content"]
    assert fake_web.queries == []


def test_a_named_field_is_the_only_one_that_changes(client: TestClient, brand: int):
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]

    _send(client, chat_id, "Shorten the second post")  # names the text field

    after = _assets(client, chat_id)[1]
    assert after["content"]["text"] == "Short."
    assert after["content"]["author"] == linkedin["content"]["author"]


def test_an_edit_with_no_field_may_change_the_whole_asset(client: TestClient, brand: int):
    chat_id = _written(client)

    _send(client, chat_id, "Make it shorter everywhere")

    assert _assets(client, chat_id)[0]["content"]["subject"] == "A new subject"


def test_a_wide_edit_lists_every_asset_it_changed(client: TestClient, brand: int):
    chat_id = _written(client)

    reply = _send(client, chat_id, "Make it shorter everywhere")[-1]

    assert reply["content"].count("\n- ") == 3


def test_an_unclear_edit_gets_a_question_card_then_runs(client: TestClient, brand: int):
    chat_id = _written(client)

    card = _send(client, chat_id, "Tweak it")[-1]
    assert card["kind"] == "question"

    answer = client.post(f"/api/chats/{chat_id}/answer", json={"question_id": card["data"]["id"], "answer": "The email"})
    assert answer.status_code == 201, answer.text


def test_undo_restores_the_previous_version(client: TestClient, brand: int):
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]
    _send(client, chat_id, "Shorten the second post")

    undone = client.post(f"/api/chats/{chat_id}/assets/{linkedin['id']}/undo").json()

    assert undone["content"] == linkedin["content"]
    versions = client.get(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions").json()
    assert [v["reason"] for v in versions][-2:] == ["chat edit", "undo"]
    again = client.post(f"/api/chats/{chat_id}/assets/{linkedin['id']}/undo")
    assert again.status_code == 400  # nothing before the first draft


def test_any_earlier_version_can_be_restored_after_an_undo(client: TestClient, brand: int):
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]
    _send(client, chat_id, "Shorten the second post")
    shortened = _assets(client, chat_id)[1]
    client.post(f"/api/chats/{chat_id}/assets/{linkedin['id']}/undo")
    calls_before = len(client.get("/api/ai-calls", params={"chat_id": chat_id}).json())

    restored = client.post(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions/{shortened['version']}/restore")

    assert restored.status_code == 200, restored.text
    assert restored.json()["content"] == shortened["content"]
    versions = client.get(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions").json()
    assert (versions[-1]["reason"], versions[-1]["note"]) == ("restore", f"Back to version {shortened['version']}")
    assert len(client.get("/api/ai-calls", params={"chat_id": chat_id}).json()) == calls_before  # free
    already = client.post(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions/{versions[-1]['number']}/restore")
    missing = client.post(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions/99/restore")
    assert already.status_code == missing.status_code == 400


def test_a_chat_edit_that_changes_nothing_makes_no_new_version(client: TestClient, brand: int):
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]

    reply = _send(client, chat_id, "Go back to version 2")[-1]

    after = _assets(client, chat_id)[1]
    assert (after["version"], after["content"]) == (linkedin["version"], linkedin["content"])
    versions = client.get(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions").json()
    assert [v["reason"] for v in versions] == ["written"]
    assert "not changed, so no new version" in reply["content"]


def test_new_assets_can_be_added_after_writing(client: TestClient, brand: int):
    chat_id = _written(client)
    before = _assets(client, chat_id)

    reply = _send(client, chat_id, "Make two more X posts")

    after = _assets(client, chat_id)
    added = after[len(before):]
    assert [(a["type"], a["title"], a["state"]) for a in added] == [
        ("x_post", "Widget teaser", "done"), ("x_post", "Widget launch day", "done")]
    assert [a["position"] for a in added] == [3, 4]
    assert [(a["id"], a["version"], a["content"]) for a in after[:3]] == [
        (a["id"], a["version"], a["content"]) for a in before]  # the written assets are untouched
    campaign = client.get(f"/api/chats/{chat_id}").json()["campaign"]
    assert campaign["stage"] == "done"
    assert [c["title"] for c in campaign["plan"]["assets"][3:]] == ["Widget teaser", "Widget launch day"]
    assert len({c["id"] for c in campaign["plan"]["assets"]}) == 5
    assert campaign["plan"]["summary"].endswith("Added after writing: 2 X posts (“Widget teaser” and “Widget launch day”).")
    note = next(m for m in reply if m["kind"] == "edit")
    assert "Widget teaser" in note["content"] and "stay as they are" in note["content"]


def test_an_asset_can_be_removed_by_chat_and_brought_back(client: TestClient, brand: int):
    chat_id = _written(client)
    before = _assets(client, chat_id)
    plan_before = client.get(f"/api/chats/{chat_id}").json()["campaign"]["plan"]["assets"]

    note = next(m for m in _send(client, chat_id, "Drop the second post") if m["kind"] == "removed")

    after = _assets(client, chat_id)
    assert [a["id"] for a in after] == [before[0]["id"], before[2]["id"]]  # gone from the tabs, not emptied
    plan = client.get(f"/api/chats/{chat_id}").json()["campaign"]["plan"]
    assert [c["id"] for c in plan["assets"]] == [plan_before[0]["id"], plan_before[2]["id"]]
    assert [c["id"] for c in plan["removed"]] == [plan_before[1]["id"]]
    assert before[1]["title"] in note["content"] and "press Undo" in note["content"]
    assert [v["reason"] for v in client.get(f"/api/chats/{chat_id}/assets/{before[1]['id']}/versions").json()] == ["written"]

    assert client.post(f"/api/chats/{chat_id}/removed/{note['id']}/undo").status_code == 200

    back = _assets(client, chat_id)
    assert [(a["id"], a["content"], a["state"]) for a in back] == [(a["id"], a["content"], a["state"]) for a in before]
    assert client.get(f"/api/chats/{chat_id}").json()["campaign"]["plan"]["assets"] == plan_before
    undone = next(m for m in _messages(client, chat_id) if m["id"] == note["id"])
    assert undone["data"]["undone"] is True
    assert client.post(f"/api/chats/{chat_id}/removed/{note['id']}/undo").status_code == 200  # twice is harmless


def test_every_asset_cannot_be_removed(client: TestClient, brand: int):
    chat_id = _written(client)

    reply = _send(client, chat_id, "Remove everything")[-1]

    assert "at least one has to stay" in reply["content"]
    assert len(_assets(client, chat_id)) == 3


def test_an_edit_that_would_empty_an_asset_is_not_saved(client: TestClient, brand: int):
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]

    reply = next(m for m in _send(client, chat_id, "Empty the second post") if m["kind"] == "edit")

    after = _assets(client, chat_id)[1]
    assert (after["version"], after["content"]) == (linkedin["version"], linkedin["content"])  # was a blank version 2
    assert "would have left it with no text" in reply["content"]


def test_an_empty_asset_fails_the_free_checks():
    empty = {"author": "Acme", "text": " ", "hashtags": [], "sources": []}

    assert [p.check for p in free_checks("linkedin_post", empty, CheckRules())] == ["empty"]


def test_a_landing_page_has_a_main_button_and_a_second_link(client: TestClient, brand: int):
    section = writer.FIELDS["landing_page"]["sections"]["items"]["properties"]
    assert {"button_text", "button_link", "link_text", "link_url"} <= set(section)  # had no link fields at all
    page = {"sections": [{"kind": "hero", "heading": "Acme Widget", "body": "Small and safe.", "items": [],
                          "button_text": "Book a demo", "button_link": "https://acme.example/demo",
                          "link_text": "Read the docs", "link_url": "https://acme.example/docs"}], "sources": []}

    assert free_checks("landing_page", page, CheckRules()) == []  # the links are not taken for citations


def test_an_optional_draft_is_marked_on_its_asset_and_told_to_the_writer(client: TestClient, brand: int,
                                                                         fake_ai: FakeTransport):
    chat_id = _planned(client)
    cards = client.get(f"/api/chats/{chat_id}").json()["campaign"]["plan"]["assets"]
    cards[1] = {**cards[1], "draft_for": "Maren"}
    assert client.put(f"/api/chats/{chat_id}/plan", json={"assets": cards}).status_code == 200

    client.post(f"/api/chats/{chat_id}/approve")

    assets = _assets(client, chat_id)
    assert [a["draft_for"] for a in assets] == ["", "Maren", ""]
    writes = [r for r in fake_ai.requests if r.prompt.task[-1].content.startswith("Write asset 2 of the approved plan")]
    assert '"draft_for": "Maren"' in writes[0].prompt.task[-1].content
    assert "only an optional draft for that person" in writes[0].prompt.task[-1].content


def test_approving_a_one_asset_plan_says_so_in_the_singular(client: TestClient, brand: int):
    chat_id = _planned(client)
    plan = client.get(f"/api/chats/{chat_id}").json()["campaign"]["plan"]
    assert client.put(f"/api/chats/{chat_id}/plan", json={"assets": plan["assets"][:1]}).status_code == 200

    note = client.post(f"/api/chats/{chat_id}/approve").json()[0]

    assert note["content"] == "Plan approved. Writing it now."  # was "Writing 1 assets, a few at a time."


def test_a_document_choice_note_reads_as_a_sentence():
    conflict = Conflict(topic="product naming", rule="approved")

    note = agent._note(conflict, "acme/naming.md", ["acme/old/guide-v3.md", "acme/messaging-2024.md"])

    assert note == ("On product naming, I'm following naming.md rather than guide-v3.md and messaging-2024.md, "
                    "because the others are only a draft.")


def test_an_edit_with_no_clear_target_never_offers_a_single_choice():
    one = [Asset(type="x_post", title="What the default policy does", position=0)]
    two = [*one, Asset(type="email", title="Launch email", position=1)]
    unclear = {"action": "edit", "targets": [], "instruction": "Create two additional X posts.", "research_query": "",
               "reply": "", "ask": {"question": "", "options": []}, "new_assets": []}

    alone = editing.route_from(unclear, one)  # was a "Which asset?" card with one option
    choice = editing.route_from(unclear, two)

    assert alone.action == "answer" and "What the default policy does" in alone.reply
    assert choice.action == "ask" and choice.ask["options"] == ["1. What the default policy does", "2. Launch email"]


def test_a_hand_edit_runs_free_checks_and_costs_nothing(client: TestClient, brand: int):
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]
    calls_before = len(client.get("/api/ai-calls", params={"chat_id": chat_id}).json())

    response = client.put(f"/api/chats/{chat_id}/assets/{linkedin['id']}",
                          json={"content": {**linkedin["content"], "text": "Pure synergy for platform leads."}})

    assert response.status_code == 200, response.text
    asset = response.json()["asset"]
    assert asset["content"]["text"] == "Pure synergy for platform leads."
    assert [w["check"] for w in asset["warnings"]] == ["banned word"]
    assert len(client.get("/api/ai-calls", params={"chat_id": chat_id}).json()) == calls_before
    versions = client.get(f"/api/chats/{chat_id}/assets/{linkedin['id']}/versions").json()
    assert (versions[-1]["reason"], versions[-1]["cost_usd"]) == ("hand edit", 0)


def test_the_same_hand_fix_in_two_campaigns_offers_to_remember_it(client: TestClient, brand: int):
    offers = []
    for _ in range(2):
        chat_id = _written(client)
        email = _assets(client, chat_id)[0]
        content = {**email["content"], "sections": [{"heading": "", "body": "Acme Widget is here for platform teams."}]}
        offers.append(client.put(f"/api/chats/{chat_id}/assets/{email['id']}", json={"content": content}).json()["messages"])

    assert offers[0] == []
    assert offers[1][0]["kind"] == "remember_offer"  # was never offered: each campaign counted on its own


def test_the_same_hand_fix_twice_offers_to_remember_it(client: TestClient, brand: int):
    chat_id = _written(client)
    email, linkedin = _assets(client, chat_id)[:2]
    email_content = {**email["content"], "sections": [{"heading": "", "body": "Acme Widget is here for platform teams."}]}
    client.put(f"/api/chats/{chat_id}/assets/{email['id']}", json={"content": email_content})

    second = client.put(f"/api/chats/{chat_id}/assets/{linkedin['id']}",
                        json={"content": {**linkedin["content"], "text": "Acme Widget is here for platform teams."}}).json()

    offer = second["messages"][0]
    assert offer["kind"] == "remember_offer" and "“teams”" in offer["data"]["text"]
    saved = client.post(f"/api/chats/{chat_id}/remember/{offer['id']}").json()
    assert saved[0]["kind"] == "memory"


def test_check_again_runs_the_ai_check(client: TestClient, brand: int):
    chat_id = _written(client)
    asset = _assets(client, chat_id)[0]

    response = client.post(f"/api/chats/{chat_id}/assets/{asset['id']}/check")

    assert response.status_code == 200
    assert "Checked" in response.json()["messages"][0]["content"]


# Costs

def test_the_cost_report_has_stages_assets_and_edits(client: TestClient, brand: int):
    chat_id = _written(client)
    _send(client, chat_id, "Shorten the second post")

    report = client.get(f"/api/chats/{chat_id}/costs").json()

    stages = {s["stage"] for s in report["stages"]}
    assert {"Questions", "Plan", "Writing", "Checks", "Edits", "Memory"} <= stages
    assert len(report["assets"]) == 3
    assert report["edits"][0]["reason"] == "chat edit"
    assert 0 <= report["total"]["cache_hit_rate"] <= 1


def test_writing_cut_off_by_a_restart_starts_again(client: TestClient, brand: int, fake_ai: FakeTransport,
                                                    fake_web: FakeWebResearch, settings):
    from app.campaign.models import Campaign
    from app.campaign.runtime import Runtime
    from app.campaign.writing import resume_interrupted
    from app.db import SessionLocal
    from app.jobs import InlineJobRunner

    chat_id = _written(client)
    with SessionLocal() as session:
        campaign = session.query(Campaign).filter_by(chat_id=chat_id).one()
        campaign.stage, campaign.assets[2].state = "writing", "writing"
        session.commit()

    resume_interrupted(Runtime(SessionLocal, fake_ai, settings, InlineJobRunner(), fake_web))

    assert client.get(f"/api/chats/{chat_id}").json()["campaign"]["stage"] == "done"
    assert _assets(client, chat_id)[2]["state"] == "done"


def _section(task: str, name: str) -> str:
    return task.split(f"=== {name} ===\n", 1)[1].split("\n\n===", 1)[0]


def test_a_chat_edit_sees_the_same_channel_rules_and_facts_as_the_first_draft(client: TestClient, brand: int,
                                                                              fake_ai: FakeTransport):
    """The bug: the edit prompt told the model to keep the brand's rules and facts but never gave them."""
    chat_id = _written(client)

    _send(client, chat_id, "Make it shorter everywhere")

    write = _schema_requests(fake_ai, "email_asset")[0].prompt.task[-1].content
    edit = next(r for r in _schema_requests(fake_ai, "email_asset")
                if "changed" in r.output_schema.schema["properties"]).prompt.task[-1].content
    assert "=== CHANNEL RULES ===" in edit and "=== FACTS FOR THIS ASSET ===" in edit
    assert _section(edit, "CHANNEL RULES") == _section(write, "CHANNEL RULES")
    assert _section(edit, "FACTS FOR THIS ASSET") == _section(write, "FACTS FOR THIS ASSET")


# Group 3 of the design review: undo, restore and failed edits keep the whole earlier state

def _versions(client: TestClient, chat_id: int, asset_id: int) -> list[dict]:
    return client.get(f"/api/chats/{chat_id}/assets/{asset_id}/versions").json()


def _checks_answer(fake_ai: FakeTransport, problems: list[dict]) -> None:
    default = brand_brain.reply
    fake_ai._default = lambda request: json.dumps({"problems": problems}) \
        if request.output_schema and request.output_schema.name == "asset_check" else default(request)


def test_undo_after_check_again_shows_what_the_check_found(client: TestClient, brand: int, fake_ai: FakeTransport):
    """Check again used to update the asset but not its version, so going back to that version brought back
    the list from before the check."""
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]
    quote = " ".join(linkedin["content"]["text"].split()[:3])
    url = f"/api/chats/{chat_id}/assets/{linkedin['id']}"
    _checks_answer(fake_ai, [{"check": "claim", "quote": quote, "problem": "Not in the facts.", "fix": "Cut it."}])
    client.post(f"{url}/check")
    fake_ai._default = brand_brain.reply
    checked = _assets(client, chat_id)[1]
    client.put(url, json={"content": {**checked["content"], "author": "Mira Holt"}, "base_version": checked["version"]})
    edited = _assets(client, chat_id)[1]

    client.post(f"{url}/undo?base_version={edited['version']}")

    back = _assets(client, chat_id)[1]
    assert back["content"] == checked["content"]
    assert [w["check"] for w in back["warnings"]] == ["claim"]  # was [], as before the check
    assert _versions(client, chat_id, linkedin["id"])[checked["version"] - 1]["warnings"] == checked["warnings"]


def test_a_not_checked_warning_cleared_by_check_again_stays_cleared_after_undo(client: TestClient, brand: int,
                                                                              fake_ai: FakeTransport):
    state = {"failed": False}

    def first_check_fails(request: AiRequest):
        if not state["failed"] and request.output_schema and request.output_schema.name == "asset_check":
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = first_check_fails
    chat_id = _written(client)
    email = _assets(client, chat_id)[0]  # written first, so its check is the one that failed
    assert [w["check"] for w in email["warnings"]] == ["not checked"]
    url = f"/api/chats/{chat_id}/assets/{email['id']}"
    client.post(f"{url}/check")
    cleared = _assets(client, chat_id)[0]
    assert cleared["warnings"] == []
    client.put(url, json={"content": {**cleared["content"], "sender": "Mira Holt"}, "base_version": cleared["version"]})

    client.post(f"{url}/undo?base_version={_assets(client, chat_id)[0]['version']}")

    assert _assets(client, chat_id)[0]["warnings"] == []  # "not checked" used to come back


def test_a_chat_edit_whose_checks_fail_is_kept_as_not_checked(client: TestClient, brand: int, fake_ai: FakeTransport):
    """It used to be paid for, then thrown away with a 502."""
    chat_id = _written(client)
    linkedin = _assets(client, chat_id)[1]
    state = {"failed": False}

    def check_fails(request: AiRequest):
        if not state["failed"] and request.output_schema and request.output_schema.name == "asset_check":
            state["failed"] = True
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = check_fails
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Shorten the second post"})

    assert response.status_code == 201, response.text
    after = _assets(client, chat_id)[1]
    assert after["version"] == linkedin["version"] + 1 and after["content"]["text"] == "Short."
    assert [w["check"] for w in after["warnings"]] == ["not checked"]
    assert _versions(client, chat_id, linkedin["id"])[-1]["reason"] == "chat edit"
    edit = next(m for m in response.json() if m["kind"] == "edit")
    assert "its checks couldn't run, so press Check again" in edit["content"]


def test_a_wide_edit_lists_every_asset_even_when_one_edit_fails(client: TestClient, brand: int, fake_ai: FakeTransport):
    chat_id = _written(client)
    before = _assets(client, chat_id)
    edits = []

    def second_edit_fails(request: AiRequest):
        extra = request.output_schema.schema["properties"] if request.output_schema else {}
        if "changed" in extra:
            edits.append(request)
            if len(edits) == 2:
                raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = second_edit_fails
    response = client.post(f"/api/chats/{chat_id}/messages", json={"content": "Make it shorter everywhere"})

    assert response.status_code == 201, response.text  # was a 502, with the first edit saved but not mentioned
    edit = next(m for m in response.json() if m["kind"] == "edit")
    lines = edit["content"].splitlines()[1:4]
    assert "Made it shorter" in lines[0] and "couldn't be edited" in lines[1] and "Made it shorter" in lines[2]
    after = _assets(client, chat_id)
    assert [a["version"] - b["version"] for a, b in zip(after, before)] == [1, 0, 1]
