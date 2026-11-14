"""Tests run against a real Postgres (twin_test DB) migrated with Alembic,
so the migrations themselves are tested too."""

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

# Tests never call OpenAI or download models: deterministic fakes for both.
# Set before importing the app so Settings picks them up (env beats .env).
os.environ["LLM_PROVIDER"] = "fake"
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["DEMO_ENABLED"] = "true"
os.environ["SCHEDULER_ENABLED"] = "false"  # no background nightly job during tests
os.environ["DEMO_BACKTEST_DAYS"] = "3"  # keep /demo/seed fast in tests
os.environ["MODEL_STORE_DIR"] = tempfile.mkdtemp(prefix="twin-models-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.api.chat import limiter  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import get_db, get_session_factory  # noqa: E402
from app.main import app  # noqa: E402

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
    limiter.reset()
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
    app.dependency_overrides[get_session_factory] = lambda: TestSession
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
