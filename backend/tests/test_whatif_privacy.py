"""What-if simulator and privacy (export, delete)."""

from pathlib import Path

from sqlalchemy import func, select

from app.core.config import settings
from app.models import (
    Activity,
    Checkin,
    Insight,
    JobRun,
    Message,
    MLModel,
    Prediction,
    Recommendation,
    User,
)
from tests.conftest import TestSession, auth, register


def seeded(client, persona="founder"):
    tokens = register(client)
    r = client.post("/demo/seed", headers=auth(tokens), json={"persona": persona, "days": 60})
    assert r.status_code == 200 and r.json()["pipeline"] == "ok", r.text
    return tokens


# ---------- what-if ----------


def test_whatif_matches_tomorrow_and_moves_with_sliders(client):
    h = auth(seeded(client))
    base = client.get("/whatif", headers=h).json()
    tomorrow = {p["target"]: p for p in client.get("/predictions/tomorrow", headers=h).json()}
    for target, r in base["results"].items():
        # nothing changed = exactly the dashboard's prediction
        assert abs(r["value"] - tomorrow[target]["predicted"]) < 0.01, target
        assert r["delta"] == 0
    controls = base["controls"]
    assert controls and base["note"] is None
    learned = [t for t, r in base["results"].items() if r["learned"]]
    assert learned, "the founder has a learned model"
    for c in controls:
        assert c["min"] < c["max"] and c["min"] <= c["value"] <= c["max"]

    moved = False
    for c in controls:
        for v in (c["min"], c["max"]):
            r = client.post("/whatif", headers=h, json={"overrides": {c["key"]: v}}).json()
            assert r["applied"] == {c["key"]: v}
            for res in r["results"].values():
                if not res["learned"]:
                    assert res["delta"] == 0  # an average-based prediction can't move
                moved |= abs(res["delta"]) >= 0.05
            assert r["ms"] < 1000
    assert moved, "no slider changed the prediction"


def test_whatif_clips_to_history_and_ignores_unknown_inputs(client):
    h = auth(seeded(client))
    c = client.get("/whatif", headers=h).json()["controls"][0]
    r = client.post(
        "/whatif", headers=h, json={"overrides": {c["key"]: c["max"] + 1000, "next_magic": 3}}
    ).json()
    assert r["applied"] == {c["key"]: c["max"]} and r["clipped"] == [c["key"]]


def test_whatif_is_honest_when_nothing_can_change(client):
    h = auth(seeded(client, "noise"))
    r = client.get("/whatif", headers=h).json()
    assert r["controls"] == [] and "recent average" in r["note"]
    new = auth(register(client))
    r = client.get("/whatif", headers=new).json()
    assert r["controls"] == [] and r["results"] == {} and "few days" in r["note"]


# ---------- privacy ----------


def test_export_contains_everything_but_secrets(client):
    tokens = seeded(client)
    h = auth(tokens)
    r = client.get("/privacy/export", headers=h)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    for key in (
        "user",
        "profile",
        "checkins",
        "activities",
        "chat_messages",
        "insights",
        "predictions",
        "recommendations",
        "consents",
        "models",
        "pipeline_runs",
    ):
        assert key in data, key
    assert data["user"]["email"] == tokens["email"]
    assert "password_hash" not in data["user"]
    assert data["checkins"] and data["chat_messages"] and data["recommendations"]
    assert all("embedding" not in m for m in data["chat_messages"])
    assert all("path" not in m for m in data["models"])


def test_delete_me_removes_everything(client):
    tokens = seeded(client)
    h = auth(tokens)
    with TestSession() as db:
        uid = db.scalar(select(User.id).where(User.email == tokens["email"]))
    model_dir = Path(settings.model_store_dir) / str(uid)
    assert any(model_dir.glob("*.joblib"))

    assert (
        client.request("DELETE", "/me", headers=h, json={"confirm_email": "nope@x.y"}).status_code
        == 422
    )
    r = client.request("DELETE", "/me", headers=h, json={"confirm_email": tokens["email"].upper()})
    assert r.status_code == 204

    with TestSession() as db:
        assert db.get(User, uid) is None
        for model in (
            Checkin,
            Activity,
            Message,
            Insight,
            Prediction,
            Recommendation,
            JobRun,
            MLModel,
        ):
            n = db.scalar(select(func.count()).select_from(model).where(model.user_id == uid))
            assert n == 0, model.__name__
    assert not any(model_dir.glob("*.joblib"))
    assert client.get("/me", headers=h).status_code == 401  # the token is dead
