"""The image library through the API: image info, descriptions, restrictions, channel rules and picking."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.ai.fake import FakeTransport
from tests import brand_brain
from tests.brand_brain import calls_for


def _png(width: int, height: int, transparent: bool = False) -> bytes:
    image = Image.new("RGBA", (width, height), (200, 100, 50, 0 if transparent else 255))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _jpg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


RECORDS = [
    {"filename": "hero-team.jpg", "title": "Team at work", "description": "Three people planning a release at a long desk.", "type": "photography",
     "tags": ["team"], "restrictions": ""},
    {"filename": "spot-lamp.png", "title": "Lamp", "description": "", "type": "illustration", "restrictions": ""},
    {"filename": "logo-shield.png", "title": "Shield logo", "description": "The old shield logo on a white ground.", "type": "logo",
     "restrictions": "Deprecated"},
    {"filename": "event-card.png", "title": "Summit card", "description": "A social card with the summit date on it.", "type": "social_template",
     "restrictions": "Summit 2026 only. The event has passed."},
    {"filename": "team-tomas.jpg", "title": "Tomas", "description": "Tomas sketching a diagram at the whiteboard.",
     "type": "photography", "restrictions": "Tomas left the company in June."},
    {"filename": "concept-hacker.jpg", "title": "Hacker", "description": "A hooded hacker at a keyboard in the dark.",
     "type": "photography", "restrictions": ""},
    {"filename": "office-desk.jpg", "title": "Desk", "description": "A desk.", "type": "photography", "restrictions": ""},
]

FILES = {
    "acme/visuals/email-images.md": (
        "# Email images\n\nDo not use transparent images in email headers.\n\n"
        "## Clichés\n\nNever show hooded hackers in any image.\n"
    ),
    "acme/images/metadata.json": json.dumps(RECORDS).encode(),
    "acme/images/hero-team.jpg": _jpg(300, 200),
    "acme/images/spot-lamp.png": _png(100, 100, transparent=True),
    "acme/images/logo-shield.png": _png(100, 100),
    "acme/images/event-card.png": _png(120, 63),
    "acme/images/team-tomas.jpg": _jpg(300, 200),
    "acme/images/concept-hacker.jpg": _jpg(300, 200),
    "acme/images/office-desk.jpg": _jpg(300, 200),
    "acme/images/chart-growth.png": _png(160, 90),
}


@pytest.fixture(autouse=True)
def brain(fake_ai: FakeTransport) -> None:
    fake_ai._default = brand_brain.reply


def _upload(client: TestClient) -> int:
    response = client.post(
        "/api/brands",
        data={"name": "Acme"},
        files=[("files", (path, content if isinstance(content, bytes) else content.encode())) for path, content in FILES.items()],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _images(client: TestClient, brand_id: int) -> dict[str, dict]:
    return {image["path"]: image for image in client.get(f"/api/brands/{brand_id}").json()["images"]}


def test_the_image_info_file_is_matched_to_the_images(client: TestClient):
    images = _images(client, _upload(client))

    hero = images["images/hero-team.jpg"]
    assert (hero["title"], hero["description"], hero["description_source"]) == (
        "Team at work", "Three people planning a release at a long desk.", "file",
    )
    assert (hero["image_type"], hero["tags"], hero["width"], hero["height"]) == ("photography", ["team"], 300, 200)
    assert hero["record"]["filename"] == "hero-team.jpg"


def test_see_through_pixels_are_detected(client: TestClient):
    images = _images(client, _upload(client))

    assert images["images/spot-lamp.png"]["transparent"] is True
    assert images["images/logo-shield.png"]["transparent"] is False


def test_images_without_a_description_are_described_by_the_vision_model(client: TestClient, fake_ai: FakeTransport):
    images = _images(client, _upload(client))

    assert images["images/spot-lamp.png"]["description_source"] == "ai"
    assert images["images/chart-growth.png"]["description"] == "A described picture."
    assert images["images/chart-growth.png"]["image_type"] == "chart"  # no info row, so the model's type is used
    assert calls_for(fake_ai.requests, "image_description") == 3  # two with no description, one too short
    call = client.get(f"/api/ai-calls/{images['images/spot-lamp.png']['describe_call_id']}").json()
    assert call["model"] == "gpt-6-luna"
    assert call["request"]["input"][-1]["content"][1]["image_url"] == "<image: images/spot-lamp.png>"


def test_restrictions_become_reasons(client: TestClient):
    images = _images(client, _upload(client))

    assert images["images/logo-shield.png"]["blocked"] == "Retired logo."
    assert images["images/event-card.png"]["blocked"] == "The event has passed."
    assert images["images/team-tomas.jpg"]["blocked"] == "The person left."
    assert images["images/hero-team.jpg"]["blocked"] is None


def test_channel_rules_come_from_the_brands_documents(client: TestClient):
    brand_id = _upload(client)
    brand = client.get(f"/api/brands/{brand_id}").json()

    assert brand["image_rules"]["channels"]["email"]["block_transparent"] is True
    spot = _images(client, brand_id)["images/spot-lamp.png"]
    assert spot["channels"]["email"] == "See-through images aren't used in email."
    assert spot["channels"]["blog"] is None


def test_picking_ranks_only_cleared_images(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)

    response = client.post(
        f"/api/brands/{brand_id}/images/pick",
        json={"channel": "email", "asset_type": "launch email", "message": "Our team shipped the release."},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["choices"][0]["path"] in ("images/hero-team.jpg", "images/chart-growth.png")
    assert result["choices"][0]["alt_text"] == "A photo of the team."
    blocked = {b["path"]: b["reason"] for b in result["blocked"]}
    assert blocked["images/spot-lamp.png"] == "See-through images aren't used in email."
    assert blocked["images/logo-shield.png"] == "Retired logo."
    listed = fake_ai.requests[-1].prompt.campaign
    assert "spot-lamp" not in listed and "Shield logo" not in listed and "Tomas" not in listed


def test_nothing_fits_when_every_image_is_blocked(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)
    calls_before = len(fake_ai.requests)

    result = client.post(
        f"/api/brands/{brand_id}/images/pick",
        json={"channel": "email", "asset_type": "email", "message": "x",
              "exclude": ["images/hero-team.jpg", "images/chart-growth.png", "images/office-desk.jpg"]},
    ).json()

    assert result["choices"] == []
    assert result["suggestion"]
    assert len(fake_ai.requests) == calls_before  # nothing to rank, so no AI call


def test_marking_an_image_usable_overrides_its_restrictions_and_survives_an_update(client: TestClient):
    brand_id = _upload(client)
    client.post(
        f"/api/brands/{brand_id}/corrections",
        json={"kind": "image_usable", "target": "images/team-tomas.jpg", "value": "yes"},
    )

    client.post(f"/api/brands/{brand_id}/files", files=[("files", ("acme/images/new.png", _png(50, 50)))])

    assert _images(client, brand_id)["images/team-tomas.jpg"]["blocked"] is None


def test_reading_again_makes_no_image_calls(client: TestClient, fake_ai: FakeTransport):
    brand_id = _upload(client)
    calls_before = len(fake_ai.requests)

    client.post(f"/api/brands/{brand_id}/read")

    assert len(fake_ai.requests) == calls_before


def test_images_are_served(client: TestClient):
    brand_id = _upload(client)

    response = client.get(f"/api/brands/{brand_id}/files/images/hero-team.jpg")

    assert response.status_code == 200
    assert response.content == FILES["acme/images/hero-team.jpg"]
    assert client.get(f"/api/brands/{brand_id}/files/visuals/email-images.md").status_code == 404


def test_an_uploaded_svg_cannot_run_scripts_when_opened(client: TestClient):
    brand_id = _upload(client)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.cookie)</script><circle r="5"/></svg>'
    client.post(f"/api/brands/{brand_id}/files", files=[("files", ("acme/images/badge.svg", svg))])

    response = client.get(f"/api/brands/{brand_id}/files/images/badge.svg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["x-content-type-options"] == "nosniff"
    policy = {part.split()[0]: part.split()[1:] for part in response.headers["content-security-policy"].split("; ")}
    assert policy["default-src"] == ["'none'"]  # no scripts, frames or requests of any kind
    assert "script-src" not in policy
    assert "sandbox" in policy
    # Ordinary images get the same headers and are served unchanged, so previews keep working.
    photo = client.get(f"/api/brands/{brand_id}/files/images/hero-team.jpg")
    assert photo.content == FILES["acme/images/hero-team.jpg"]
    assert photo.headers["x-content-type-options"] == "nosniff"


def test_a_broken_image_file_does_not_stop_the_read(client: TestClient):
    response = client.post(
        "/api/brands",
        data={"name": "Acme"},
        files=[("files", ("acme/guide.md", b"# Guide")), ("files", ("acme/broken.png", b"not an image"))],
    )
    brand = client.get(f"/api/brands/{response.json()['id']}").json()

    assert brand["status"] == "ready"
    broken = brand["images"][0]
    assert (broken["width"], broken["description_source"]) == (0, "name")


def test_an_image_limited_to_some_channels_is_not_blocked_overall(client: TestClient, fake_ai: FakeTransport):
    def only_linkedin(request):
        reply = json.loads(brand_brain.reply(request))
        if request.output_schema and request.output_schema.name == "image_notes":
            for image in reply["images"]:
                image["allowed_channels"] = ["linkedin"]
        return json.dumps(reply)

    fake_ai._default = only_linkedin
    hero = _images(client, _upload(client))["images/hero-team.jpg"]

    assert hero["blocked"] is None
    assert hero["channels"]["email"] == "Only for linkedin."
    assert hero["channels"]["linkedin"] is None


def test_a_too_short_description_is_backed_by_the_vision_model(client: TestClient, fake_ai: FakeTransport):
    desk = _images(client, _upload(client))["images/office-desk.jpg"]

    assert (desk["description"], desk["description_source"]) == ("A described picture.", "ai")
    call = client.get(f"/api/ai-calls/{desk['describe_call_id']}").json()
    assert "Library note: A desk." in call["request"]["input"][-1]["content"][0]["text"]


def test_an_image_that_breaks_a_brand_image_rule_is_blocked(client: TestClient):
    hacker = _images(client, _upload(client))["images/concept-hacker.jpg"]

    assert hacker["blocked"] == "Banned motif: hooded hackers."


def test_an_image_whose_changed_restrictions_could_not_be_read_is_blocked(client: TestClient, fake_ai: FakeTransport):
    """The reviewer's probe: the image's record now said "Deprecated", the notes call failed, and the old
    "usable" notes stayed, with the brand shown as ready."""
    brand_id = _upload(client)
    assert not _images(client, brand_id)["images/hero-team.jpg"]["blocked"]

    def notes_fail(request):
        if request.output_schema and request.output_schema.name == "image_notes":
            raise RuntimeError("The AI service is down")
        return brand_brain.reply(request)

    fake_ai._default = notes_fail
    records = [{**r, "restrictions": "Deprecated. Retired image, do not use."} if r["filename"] == "hero-team.jpg" else r
               for r in RECORDS]
    client.post(f"/api/brands/{brand_id}/files", files=[("files", ("acme/images/metadata.json", json.dumps(records).encode()))])

    brand = client.get(f"/api/brands/{brand_id}").json()
    hero = _images(client, brand_id)["images/hero-team.jpg"]
    assert brand["status"] == "ready"
    assert hero["notes"] is None and "couldn't be" in hero["blocked"]  # was still usable
    assert _images(client, brand_id)["images/office-desk.jpg"]["notes"] is not None  # unchanged images keep theirs



def test_a_pick_tried_on_the_brand_page_is_not_reading_cost(client: TestClient):
    """It has no chat, so it was counted as reading the brand."""
    from app.ai.models import AiCall
    from app.brand.images.library import BRAND_PAGE_PICK
    from app.db import SessionLocal
    brand_id = _upload(client)
    before = client.get(f"/api/brands/{brand_id}").json()["reading_cost"]

    result = client.post(f"/api/brands/{brand_id}/images/pick",
                         json={"channel": "email", "asset_type": "launch email", "message": "Our team shipped."}).json()
    with SessionLocal() as session:  # the fake AI's calls cost nothing; give the pick a price
        call = session.get(AiCall, result["call_id"])
        assert call.step == BRAND_PAGE_PICK
        call.cost_usd = 1.0
        session.commit()

    assert client.get(f"/api/brands/{brand_id}").json()["reading_cost"] == before
