"""Tests run against a real Postgres (twin_test DB) migrated with Alembic,
so the migrations themselves are tested too."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.db import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_URL = settings.test_database_url

engine = create_engine(TEST_URL, pool_pre_ping=True)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> Iterator[None]:
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    cfg = alembic_config()
    # Full down + up proves both directions of every migration work.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    os.environ.pop("ALEMBIC_DATABASE_URL", None)


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client: TestClient, email: str | None = None, password: str = "password123") -> dict:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": password, "name": "Test"})
    assert r.status_code == 201, r.text
    tokens = r.json()
    return {"email": email, "password": password, **tokens}


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


ONBOARDING = {
    "role": "Student",
    "goals": ["Sleep 7h", "Study 3h a day"],
    "categories": ["Study", "Exercise", "Social"],
    "quiz": {
        "best_time": "night",
        "plans_ahead": 2,
        "estimate_bias": "much_slower",
        "routine": 2,
        "stress_source": "deadlines",
    },
}


@pytest.fixture
def user(client) -> dict:
    tokens = register(client)
    r = client.post("/onboarding", json=ONBOARDING, headers=auth(tokens))
    assert r.status_code == 200, r.text
    return tokens
