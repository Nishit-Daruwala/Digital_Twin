"""The per-user pipeline (plan section 12), run nightly, on "Retrain", and after demo seeding.

Order: features -> patterns -> anomalies -> models + predictions + SHAP -> resolve past
predictions + accuracy -> traits -> (recommendations: Phase 4) -> profile.

Robustness:
- Idempotent: insights are upserted by a stable key, predictions by (day, target, task).
- A Postgres advisory lock per user means two runs never overlap (nightly vs Retrain).
- Each step is isolated: a failing step is logged in job_runs and the rest still run,
  except when the feature table itself can't be built.
- Consent: everything starts from features.load_frames, which drops disallowed sources.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ml import accuracy, anomaly, intraday, patterns, predict, store
from app.ml.explain import explain
from app.ml.features import build_features, load_frames
from app.ml.traits import compute_traits, quiz_prior
from app.models import Activity, Checkin, Insight, JobRun, Prediction, TwinProfile
from app.schemas.profile import QuizAnswers
from app.services.insight_wording import reword, verified

log = logging.getLogger("twin.pipeline")

MIN_DAYS = 3
MAX_ACTIVE_PATTERNS = 8
NIGHTLY_LOCK = 0x7417_0000_0001


def lock_key(user_id: uuid.UUID) -> int:
    return user_id.int & 0x7FFF_FFFF_FFFF_FFFF


def clean(obj):
    """JSON-safe copy: NaN/inf -> None, numpy scalars -> Python (Postgres JSONB rejects NaN)."""
    import math

    import numpy as np

    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [clean(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, date | datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return obj


class Busy(Exception):
    """Another pipeline run for this user is in progress."""


# --------------------------------------------------------------------------------------


def run_user(
    session_factory: Callable[[], Session],
    user_id: uuid.UUID,
    *,
    trigger: str,
    today: date | None = None,
    backtest_days: int = 0,
) -> JobRun:
    today = today or date.today()
    with session_factory() as db:
        engine = db.get_bind()
    with engine.connect() as lock_conn:
        got = lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key(user_id)}
        ).scalar()
        if not got:
            raise Busy("A twin update is already running.")
        try:
            return _run_locked(session_factory, user_id, trigger, today, backtest_days)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key(user_id)})
            lock_conn.commit()


def _run_locked(session_factory, user_id, trigger, today, backtest_days) -> JobRun:
    t0 = time.perf_counter()
    with session_factory() as db:
        run = JobRun(user_id=user_id, trigger=trigger, status="running", steps={})
        db.add(run)
        db.commit()
        run_id = run.id

    steps: dict[str, dict] = {}
    status, error = "ok", None
    with session_factory() as db:
        try:
            ctx = _step(steps, "features", lambda: _load(db, user_id, today))
            if ctx is None:
                raise RuntimeError("feature step failed")
            f, acts, categories, data_days, ck = ctx
            rhythm = intraday.learn(ck)
            if data_days < MIN_DAYS:
                status = "skipped"
                steps["features"]["note"] = f"needs {MIN_DAYS}+ days of data (has {data_days})"
            else:
                _step(steps, "patterns", lambda: _patterns(db, user_id, f, categories, today))
                _step(steps, "anomalies", lambda: _anomalies(db, user_id, f, today))
                _step(steps, "rhythm", lambda: _rhythm(db, user_id, ck, rhythm, today))
                _step(
                    steps,
                    "predictions",
                    lambda: _predictions(db, user_id, f, acts, categories, today, rhythm),
                )
                if backtest_days:
                    _step(
                        steps,
                        "backtest",
                        lambda: _backtest(db, user_id, f, ck, today, backtest_days),
                    )
                _step(steps, "accuracy", lambda: _accuracy(db, user_id, today))
                _step(steps, "traits", lambda: _traits(db, user_id, f, acts, categories, data_days))
                steps["recommendations"] = {"status": "skipped", "note": "Phase 4"}
            _step(steps, "profile", lambda: _profile(db, user_id, data_days))
            if any(s.get("status") == "error" for s in steps.values()):
                status = "error"
                error = "; ".join(
                    f"{k}: {v.get('error')}" for k, v in steps.items() if v.get("status") == "error"
                )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            status, error = "error", f"{type(exc).__name__}: {exc}"
            log.exception("pipeline failed for %s", user_id)

    with session_factory() as db:
        run = db.get(JobRun, run_id)
        run.status, run.error, run.steps = status, error, clean(steps)
        run.finished_at = datetime.now(UTC)
        run.duration_ms = int((time.perf_counter() - t0) * 1000)
        db.commit()
        db.refresh(run)
        return run


def _step(steps: dict, name: str, fn):
    t = time.perf_counter()
    try:
        result = fn()
        info = {"status": "ok", "ms": int((time.perf_counter() - t) * 1000)}
        if isinstance(result, dict):
            info.update(result)
        steps[name] = info
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception("step %s failed", name)
        steps[name] = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(limit=3)[-600:],
            "ms": int((time.perf_counter() - t) * 1000),
        }
        return None


# --------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------


def _load(db: Session, user_id: uuid.UUID, today: date):
    checkins, acts, messages, categories = load_frames(db, user_id, until=today)
    f = build_features(checkins, acts, messages, categories)
    data_days = int((f["imputed"] == 0).sum()) if not f.empty else 0
    return f, acts, categories, data_days, checkins


def _upsert_insight(db, user_id, key, type_, text_, evidence, confidence, rank, today):
    row = db.scalar(select(Insight).where(Insight.user_id == user_id, Insight.key == key))
    if row is None:
        row = Insight(user_id=user_id, key=key, type=type_, text=text_, first_seen=today)
        db.add(row)
    row.text, row.evidence = text_, clean(evidence)
    row.confidence = None if confidence is None else float(confidence)
    row.rank = None if rank is None else float(rank)
    row.active, row.last_seen = True, today
    return row


def _patterns(db: Session, user_id, f, categories, today) -> dict:
    found = patterns.discover(f, categories)[:MAX_ACTIVE_PATTERNS]
    existing = {
        r.key: r
        for r in db.scalars(
            select(Insight).where(Insight.user_id == user_id, Insight.type == "pattern")
        )
    }

    # Reword only what's new, whose numbers changed, or whose earlier wording no longer
    # passes today's checks (self-healing). Keeps the LLM cost tiny.
    def stale(p) -> bool:
        row = existing.get(p.key)
        if row is None or row.evidence.get("template") != p.template:
            return True
        return row.text != p.template and not verified(p.template, row.text)

    to_word = {p.key: p.template for p in found if stale(p)}
    worded = reword(to_word)

    keep = set()
    for p in found:
        ev = p.evidence()
        if p.key in worded:
            txt, ev["wording"] = worded[p.key]
        else:
            txt, ev["wording"] = existing[p.key].text, existing[p.key].evidence.get("wording")
        _upsert_insight(db, user_id, p.key, "pattern", txt, ev, p.confidence, p.rank, today)
        keep.add(p.key)

    # Stability: an insight that slips just under the bar stays for a while instead of
    # flickering off and on; it's retired when the link is clearly gone.
    retired = 0
    for key, row in existing.items():
        if key in keep or not row.active:
            continue
        col, tgt = row.evidence.get("column"), row.evidence.get("target")
        still = False
        if col in f and tgt in f:
            ok = f[col].notna() & f[tgt].notna()
            if ok.sum() >= patterns.MIN_N and f.loc[ok, col].nunique() > 1:
                from scipy import stats

                r, pv = stats.spearmanr(f.loc[ok, col], f.loc[ok, tgt])
                still = abs(r) >= 0.3 and pv < 0.01
        if still and (today - (row.last_seen or today)).days <= 14:
            row.evidence = {**row.evidence, "fading": True}
        else:
            row.active = False
            retired += 1
    db.commit()
    return {
        "found": len(found),
        "new": len([k for k in keep if k not in existing]),
        "retired": retired,
        "llm_worded": sum(1 for v in worded.values() if v[1] == "llm"),
    }


def _anomalies(db: Session, user_id, f, today) -> dict:
    found = anomaly.detect(f, today)[:4]
    keys = {a.key for a in found}
    for row in db.scalars(
        select(Insight).where(Insight.user_id == user_id, Insight.type == "anomaly", Insight.active)
    ):
        if row.key not in keys:
            row.active = False
    for a in found:
        ev = {**a.evidence, "kind": a.kind, "day": a.day.isoformat()}
        _upsert_insight(
            db, user_id, a.key, "anomaly", a.text, ev, min(1.0, a.severity / 4), a.severity, today
        )
    db.commit()
    return {"found": len(found)}


def _rhythm(db: Session, user_id, ck, rhythm: dict, today) -> dict:
    """Time-of-day statements ("energy is higher in the morning than in the evening")."""
    found = intraday.insights(ck)
    keys = {f"rhythm:{r['metric']}" for r in found}
    for row in db.scalars(
        select(Insight).where(Insight.user_id == user_id, Insight.type == "rhythm", Insight.active)
    ):
        if row.key not in keys:
            row.active = False
    for r in found:
        evidence = {k: v for k, v in r.items() if k not in ("text", "confidence")}
        evidence["offsets"] = {
            s: v["offset"] for s, v in rhythm["metrics"].get(r["metric"], {}).items()
        }
        _upsert_insight(
            db,
            user_id,
            f"rhythm:{r['metric']}",
            "rhythm",
            r["text"],
            evidence,
            r["confidence"],
            r["diff"] * r["n"] ** 0.5,
            today,
        )
    db.commit()
    return {"found": len(found), "days_with_2plus": rhythm["days_multi"]}


def _time_of_day(value: float, rhythm: dict, target: str) -> dict | None:
    """Per-slot forecast, only once the rhythm has been seen (days with 2+ check-ins)."""
    tod = intraday.forecast(value, rhythm, target)
    return tod if tod["learned"] else None


def _planned_tomorrow(db: Session, user_id, tomorrow, allowed: bool) -> pd.DataFrame:
    cols = ["id", "category", "title", "planned_min", "start_time"]
    if not allowed:
        return pd.DataFrame(columns=cols)
    rows = db.execute(
        select(
            Activity.id,
            Activity.category,
            Activity.title,
            Activity.planned_min,
            Activity.start_time,
        ).where(
            Activity.user_id == user_id,
            Activity.date == tomorrow,
            Activity.planned,
            Activity.completed.is_(False),
        )
    ).all()
    return pd.DataFrame([dict(zip(cols, r, strict=True)) for r in rows], columns=cols)


def _upsert_prediction(db, user_id, for_date, target, task_id, **vals):
    row = db.scalar(
        select(Prediction).where(
            Prediction.user_id == user_id,
            Prediction.for_date == for_date,
            Prediction.target == target,
            Prediction.task_id.is_(None) if task_id is None else Prediction.task_id == task_id,
        )
    )
    if row is not None and row.actual is not None:
        return row  # never overwrite a prediction that already has its answer
    if row is None:
        row = Prediction(
            user_id=user_id,
            for_date=for_date,
            target=target,
            task_id=task_id,
            predicted=vals["predicted"],
        )
        db.add(row)
    for k, v in vals.items():
        setattr(row, k, clean(v))
    return row


def _predictions(db: Session, user_id, f, acts, categories, today, rhythm=None) -> dict:
    from app.api.privacy import consent_map
    from app.seed.patterns import slug

    tomorrow = today + timedelta(days=1)
    consents = consent_map(db, user_id)
    planned = _planned_tomorrow(db, user_id, tomorrow, consents["activities"])
    planned_minutes = {}
    for cat, grp in planned.groupby("category"):
        planned_minutes[f"min_{slug(cat)}"] = float(grp["planned_min"].fillna(0).sum())
    plan, sources = predict.assumed_plan(f, tomorrow, planned_minutes, len(planned) or None)

    out = {}
    last_day = pd.to_datetime(max(f.index)).date()
    stale = (today - last_day).days > 2
    for target in predict.REG_TARGETS:
        if not consents["checkin"]:
            # Consent withdrawn: also remove open predictions built from that data.
            for p in db.scalars(
                select(Prediction).where(
                    Prediction.user_id == user_id,
                    Prediction.target == target,
                    Prediction.for_date >= today,
                    Prediction.actual.is_(None),
                )
            ):
                db.delete(p)
            out[target] = "skipped (check-in consent off)"
            continue
        if stale or target not in f or f[target].notna().sum() < MIN_DAYS:
            out[target] = "skipped (no recent data)"
            continue
        t = predict.train_regression(f, target)
        store.save(db, user_id, t)
        row = predict.tonight_row(f, plan, t.features)
        value = predict.predict_value(t, row)
        lo, hi = predict.interval(t, value)
        base = float(f[target].dropna().tail(7).mean())
        ex = explain(t, row, categories, sources)
        ex["assumptions"] = {
            k: {"value": v, "source": sources.get(k)}
            for k, v in plan.items()
            if sources.get(k) in ("planned", "set") or k == "next_sleep_hours"
        }
        tod = _time_of_day(value, rhythm or {}, target)
        if tod:
            ex["time_of_day"] = tod
        _upsert_prediction(
            db,
            user_id,
            tomorrow,
            target,
            None,
            predicted=round(value, 3),
            baseline=round(base, 3),
            low=round(lo, 2),
            high=round(hi, 2),
            model_kind=t.kind,
            explanation=ex,
            backtest=False,
        )
        out[target] = t.kind

    # Task completion for tomorrow's planned tasks
    tt = predict.train_tasks(acts, f, categories, today)
    store.save(db, user_id, tt)
    keep_ids = set()
    if not planned.empty and not stale:
        rows = predict.task_rows(planned, f, categories, tomorrow, plan.get("next_sleep_hours"))
        for (_, task), (_, r) in zip(planned.iterrows(), rows.iterrows(), strict=True):
            rr = pd.DataFrame([r])
            prob = predict.predict_task(tt, rr)
            ex = explain(tt, rr.reindex(columns=tt.features), categories, sources)
            ex["task"] = {
                "title": task["title"],
                "category": task["category"],
                "planned_min": task["planned_min"],
            }
            _upsert_prediction(
                db,
                user_id,
                tomorrow,
                "task",
                task["id"],
                predicted=round(prob, 3),
                baseline=tt.metrics.get("rate"),
                model_kind=tt.kind,
                explanation=ex,
                backtest=False,
            )
            keep_ids.add(task["id"])
    # drop task predictions for tasks no longer planned (deleted / moved / done)
    for p in db.scalars(
        select(Prediction).where(
            Prediction.user_id == user_id,
            Prediction.for_date == tomorrow,
            Prediction.target == "task",
            Prediction.actual.is_(None),
        )
    ):
        if p.task_id not in keep_ids:
            db.delete(p)
    out["task"] = f"{tt.kind} ({len(keep_ids)} tasks)"
    db.commit()
    return out


def _backtest(db: Session, user_id, f, ck, today, days: int) -> dict:
    """Walk-forward history for demo users: for each of the last `days` days, train only on
    what was known the evening before and predict that day; the answer is already known.
    Marked backtest=True so the UI can say so."""
    made = 0
    idx = pd.to_datetime(pd.Index(f.index))
    for d in [today - timedelta(days=i) for i in range(days, 0, -1)]:
        past = f[idx < pd.Timestamp(d)]
        actual_row = f[idx == pd.Timestamp(d)]
        if len(past) < MIN_DAYS or actual_row.empty or int(actual_row["imputed"].iloc[0]):
            continue
        plan, _ = predict.assumed_plan(past, d)
        # the rhythm as known the evening before (no peeking at that day's check-ins)
        rhythm_d = (
            intraday.learn(ck[pd.to_datetime(ck["date"]) < pd.Timestamp(d)]) if len(ck) else {}
        )
        for target in predict.REG_TARGETS:
            actual = actual_row[target].iloc[0]
            if target not in past or pd.isna(actual):
                continue
            t = predict.train_regression(past, target)
            value = predict.predict_value(t, predict.tonight_row(past, plan, t.features))
            lo, hi = predict.interval(t, value)
            ex = {"model": t.kind, "backtest": True, "contributors": []}
            tod = _time_of_day(value, rhythm_d, target)
            if tod:
                ex["time_of_day"] = tod
            _upsert_prediction(
                db,
                user_id,
                d,
                target,
                None,
                predicted=round(value, 3),
                baseline=round(float(past[target].dropna().tail(7).mean()), 3),
                low=round(lo, 2),
                high=round(hi, 2),
                model_kind=t.kind,
                backtest=True,
                explanation=ex,
                actual=float(actual),
            )
            made += 1
    db.commit()
    return {"predictions": made}


def _accuracy(db: Session, user_id, today) -> dict:
    resolved = accuracy.resolve_past(db, user_id, today)
    s = accuracy.score(db, user_id, today)
    profile = db.get(TwinProfile, user_id)
    if profile:
        profile.accuracy_score = s["accuracy"]
    db.commit()
    return {"resolved": resolved, **{k: s[k] for k in ("accuracy", "baseline_accuracy", "n")}}


def _traits(db: Session, user_id, f, acts, categories, data_days) -> dict:
    profile = db.get(TwinProfile, user_id)
    if profile is None:
        return {"note": "no profile"}
    quiz = (profile.onboarding or {}).get("quiz")
    prior = quiz_prior(QuizAnswers(**quiz)) if quiz else (profile.traits or {})
    profile.traits = compute_traits(f, acts, categories, prior, data_days)
    db.commit()
    return {
        "from_data": sum(
            1 for t in profile.traits.values() if isinstance(t, dict) and t.get("source") == "data"
        )
    }


def _profile(db: Session, user_id, data_days) -> dict:
    profile = db.get(TwinProfile, user_id)
    if profile:
        profile.data_days = data_days
        db.commit()
    return {"data_days": data_days}


# --------------------------------------------------------------------------------------
# All users (nightly)
# --------------------------------------------------------------------------------------


def eligible_users(db: Session) -> list[uuid.UUID]:
    q = (
        select(Checkin.user_id)
        .group_by(Checkin.user_id)
        .having(func.count(func.distinct(Checkin.date)) >= MIN_DAYS)
    )
    return list(db.scalars(q))


def run_all(
    session_factory: Callable[[], Session], *, trigger: str = "nightly", today: date | None = None
) -> dict:
    """Run every eligible user, one at a time. A global lock prevents two schedulers
    (e.g. two API workers) from running the nightly job simultaneously."""
    with session_factory() as db:
        engine = db.get_bind()
        users = eligible_users(db)
    summary = {"users": len(users), "ok": 0, "skipped": 0, "error": 0, "busy": 0}
    with engine.connect() as lock_conn:
        if not lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": NIGHTLY_LOCK}
        ).scalar():
            return {**summary, "note": "another nightly run is in progress"}
        try:
            for uid in users:
                try:
                    run = run_user(session_factory, uid, trigger=trigger, today=today)
                    summary[run.status] = summary.get(run.status, 0) + 1
                except Busy:
                    summary["busy"] += 1
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": NIGHTLY_LOCK})
            lock_conn.commit()
    log.info("nightly run: %s", summary)
    return summary
