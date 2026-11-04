"""Facts, names, document statuses, conflicts, the summary and corrections, through the API."""

import pytest
from fastapi.testclient import TestClient

from app.ai.fake import FakeTransport
from tests import brand_brain
from tests.brand_brain import BRAND, NEW_GUIDE, calls_for


@pytest.fixture(autouse=True)
def brain(fake_ai: FakeTransport) -> None:
    fake_ai._default = brand_brain.reply


def _upload(client: TestClient, files=BRAND) -> int:
    response = client.post(
        "/api/brands",
        data={"name": "Acme", "exclude": ["briefs"]},
        files=[("files", (path, content.encode())) for path, content in files.items()],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _brand(client: TestClient, brand_id: int) -> dict:
    return client.get(f"/api/brands/{brand_id}").json()


def _docs(brand: dict) -> dict[str, dict]:
    return {doc["path"]: doc for doc in brand["documents"]}


def _conflict(brand: dict, topic: str) -> dict:
    return next(c for c in brand["conflicts"] if c["topic"] == topic)


def test_a_replaced_document_is_marked_with_the_reason(client: TestClient):
    docs = _docs(_brand(client, _upload(client)))

    old = docs["old/voice-guide-2023-old.md"]
    assert old["status"] == "replaced"
    assert old["replaced_by"] == "guide.md"
    assert 'guide.md says it replaces this: "This guide replaces the 2023 voice guide."' in old["status_reason"]
    assert docs["guide.md"]["status"] == "current"
    assert docs["legal/certifications.md"]["status"] == "current"


def test_old_names_are_kept_with_their_proof(client: TestClient):
    entities = _brand(client, _upload(client))["entities"]

    assert entities == [
        {
            "name": "Acme Widget",
            "kind": "product",
            "short_forms": ["Widget"],
            "old_names": [
                {"name": "Gizmo", "evidence": "Acme Widget, formerly called Gizmo, is our product.", "path": "guide.md"}
            ],
        }
    ]


def test_facts_under_an_old_name_are_compared_with_the_new_name(client: TestClient):
    tone = _conflict(_brand(client, _upload(client)), "tone")

    assert {fact["path"] for fact in tone["facts"]} == {"guide.md", "old/voice-guide-2023-old.md"}
    assert tone["winner"] == "guide.md"
    assert tone["rule"] == "replaces"


def test_the_document_in_charge_wins_a_conflict(client: TestClient):
    certification = _conflict(_brand(client, _upload(client)), "certifications")

    assert certification["winner"] == "legal/certifications.md"
    assert certification["rule"] == "owner"
    assert certification["reason"] == (
        "legal/certifications.md is in charge of certifications; "
        "internal/sales-notes.md is internal, so not in charge of what is said in public."
    )


def test_the_summary_is_built_from_winning_quotable_facts(client: TestClient, fake_ai: FakeTransport):
    brand = _brand(client, _upload(client))

    assert brand["summary"].startswith("# Acme brand summary")
    call = client.get(f"/api/ai-calls/{brand['summary_call_id']}").json()
    assert call["model"] == "gpt-6.1-sol"
    source = call["request"]["input"][-1]["content"]
    assert "tone: short sentences" in source
    assert "certification: not certified" in source
    assert "playful" not in source  # lost a conflict, and its document was replaced
    assert "sales-notes" not in source  # internal, not for public copy


def test_picking_another_winner_applies_at_once_and_can_be_undone(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)
    target = _conflict(_brand(client, brand_id), "certifications")["target"]
    calls_before = len(fake_ai.requests)

    corrected = client.post(
        f"/api/brands/{brand_id}/corrections",
        json={"kind": "conflict_winner", "target": target, "value": "internal/sales-notes.md"},
    ).json()

    certification = _conflict(corrected, "certifications")
    assert (certification["winner"], certification["rule"]) == ("internal/sales-notes.md", "you")
    assert corrected["summary_stale"] is True
    assert len(fake_ai.requests) == calls_before  # no AI needed

    undone = client.delete(f"/api/brands/{brand_id}/corrections/{corrected['decisions'][0]['id']}").json()
    assert _conflict(undone, "certifications")["winner"] == "legal/certifications.md"
    assert undone["summary_stale"] is False


def test_reading_again_with_nothing_new_makes_no_ai_calls(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)
    calls_before = (len(fake_ai.requests), len(fake_ai.embed_requests))

    client.post(f"/api/brands/{brand_id}/read")

    assert (len(fake_ai.requests), len(fake_ai.embed_requests)) == calls_before
    assert _brand(client, brand_id)["status"] == "ready"


def test_a_new_document_can_replace_an_old_one_without_reading_it_again(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)
    cards_before = calls_for(fake_ai.requests, "document_card")

    response = client.post(
        f"/api/brands/{brand_id}/files",
        files=[("files", ("acme/guide-2026.md", NEW_GUIDE.encode()))],
    )

    assert response.status_code == 200, response.text
    assert calls_for(fake_ai.requests, "document_card") == cards_before + 1
    brand = _brand(client, brand_id)
    docs = _docs(brand)
    assert docs["guide.md"]["status"] == "replaced"
    assert docs["guide.md"]["replaced_by"] == "guide-2026.md"
    tone = _conflict(brand, "tone")
    assert (tone["winner"], tone["rule"]) == ("guide-2026.md", "replaces")


def test_a_correction_survives_an_update(client: TestClient):
    brand_id = _upload(client)
    client.post(
        f"/api/brands/{brand_id}/corrections",
        json={"kind": "document_status", "target": "old/voice-guide-2023-old.md", "value": "current"},
    )

    client.post(f"/api/brands/{brand_id}/files", files=[("files", ("acme/guide-2026.md", NEW_GUIDE.encode()))])

    old = _docs(_brand(client, brand_id))["old/voice-guide-2023-old.md"]
    assert (old["status"], old["status_reason"]) == ("current", "You set this on the Brand page.")


def test_correcting_a_documents_type(client: TestClient):
    brand_id = _upload(client)

    brand = client.post(
        f"/api/brands/{brand_id}/corrections",
        json={"kind": "document_kind", "target": "guide.md", "value": "example"},
    ).json()

    assert _docs(brand)["guide.md"]["doc_type"] == "example"


def test_an_edited_summary_is_kept_until_rebuilt(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)

    edited = client.put(f"/api/brands/{brand_id}/summary", json={"text": "My own summary."})
    assert edited.status_code == 200
    client.post(f"/api/brands/{brand_id}/files", files=[("files", ("acme/guide-2026.md", NEW_GUIDE.encode()))])
    assert _brand(client, brand_id)["summary"] == "My own summary."

    client.post(f"/api/brands/{brand_id}/summary/rebuild")
    brand = _brand(client, brand_id)
    assert brand["summary"].startswith("# Acme brand summary")
    assert brand["summary_edited"] is False


def test_an_impossible_correction_is_refused(client: TestClient):
    brand_id = _upload(client)

    response = client.post(
        f"/api/brands/{brand_id}/corrections",
        json={"kind": "document_status", "target": "guide.md", "value": "banana"},
    )

    assert response.status_code == 400
