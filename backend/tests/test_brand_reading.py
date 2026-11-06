import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.deps import get_ai_transport
from app.ai.fake import FakeTransport
from app.ai.transport import AiRequest
from app.brand.models import BrandFile, Section
from app.brand.reading import reader as reader_module
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.jobs import InlineJobRunner, get_job_runner
from app.main import create_app
from tests import brand_brain
from tests.brand_brain import calls_for

GUIDE = """---
title: Voice guide
owner: Mira Holt
---
# Voice guide

Status: current. This guide replaces the 2023 voice guide.

## Tone

Write short sentences. Name the product on first mention.
"""

OLD_GUIDE = """# Voice guide 2023

Superseded. Kept for history.

## Tone

Be playful.
"""

NOTES = """# Sales notes

INTERNAL. Do not forward to customers.

We say we are certified. Check this.
"""

FILES = {
    "acme/guide.md": GUIDE,
    "acme/old/voice-guide-2023-old.md": OLD_GUIDE,
    "acme/internal/sales-notes.md": NOTES,
    "acme/briefs/launch-brief.md": "# Brief\n\nLaunch it.",
    "acme/images/logo.png": "png-bytes",
    "acme/.DS_Store": "junk",
}


def _document(request: AiRequest) -> str:
    return request.prompt.task[-1].content.split("--- DOCUMENT ---\n", 1)[1]


def _card(status="unknown", status_evidence="", safe="unknown", safe_evidence="", replaces=()):
    return {
        "summary": "A document.",
        "kind": "rule",
        "claimed_status": {"value": status, "evidence": status_evidence},
        "date": {"as_written": "", "iso": "", "evidence": ""},
        "owner": {"name": "", "role": "", "evidence": ""},
        "safe_to_quote": {"value": safe, "evidence": safe_evidence},
        "rules_on": [],
        "replaces": list(replaces),
        "claims_about_other_documents": [],
        "mentions": {"products": [], "channels": [], "customers": [], "people": []},
    }


def card_reply(request: AiRequest) -> str:
    """A fake model that quotes real sentences, except for one invented quote in the old guide."""
    document = _document(request)
    if "replaces the 2023" in document:
        card = _card(
            "current",
            "Status: current.",
            replaces=[{"document": "2023 voice guide", "evidence": "This guide replaces the 2023 voice guide."}],
        )
    elif "INTERNAL" in document:
        card = _card(safe="no", safe_evidence="INTERNAL. Do not forward to customers.")
    else:
        card = _card("current", "This guide is the current one.")  # not in the document
    return json.dumps(card)


def _upload(client: TestClient, files=FILES, exclude=("briefs",), name="Acme"):
    return client.post(
        "/api/brands",
        data={"name": name, "exclude": list(exclude)},
        files=[("files", (path, content.encode())) for path, content in files.items()],
    )


def _is_card(request: AiRequest) -> bool:
    return request.output_schema is not None and request.output_schema.name == "document_card"


def reply(request: AiRequest) -> str:
    """Cards come from `card_reply`; the later reading steps get the shared fake brand brain."""
    return card_reply(request) if _is_card(request) else brand_brain.reply(request)


@pytest.fixture(autouse=True)
def fake_cards(fake_ai: FakeTransport) -> None:
    fake_ai._default = reply


def _documents_by_path(client: TestClient, brand_id: int) -> dict[str, dict]:
    brand = client.get(f"/api/brands/{brand_id}").json()
    return {doc["path"]: doc for doc in brand["documents"]}


def test_upload_reads_the_brand(client: TestClient):
    response = _upload(client)

    assert response.status_code == 201
    brand = client.get(f"/api/brands/{response.json()['id']}").json()
    assert brand["status"] == "ready"
    assert brand["documents_total"] == brand["documents_done"] == 3
    assert brand["reviewed"] is False


def test_folder_name_is_dropped_and_excluded_and_hidden_files_are_left_out(client: TestClient):
    brand_id = _upload(client).json()["id"]
    brand = client.get(f"/api/brands/{brand_id}").json()

    assert sorted(doc["path"] for doc in brand["documents"]) == [
        "guide.md",
        "internal/sales-notes.md",
        "old/voice-guide-2023-old.md",
    ]
    assert brand["other_files"] == [{"path": "images/logo.png", "kind": "image", "size_bytes": 9}]


