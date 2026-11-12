from datetime import date, timedelta

from tests.conftest import ONBOARDING, auth, register

TODAY = date.today().isoformat()


def checkin(**overrides) -> dict:
    return {
        "date": TODAY,
        "mood": 3,
        "energy": 4,
        "stress": 2,
        "focus": 3,
        "sleep_hours": 7.5,
        "note": "ok day",
    } | overrides


# ---------- onboarding ----------


def test_onboarding_sets_profile_and_trait_prior(client):
    tokens = register(client)
    r = client.post("/onboarding", json=ONBOARDING, headers=auth(tokens))
    assert r.status_code == 200
    profile = r.json()
    assert profile["categories"] == ["Study", "Exercise", "Social"]
    assert profile["traits"]["chronotype"]["value"] == "night owl"
    assert profile["traits"]["chronotype"]["source"] == "quiz"
    assert profile["traits"]["optimism_bias"]["value"] == 0.6

    me = client.get("/me", headers=auth(tokens)).json()
    assert me["onboarded"] is True
    assert me["user"]["role"] == "Student"


def test_onboarding_validation(client):
    tokens = register(client)
    bad = ONBOARDING | {"categories": []}
    assert client.post("/onboarding", json=bad, headers=auth(tokens)).status_code == 422
    bad_quiz = ONBOARDING | {"quiz": ONBOARDING["quiz"] | {"plans_ahead": 9}}
    assert client.post("/onboarding", json=bad_quiz, headers=auth(tokens)).status_code == 422


# ---------- check-ins ----------


def test_checkin_create_and_overwrite(client, user):
    h = auth(user)
    first = client.post("/checkins", json=checkin(), headers=h)
    assert first.status_code == 200, first.text
    second = client.post("/checkins", json=checkin(mood=5, note="better"), headers=h)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]  # same row, overwritten

    rows = client.get("/checkins", headers=h).json()
    assert len(rows) == 1
    assert rows[0]["mood"] == 5 and rows[0]["note"] == "better"


def test_checkin_range_and_validation(client, user):
    h = auth(user)
    for d in range(3):
        day = (date.today() - timedelta(days=d)).isoformat()
        assert client.post("/checkins", json=checkin(date=day), headers=h).status_code == 200
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    rows = client.get(f"/checkins?from={yesterday}", headers=h).json()
    assert len(rows) == 2

    assert client.post("/checkins", json=checkin(mood=6), headers=h).status_code == 422
    assert client.post("/checkins", json=checkin(sleep_hours=25), headers=h).status_code == 422
    future = (date.today() + timedelta(days=5)).isoformat()
    assert client.post("/checkins", json=checkin(date=future), headers=h).status_code == 422


# ---------- activities ----------


def activity(**overrides) -> dict:
    return {
        "date": TODAY,
        "category": "study",
        "title": "DBMS revision",
        "planned": True,
        "planned_min": 60,
    } | overrides


def test_activity_crud(client, user):
    h = auth(user)
    r = client.post("/activities", json=activity(), headers=h)
    assert r.status_code == 201, r.text
    act = r.json()
    assert act["category"] == "Study"  # canonical spelling from profile
    assert act["completed"] is False

    r = client.patch(
        f"/activities/{act['id']}", json={"completed": True, "duration_min": 95}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["completed"] is True and r.json()["duration_min"] == 95

    rows = client.get(f"/activities?from={TODAY}&to={TODAY}", headers=h).json()
    assert len(rows) == 1

    assert client.delete(f"/activities/{act['id']}", headers=h).status_code == 204
    assert client.get("/activities", headers=h).json() == []


def test_activity_unknown_category(client, user):
    r = client.post("/activities", json=activity(category="Gaming"), headers=auth(user))
    assert r.status_code == 422


# ---------- consents ----------


def test_toggle_consent(client, user):
    h = auth(user)
    r = client.put("/privacy/consents", json={"source": "chat", "allowed": False}, headers=h)
    assert r.status_code == 200
    by_source = {c["source"]: c["allowed"] for c in r.json()}
    assert by_source["chat"] is False and by_source["checkin"] is True
    bad = client.put("/privacy/consents", json={"source": "email", "allowed": False}, headers=h)
    assert bad.status_code == 422


# ---------- isolation: the Phase 1 gate ----------


def test_user_a_cannot_see_or_touch_user_b_data(client):
    a, b = register(client), register(client)
    client.post("/onboarding", json=ONBOARDING, headers=auth(a))
    client.post("/onboarding", json=ONBOARDING, headers=auth(b))

    client.post("/checkins", json=checkin(mood=1), headers=auth(a))
    act_a = client.post("/activities", json=activity(), headers=auth(a)).json()

    # B sees nothing of A's
    assert client.get("/checkins", headers=auth(b)).json() == []
    assert client.get("/activities", headers=auth(b)).json() == []

    # B cannot modify or delete A's activity (404, not 403: no existence leak)
    assert (
        client.patch(
            f"/activities/{act_a['id']}", json={"completed": True}, headers=auth(b)
        ).status_code
        == 404
    )
    assert client.delete(f"/activities/{act_a['id']}", headers=auth(b)).status_code == 404

    # A smuggling a user_id in the body is ignored
    client.post("/checkins", json=checkin(mood=5) | {"user_id": "someone-else"}, headers=auth(b))
    assert client.get("/checkins", headers=auth(a)).json()[0]["mood"] == 1

    # A's data is intact
    assert client.get("/activities", headers=auth(a)).json()[0]["completed"] is False
