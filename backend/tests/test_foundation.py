"""Hardening tests for the Phase 1 foundation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from pydantic import ValidationError

from alembic import command
from app.core.config import Settings
from tests.conftest import alembic_config, auth, register

TODAY = date.today().isoformat()


def test_models_and_migrations_are_in_sync():
    """Fails if someone changes a model without writing an Alembic migration."""
    command.check(alembic_config())


def test_health_checks_database(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_cors_preflight_allows_frontend_only(client):
    ok = client.options(
        "/auth/login",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options(
        "/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_openapi_docs_available(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for p in [
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/me",
        "/onboarding",
        "/checkins",
        "/activities",
        "/activities/{activity_id}",
        "/privacy/consents",
    ]:
        assert p in paths


# ---------- config ----------


def test_production_rejects_weak_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="change-me")
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="short")
    Settings(app_env="production", jwt_secret="x" * 40)  # ok


# ---------- auth edge cases ----------


def test_password_byte_limit(client):
    # 30 emoji = 30 chars but 120 bytes; bcrypt would silently truncate it
    r = client.post(
        "/auth/register", json={"email": "e@example.com", "password": "😀" * 30, "name": "E"}
    )
    assert r.status_code == 422


def test_blank_name_and_password_rejected(client):
    r = client.post(
        "/auth/register", json={"email": "n@example.com", "password": "password123", "name": "   "}
    )
    assert r.status_code == 422
    r = client.post(
        "/auth/register", json={"email": "n@example.com", "password": " " * 10, "name": "N"}
    )
    assert r.status_code == 422


def test_unknown_email_and_wrong_password_look_the_same(client):
    register(client, email="known@example.com")
    a = client.post("/auth/login", json={"email": "known@example.com", "password": "wrongpass"})
    b = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrongpass"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_concurrent_duplicate_registration_gives_409_not_500(client):
    body = {"email": "race@example.com", "password": "password123", "name": "R"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(
            pool.map(lambda _: client.post("/auth/register", json=body).status_code, range(4))
        )
    assert codes.count(201) == 1
    assert set(codes) <= {201, 409}


def test_token_for_deleted_user_is_rejected(client):
    from sqlalchemy import text

    from tests.conftest import engine

    tokens = register(client, email="gone@example.com")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = 'gone@example.com'"))
    assert client.get("/me", headers=auth(tokens)).status_code == 401
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_tampered_token_rejected(client):
    tokens = register(client)
    t = tokens["access_token"]
    tampered = t[:-4] + ("AAAA" if not t.endswith("AAAA") else "BBBB")
    assert client.get("/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


# ---------- data edge cases ----------


def test_patch_activity_rejects_null_completed_and_empty_body(client, user):
    h = auth(user)
    act = client.post(
        "/activities",
        headers=h,
        json={"date": TODAY, "category": "Study", "title": "Read", "planned": True},
    ).json()
    assert (
        client.patch(f"/activities/{act['id']}", json={"completed": None}, headers=h).status_code
        == 422
    )
    assert client.patch(f"/activities/{act['id']}", json={}, headers=h).status_code == 422
    # duration_min may be cleared explicitly
    r = client.patch(f"/activities/{act['id']}", json={"duration_min": None}, headers=h)
    assert r.status_code == 200


def test_bad_ids_and_ranges(client, user):
    h = auth(user)
    assert (
        client.patch("/activities/not-a-uuid", json={"completed": True}, headers=h).status_code
        == 422
    )
    assert (
        client.delete("/activities/00000000-0000-0000-0000-000000000000", headers=h).status_code
        == 404
    )
    assert client.get("/checkins?from=2026-02-01&to=2026-01-01", headers=h).status_code == 422
    assert client.get("/activities?from=2026-02-01&to=2026-01-01", headers=h).status_code == 422


def test_blank_activity_title_rejected(client, user):
    r = client.post(
        "/activities", headers=auth(user), json={"date": TODAY, "category": "Study", "title": "   "}
    )
    assert r.status_code == 422


def test_onboarding_can_be_redone(client, user):
    from tests.conftest import ONBOARDING

    h = auth(user)
    r = client.post("/onboarding", headers=h, json=ONBOARDING | {"categories": ["Work"]})
    assert r.status_code == 200
    assert r.json()["categories"] == ["Work"]
    # duplicate categories (case-insensitive) are merged
    r = client.post(
        "/onboarding", headers=h, json=ONBOARDING | {"categories": ["Work", "work", " Gym "]}
    )
    assert r.json()["categories"] == ["Work", "Gym"]


def test_deleting_user_cascades_all_rows(client, user):
    from sqlalchemy import text

    from tests.conftest import engine

    h = auth(user)
    client.post(
        "/checkins",
        headers=h,
        json={"date": TODAY, "mood": 3, "energy": 3, "stress": 3, "focus": 3},
    )
    client.post("/activities", headers=h, json={"date": TODAY, "category": "Study", "title": "X"})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users"))
        for table in ["twin_profiles", "consents", "checkins", "activities"]:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0
