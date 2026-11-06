"""The seed script: one brand already read, exported, and loaded into an empty install."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.ai.fake import FakeTransport
from app.ai.models import AiCall
from app.brand.files import storage_path
from app.brand.models import Brand, BrandFile, Conflict, Fact, ImageInfo, Section
from app.config import Settings
from app.db import Base, SessionLocal, engine
from scripts import seed
from tests import brand_brain
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def brain(fake_ai: FakeTransport) -> None:
    fake_ai._default = brand_brain.reply


def _read_brand(client: TestClient) -> int:
    response = client.post("/api/brands", data={"name": "Acme"},
                           files=[("files", (p, c.encode())) for p, c in brand_brain.BRAND.items()])
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _counts() -> dict[str, int]:
    with SessionLocal() as session:
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (Brand, BrandFile, Section, Fact, Conflict)}


def _calls_behind_the_data() -> set[int]:
    """The AI calls the brand's rows point at: the ones a seed keeps."""
    with SessionLocal() as session:
        columns = (Brand.summary_call_id, Brand.image_rules_call_id, Brand.writing_rules_call_id,
                   BrandFile.card_call_id, BrandFile.facts_call_id, Conflict.call_id,
                   ImageInfo.describe_call_id, ImageInfo.notes_call_id)
        return {i for column in columns for i in session.scalars(select(column)) if i is not None}


def _empty_database() -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(Base.metadata.tables)} RESTART IDENTITY CASCADE"))


def test_a_brand_comes_back_from_its_seed_exactly_as_it_was_read(client: TestClient, settings: Settings,
                                                                  tmp_path: Path):
    brand_id = _read_brand(client)
    chat_id = client.post("/api/chats").json()["id"]  # a chat is never part of a seed
    before = client.get(f"/api/brands/{brand_id}").json()
    counts, calls = _counts(), _calls_behind_the_data()
    out = tmp_path / "seed.tar.gz"

    seed.export(TEST_DATABASE_URL, settings.data_dir, brand_id, out)
    _empty_database()
    fresh = tmp_path / "fresh-install"
    loaded = seed.load(TEST_DATABASE_URL, fresh, out)

    assert loaded == brand_id
    assert _counts() == counts
    with SessionLocal() as session:  # only the calls behind the data: earlier reads would overstate the cost
        assert set(session.scalars(select(AiCall.id))) == calls
    with SessionLocal() as session:
        brand = session.get(Brand, brand_id)
        assert (brand.status, brand.summary, brand.reviewed) == ("ready", before["summary"], False)
        assert all(storage_path(fresh, brand_id, f.path).is_file() for f in brand.files)
        assert session.scalar(select(func.count()).select_from(AiCall).where(AiCall.chat_id == chat_id)) == 0
        # New rows get new ids after the loaded ones.
        session.add(Brand(name="Next"))
        session.commit()
        assert session.scalar(select(func.max(Brand.id))) == brand_id + 1


def test_a_seed_never_loads_over_an_existing_brand(client: TestClient, settings: Settings, tmp_path: Path):
    brand_id = _read_brand(client)
    out = tmp_path / "seed.tar.gz"
    seed.export(TEST_DATABASE_URL, settings.data_dir, brand_id, out)

    with pytest.raises(seed.SeedError, match="brand already"):
        seed.load(TEST_DATABASE_URL, tmp_path / "other", out)


def test_the_script_loads_into_an_empty_app_and_leaves_one_with_a_brand(client: TestClient, settings: Settings,
                                                                          tmp_path: Path, monkeypatch, capsys):
    out = tmp_path / "seed.tar.gz"
    seed.export(TEST_DATABASE_URL, settings.data_dir, _read_brand(client), out)
    _empty_database()
    monkeypatch.setattr(seed, "get_settings", lambda: settings.model_copy(update={"data_dir": tmp_path / "fresh"}))

    first, second = seed.main(["load", str(out)]), seed.main(["load", str(out)])

    assert (first, second) == (0, 0)  # a second run is not an error, so the app still starts
    assert "Seed not loaded: the app has a brand already." in capsys.readouterr().out
    assert _counts()["brands"] == 1