def test_basic_facts_are_found_without_ai(client: TestClient):
    documents = _documents_by_path(client, _upload(client).json()["id"])

    guide = documents["guide.md"]["basics"]
    assert guide["frontmatter"] == {"title": "Voice guide", "owner": "Mira Holt"}
    assert guide["top_labels"] == {"status": "current. This guide replaces the 2023 voice guide."}
    assert [h["text"] for h in guide["headings"]] == ["Voice guide", "Tone"]
    old = documents["old/voice-guide-2023-old.md"]["basics"]
    assert old["name_hints"] == ["old", "year 2023"]
    assert old["folder"] == "old"


def test_cards_keep_claims_whose_quotes_are_in_the_document(client: TestClient):
    documents = _documents_by_path(client, _upload(client).json()["id"])

    guide = documents["guide.md"]["card"]
    assert guide["claimed_status"] == {"value": "current", "evidence": "Status: current."}
    assert guide["replaces"][0]["document"] == "2023 voice guide"
    notes = documents["internal/sales-notes.md"]["card"]
    assert notes["safe_to_quote"]["value"] == "no"
    assert notes["unverified"] == []


def test_a_claim_with_an_invented_quote_goes_back_to_unknown(client: TestClient):
    documents = _documents_by_path(client, _upload(client).json()["id"])

    old = documents["old/voice-guide-2023-old.md"]["card"]
    assert old["claimed_status"] == {"value": "unknown", "evidence": ""}
    assert old["unverified"] == [
        {"field": "claimed_status", "value": "current", "evidence": "This guide is the current one."}
    ]


def test_a_one_word_quote_or_the_bare_value_is_not_proof():
    """"Maren" is in the document, so it used to prove that Maren owns it."""
    from app.brand.reading.cards import checked_card
    document = "# Launch notes\n\nOwner: Maren Tolliver\nStatus: draft\nMaren wrote most of this.\n"
    reply = {"claimed_status": {"value": "draft", "evidence": "draft"},
             "date": {"as_written": "", "iso": "", "evidence": ""},
             "owner": {"name": "Maren", "role": "", "evidence": "Maren"},
             "safe_to_quote": {"value": "unknown", "evidence": ""},
             "replaces": [], "claims_about_other_documents": []}

    card = checked_card(json.dumps(reply), document)
    assert card["owner"]["name"] == "" and card["claimed_status"]["value"] == "unknown"
    assert [u["field"] for u in card["unverified"]] == ["claimed_status", "owner"]

    proved = {**reply, "claimed_status": {"value": "draft", "evidence": "Status: draft"},
              "owner": {"name": "Maren Tolliver", "role": "", "evidence": "Owner: Maren Tolliver"}}
    card = checked_card(json.dumps(proved), document)
    assert card["owner"]["name"] == "Maren Tolliver" and card["claimed_status"]["value"] == "draft"
    assert card["unverified"] == []


def test_documents_are_split_into_sections_with_search_vectors(client: TestClient, fake_ai: FakeTransport):
    documents = _documents_by_path(client, _upload(client).json()["id"])

    assert all(doc["sections"] >= 1 for doc in documents.values())
    embedded = [text for request in fake_ai.embed_requests for text in request.texts]
    assert sum(doc["sections"] for doc in documents.values()) == len(embedded)
    assert any("Write short sentences." in text for text in embedded)


def test_reading_again_skips_unchanged_documents(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client).json()["id"]
    calls_before = (len(fake_ai.requests), len(fake_ai.embed_requests))

    response = client.post(f"/api/brands/{brand_id}/read")

    assert response.status_code == 200
    assert (len(fake_ai.requests), len(fake_ai.embed_requests)) == calls_before
    assert client.get(f"/api/brands/{brand_id}").json()["status"] == "ready"


def test_a_failed_card_does_not_stop_the_others_and_is_retried(client: TestClient, fake_ai: FakeTransport):
    def fail_for_notes(request: AiRequest) -> str:
        if "INTERNAL" in _document(request):
            raise RuntimeError("timeout")
        return card_reply(request)

    fake_ai._default = lambda request: fail_for_notes(request) if _is_card(request) else reply(request)
    brand_id = _upload(client).json()["id"]

    documents = _documents_by_path(client, brand_id)
    assert "timeout" in documents["internal/sales-notes.md"]["card_error"]
    assert documents["guide.md"]["card"] is not None
    assert client.get(f"/api/brands/{brand_id}").json()["status"] == "ready"

    fake_ai._default = reply
    cards_before = calls_for(fake_ai.requests, "document_card")
    client.post(f"/api/brands/{brand_id}/read")

    assert calls_for(fake_ai.requests, "document_card") == cards_before + 1
    assert _documents_by_path(client, brand_id)["internal/sales-notes.md"]["card_error"] is None


