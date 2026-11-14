"""The nightly pipeline against the real (test) database."""

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.ml.pipeline import Busy, lock_key, run_all, run_user
from app.models import Insight, JobRun, MLModel, Prediction, TwinProfile, User
from tests.conftest import TestSession, auth, engine, register

TODAY = date.today()


def seeded(client, persona="founder", days=60) -> tuple[dict, uuid.UUID]:
    tokens = register(client)
    r = client.post("/demo/seed", headers=auth(tokens), json={"persona": persona, "days": days})
    assert r.status_code == 200, r.text
    assert r.json()["pipeline"] == "ok", r.json()
    with TestSession() as db:
        uid = db.scalar(select(User.id).where(User.email == tokens["email"]))
    return tokens, uid


def counts(uid):
    with TestSession() as db:

        def n(model, *where):
            return db.scalar(
                select(func.count()).select_from(model).where(model.user_id == uid, *where)
            )

        return {
            "insights": n(Insight, Insight.active),
            "preds": n(Prediction),
            "runs": n(JobRun),
            "models": n(MLModel, MLModel.active),
        }


def test_seed_runs_full_pipeline(client):
    _, uid = seeded(client)
    with TestSession() as db:
        run = db.scalar(select(JobRun).where(JobRun.user_id == uid))
        assert run.status == "ok" and run.trigger == "seed" and run.duration_ms > 0
        for step in (
            "features",
            "patterns",
            "anomalies",
            "predictions",
            "backtest",
            "accuracy",
            "traits",
            "profile",
        ):
            assert run.steps[step]["status"] == "ok", (step, run.steps[step])
        assert run.steps["recommendations"]["status"] == "skipped"

        pats = db.scalars(
            select(Insight).where(Insight.user_id == uid, Insight.type == "pattern")
        ).all()
        keys = {p.key for p in pats}
        # the founder's planted patterns are rediscovered from the database data
        assert "pattern:min_exercise>mood@1" in keys, keys
        assert all(p.evidence["n"] >= 10 and abs(p.evidence["r"]) >= 0.4 for p in pats)
        assert all(p.first_seen == TODAY for p in pats)

        tomorrow = db.scalars(
            select(Prediction).where(
                Prediction.user_id == uid, Prediction.for_date == TODAY + timedelta(days=1)
            )
        ).all()
        targets = {p.target for p in tomorrow}
        assert {"mood", "energy"} <= targets and "task" in targets  # planned tasks exist
        for p in tomorrow:
            assert p.baseline is not None and p.model_kind and not p.backtest
            if p.target != "task":
                assert 1 <= p.low <= p.predicted <= p.high <= 5
        assert (
            db.scalar(
                select(func.count())
                .select_from(Prediction)
                .where(Prediction.user_id == uid, Prediction.backtest)
            )
            > 0
        )

        prof = db.get(TwinProfile, uid)
        assert prof.accuracy_score is not None and prof.data_days >= 50
        assert prof.traits["chronotype"]["source"] == "data"
        for m in db.scalars(select(MLModel).where(MLModel.user_id == uid, MLModel.active)):
            assert m.path is None or Path(m.path).exists()


def test_rerun_is_idempotent_and_keeps_answers(client):
    _, uid = seeded(client, "developer")
    before = counts(uid)
    with TestSession() as db:  # answer one of tomorrow's predictions by hand
        p = db.scalar(
            select(Prediction).where(
                Prediction.user_id == uid,
                Prediction.target == "energy",
                Prediction.backtest.is_(False),
            )
        )
        p.actual, pid = 2.0, p.id
        db.commit()
    run = run_user(TestSession, uid, trigger="retrain")
    assert run.status == "ok"
    after = counts(uid)
    assert after["insights"] == before["insights"] and after["preds"] == before["preds"]
    assert after["runs"] == before["runs"] + 1
    with TestSession() as db:
        assert db.get(Prediction, pid).actual == 2.0  # never overwritten
        # model versions are pruned to the configured number
        assert (
            db.scalar(
                select(func.count())
                .select_from(MLModel)
                .where(MLModel.user_id == uid, MLModel.target == "mood")
            )
            <= 3
        )


def test_consent_off_removes_checkin_based_predictions(client):
    tokens, uid = seeded(client, "student")
    client.put(
        "/privacy/consents", headers=auth(tokens), json={"source": "checkin", "allowed": False}
    )
    run_user(TestSession, uid, trigger="retrain")
    with TestSession() as db:
        left = db.scalars(
            select(Prediction.target).where(Prediction.user_id == uid, Prediction.for_date > TODAY)
        ).all()
        assert "mood" not in left and "energy" not in left
        active = db.scalars(select(Insight).where(Insight.user_id == uid, Insight.active)).all()
        # no surviving insight may rely on check-in values
        for i in active:
            assert i.evidence.get("feature") not in (
                "sleep_hours",
                "mood",
                "energy",
                "stress",
                "focus",
            ), i.text


def test_users_are_isolated_and_locked(client):
    _, uid_a = seeded(client, "founder")
    _, uid_b = seeded(client, "noise")
    with TestSession() as db:
        a_preds = {p.id for p in db.scalars(select(Prediction).where(Prediction.user_id == uid_a))}
        b_preds = {p.id for p in db.scalars(select(Prediction).where(Prediction.user_id == uid_b))}
    assert a_preds and b_preds and not (a_preds & b_preds)

    with engine.connect() as conn:  # someone else holds A's lock
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": lock_key(uid_a)})
        with pytest.raises(Busy):
            run_user(TestSession, uid_a, trigger="retrain")
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key(uid_a)})
        conn.commit()
    assert run_user(TestSession, uid_b, trigger="retrain").status == "ok"


def test_new_users_are_skipped_and_run_all(client):
    tokens = register(client)
    client.post(
        "/checkins",
        headers=auth(tokens),
        json={"date": TODAY.isoformat(), "mood": 3, "energy": 3, "stress": 3, "focus": 3},
    )
    with TestSession() as db:
        uid = db.scalar(select(User.id).where(User.email == tokens["email"]))
    run = run_user(TestSession, uid, trigger="retrain")
    assert run.status == "skipped" and "needs 3+" in run.steps["features"]["note"]
    _, _ = seeded(client, "developer", days=30)
    summary = run_all(TestSession)
    assert summary["users"] == 1 and summary["ok"] == 1  # only users with 3+ days
