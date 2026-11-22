from tests.conftest import auth, register


def test_register_login_me(client):
    tokens = register(client, email="Alice@Example.com")
    assert tokens["access_token"] and tokens["refresh_token"]

    r = client.post("/auth/login", json={"email": "alice@example.com", "password": "password123"})
    assert r.status_code == 200

    me = client.get("/me", headers=auth(r.json())).json()
    assert me["user"]["email"] == "alice@example.com"
    assert me["onboarded"] is False
    assert me["profile"]["data_days"] == 0


def test_register_duplicate_email(client):
    register(client, email="dup@example.com")
    r = client.post(
        "/auth/register",
        json={"email": "DUP@example.com", "password": "password123", "name": "X"},
    )
    assert r.status_code == 409


def test_wrong_password(client):
    register(client, email="bob@example.com")
    r = client.post("/auth/login", json={"email": "bob@example.com", "password": "nope-nope"})
    assert r.status_code == 401


def test_short_password_rejected(client):
    r = client.post(
        "/auth/register", json={"email": "c@example.com", "password": "123", "name": "C"}
    )
    assert r.status_code == 422


def test_protected_route_needs_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_token(client):
    tokens = register(client)
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert client.get("/me", headers=auth(r.json())).status_code == 200


def test_refresh_token_cannot_be_used_as_access(client):
    tokens = register(client)
    r = client.get("/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401
    # and an access token cannot be used to refresh
    r = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


def test_register_creates_default_consents(client):
    tokens = register(client)
    consents = client.get("/privacy/consents", headers=auth(tokens)).json()
    assert {c["source"] for c in consents} == {"chat", "checkin", "activities", "decisions"}
    assert all(c["allowed"] for c in consents)


def test_login_is_rate_limited_per_account(client):
    from app.core.config import settings

    register(client, email="guess@example.com")
    bad = {"email": "guess@example.com", "password": "wrong-password"}
    codes = [
        client.post("/auth/login", json=bad).status_code
        for _ in range(settings.login_rate_limit_per_min)
    ]
    assert set(codes) == {401}
    r = client.post("/auth/login", json={**bad, "email": "GUESS@example.com"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    # even the right password waits: the limit protects the account, not the attempt
    ok = client.post("/auth/login", json={**bad, "password": "password123"})
    assert ok.status_code == 429
    # other accounts are unaffected
    register(client, email="other@example.com")
    r = client.post("/auth/login", json={"email": "other@example.com", "password": "password123"})
    assert r.status_code == 200


def test_register_is_rate_limited_per_ip(client, monkeypatch):
    from app.api import auth as auth_api

    monkeypatch.setattr(auth_api.register_per_ip, "limit", 2)
    register(client, email="r1@example.com")
    register(client, email="r2@example.com")
    r = client.post(
        "/auth/register", json={"email": "r3@example.com", "password": "password123", "name": "X"}
    )
    assert r.status_code == 429 and "Retry-After" in r.headers
