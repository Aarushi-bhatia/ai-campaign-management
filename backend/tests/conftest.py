"""Tests run the real app against a real Postgres test database, with a fake AI."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_url = make_url(os.environ.get("DATABASE_URL", "postgresql+psycopg://campaign:campaign@localhost:5432/campaign"))
TEST_DATABASE_URL = _url.set(database=f"{_url.database}_test").render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai.deps import get_ai_transport  # noqa: E402
from app.ai.fake import FakeTransport  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.jobs import InlineJobRunner, get_job_runner  # noqa: E402
from app.main import create_app  # noqa: E402
from app.research.client import FakeWebResearch  # noqa: E402
from app.research.deps import get_web_research  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _create_test_database() -> None:
    admin = create_engine(_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": f"{_url.database}_test"})
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{_url.database}_test"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _create_test_database()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = TEST_DATABASE_URL
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with engine.begin() as connection:
        names = ", ".join(Base.metadata.tables)
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def fake_ai() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def fake_web() -> FakeWebResearch:
    return FakeWebResearch()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL,
        data_dir=tmp_path,
        model_small="gpt-6-luna",
        model_medium="gpt-6.1-terra",
        model_large="gpt-6.1-sol",
        model_embedding="text-embedding-3-small",
        brand_dir=None,
        brand_exclude="",
    )


@pytest.fixture
def client(fake_ai: FakeTransport, fake_web: FakeWebResearch, settings: Settings) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_ai_transport] = lambda: fake_ai
    app.dependency_overrides[get_web_research] = lambda: fake_web
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_job_runner] = InlineJobRunner
    with TestClient(app) as test_client:
        yield test_client