def test_reading_cost_is_reported_apart_from_chats(client: TestClient):
    brand_id = _upload(client).json()["id"]
    chat_id = client.post("/api/chats").json()["id"]
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "hello"})

    cost = client.get(f"/api/brands/{brand_id}").json()["reading_cost"]

    all_calls = client.get("/api/ai-calls").json()
    assert any(c["chat_id"] == chat_id for c in all_calls)
    assert cost["calls"] == sum(1 for c in all_calls if c["chat_id"] is None)  # chat calls aren't reading
    assert cost["usd"] > 0


def test_card_calls_can_be_inspected(client: TestClient):
    documents = _documents_by_path(client, _upload(client).json()["id"])

    call = client.get(f"/api/ai-calls/{documents['guide.md']['card_call_id']}").json()

    assert call["step"] == "Brand reading: document card (guide.md)"
    assert call["model"] == "gpt-6-luna"
    assert "Write short sentences." in call["request"]["input"][-1]["content"]


def test_a_folder_without_documents_is_refused(client: TestClient):
    response = _upload(client, files={"acme/logo.png": "png"})

    assert response.status_code == 400


def test_paths_that_leave_the_folder_are_refused(client: TestClient):
    response = _upload(client, files={"../escape.md": "# Hi"})

    assert response.status_code == 400


def test_the_brand_is_marked_reviewed(client: TestClient):
    brand_id = _upload(client).json()["id"]

    assert client.post(f"/api/brands/{brand_id}/reviewed").json()["reviewed"] is True


def _start_app(fake_ai: FakeTransport, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_ai_transport] = lambda: fake_ai
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_job_runner] = InlineJobRunner
    return TestClient(app)


def test_the_settings_folder_is_preloaded_once(fake_ai: FakeTransport, settings: Settings, tmp_path: Path):
    folder = tmp_path / "preload" / "acme"
    for path, content in FILES.items():
        target = folder / path.removeprefix("acme/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    settings = settings.model_copy(update={"brand_dir": folder, "brand_exclude": "briefs"})

    with _start_app(fake_ai, settings) as client:
        brands = client.get("/api/brands").json()
    with _start_app(fake_ai, settings) as client:
        assert client.get("/api/brands").json() == brands

    assert len(brands) == 1
    assert brands[0]["name"] == "acme"
    assert brands[0]["documents_total"] == 3


def test_a_blank_brand_folder_setting_means_no_preload():
    assert Settings(brand_dir="").brand_dir is None
    assert Settings(brand_dir="  ").brand_dir is None


def test_a_failed_embedding_keeps_the_old_sections(client: TestClient, fake_ai: FakeTransport,
                                                   monkeypatch: pytest.MonkeyPatch):
    """The old sections used to be deleted before the new vectors were made, and the first embedding call's
    log committed that delete: a later failure left the document with no sections at all."""
    brand_id = _upload(client).json()["id"]
    with SessionLocal() as session:
        guide = session.scalars(select(BrandFile).where(BrandFile.brand_id == brand_id, BrandFile.path == "guide.md")).one()
        before = [s.text for s in session.scalars(select(Section).where(Section.file_id == guide.id).order_by(Section.position))]
    assert before
    monkeypatch.setattr(reader_module, "EMBED_BATCH", 1)
    embed, calls = fake_ai.embed, []

    def fail_on_the_second_batch(request):
        calls.append(request)
        if len(calls) == 2:
            raise RuntimeError("The embedding service is down")
        return embed(request)

    monkeypatch.setattr(fake_ai, "embed", fail_on_the_second_batch)
    changed = {"acme/guide.md": GUIDE + "\nOne idea per paragraph.\n", "acme/internal/sales-notes.md": NOTES + "\nAsk Mira.\n"}
    client.post(f"/api/brands/{brand_id}/files", files=[("files", (p, c.encode())) for p, c in changed.items()])

    assert len(calls) == 2  # two documents, one section each: the first batch worked, the second failed
    with SessionLocal() as session:
        guide = session.get_one(BrandFile, guide.id)
        after = [s.text for s in session.scalars(select(Section).where(Section.file_id == guide.id).order_by(Section.position))]
        assert after == before
        assert guide.sections_sha256 != guide.sha256  # still to be indexed, so the next read tries again
