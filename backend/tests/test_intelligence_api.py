"""Phase 3 API: dashboard, insights, predictions, confirm, retrain."""

from datetime import date, timedelta

from sqlalchemy import select

from app.api import intelligence
from app.ml.pipeline import run_user
from app.models import User
from tests.conftest import TestSession, auth, register

TODAY = date.today()


def seeded(client, persona="founder"):
    tokens = register(client)
    r = client.post("/demo/seed", headers=auth(tokens), json={"persona": persona, "days": 60})
    assert r.status_code == 200 and r.json()["pipeline"] == "ok", r.text
    return tokens


def test_dashboard_and_insights(client):
    h = auth(seeded(client))
    d = client.get("/dashboard", headers=h).json()
    assert d["data_days"] >= 50 and d["learning"]["phase"] == "predicting"
    assert d["accuracy"]["n"] > 0 and d["accuracy"]["backtest_share"] == 1.0
    assert {p["target"] for p in d["tomorrow"]} >= {"mood", "energy"}
    assert d["insights"] and all(i["type"] == "pattern" for i in d["insights"])
    assert all(i["is_new"] for i in d["insights"])  # first seen today
    assert 20 <= len(d["series"]) <= 30 and d["minutes_by_category"]  # check-in days only
    assert d["traits"]["chronotype"]["source"] == "data"
    assert d["last_run"]["status"] == "ok"

    ins = client.get("/insights", headers=h).json()
    assert {"r", "p_adj", "n", "lag", "worse_mean", "other_mean"} <= set(ins[-1]["evidence"])

    other = auth(register(client))
    assert client.get("/insights", headers=other).json() == []
    assert client.get("/predictions/tomorrow", headers=other).json() == []
    empty = client.get("/dashboard", headers=other).json()
    assert empty["data_days"] == 0 and empty["learning"]["phase"] == "learning"


def test_tomorrow_explanations(client):
    h = auth(seeded(client))
    preds = client.get("/predictions/tomorrow", headers=h).json()
    for p in preds:
        ex = p["explanation"]
        assert ex["model"] == p["model_kind"]
        assert ex.get("contributors") is not None
        if p["target"] == "task":
            assert p["task_title"] and 0 <= p["predicted"] <= 1
        elif ex["contributors"]:
            assert ex["start_from"] is not None
            assert all(abs(c["impact"]) >= 0.05 for c in ex["contributors"])


def test_pending_confirm_and_accuracy(client):
    tokens = seeded(client, "developer")
    h = auth(tokens)
    with TestSession() as db:
        uid = db.scalar(select(User.id).where(User.email == tokens["email"]))
    # pretend the pipeline ran yesterday evening: predictions for *today* become pending
    run_user(TestSession, uid, trigger="retrain", today=TODAY - timedelta(days=1))
    pending = client.get("/predictions/pending", headers=h).json()
    reg = [p for p in pending if p["target"] in ("mood", "energy")]
    assert reg and all(p["for_date"] == TODAY.isoformat() for p in reg)

    p = reg[0]
    assert (
        client.post(f"/predictions/{p['id']}/confirm", headers=h, json={"actual": 3.5}).status_code
        == 422
    )  # whole numbers only
    assert (
        client.post(f"/predictions/{p['id']}/confirm", headers=h, json={"actual": 9}).status_code
        == 422
    )
    r = client.post(f"/predictions/{p['id']}/confirm", headers=h, json={"actual": 4})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["prediction"]["actual"] == 4 and out["prediction"]["confirmed_at"]
    assert out["accuracy"]["n"] >= 1
    assert p["id"] not in {x["id"] for x in client.get("/predictions/pending", headers=h).json()}

    task = next((x for x in pending if x["target"] == "task"), None)
    if task:
        assert (
            client.post(
                f"/predictions/{task['id']}/confirm", headers=h, json={"actual": 2}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/predictions/{task['id']}/confirm", headers=h, json={"actual": 1}
            ).status_code
            == 200
        )

    tomorrow = client.get("/predictions/tomorrow", headers=h).json()[0]
    assert (
        client.post(
            f"/predictions/{tomorrow['id']}/confirm", headers=h, json={"actual": 3}
        ).status_code
        == 422
    )  # day hasn't happened
    other = auth(register(client))
    assert (
        client.post(
            f"/predictions/{p['id']}/confirm", headers=other, json={"actual": 3}
        ).status_code
        == 404
    )


def test_retrain_endpoint_and_rate_limit(client, monkeypatch):
    intelligence.retrain_limiter.reset()
    h = auth(seeded(client, "noise"))
    r = client.post("/jobs/retrain", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["trigger"] == "retrain"
    assert client.get("/jobs/last", headers=h).json()["id"] == r.json()["id"]
    client.post("/jobs/retrain", headers=h)
    r = client.post("/jobs/retrain", headers=h)
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert client.post("/jobs/retrain").status_code == 401
