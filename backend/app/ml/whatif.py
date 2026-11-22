"""What-if simulator (plan section 11): change tomorrow's plan-able inputs and see the twin's
prediction move, with SHAP reasons and the time-of-day view.

- Uses the user's current models (the ones the nightly run saved) and the same inputs as
  tomorrow's prediction, so with no changes it returns exactly the dashboard's numbers.
- Only inputs a *learned* model actually uses become sliders. If the twin predicts from
  your 4-week average alone, moving sliders would change nothing, so it says so instead.
- Slider ranges are the values you have actually had (no extrapolation).
- The prepared context is cached per user for a short time, so sliders answer fast.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.privacy import consent_map
from app.ml import intraday, predict, store
from app.ml.explain import explain
from app.ml.features import build_features, load_frames
from app.ml.labels import category_name
from app.models import Checkin, JobRun
from app.seed.patterns import slug

LEARNED = ("ridge", "xgboost")
CACHE_TTL_S = 300


@dataclass
class Control:
    key: str
    label: str
    unit: str
    min: float
    max: float
    step: float
    value: float  # what tomorrow's prediction assumes
    source: str  # planned / typical


@dataclass
class Context:
    f: pd.DataFrame
    categories: list[str]
    plan: dict
    sources: dict
    models: dict  # target -> Trained
    rhythm: dict
    controls: list[Control]


_cache: dict[uuid.UUID, tuple[float, tuple, Context]] = {}
_lock = threading.Lock()


def _version(db: Session, user_id: uuid.UUID) -> tuple:
    """Changes whenever new data or a new model could change the answer."""
    run = db.scalar(select(func.max(JobRun.finished_at)).where(JobRun.user_id == user_id))
    ck = db.scalar(select(func.max(Checkin.updated_at)).where(Checkin.user_id == user_id))
    return (run, ck, date.today())


def _control(key: str, f: pd.DataFrame, categories: list[str], plan: dict, src: dict):
    base = key.removeprefix("next_")
    if base not in f:
        return None
    hist = f.loc[f.get("imputed", 0) == 0, base].dropna() if "imputed" in f else f[base].dropna()
    if hist.empty or hist.min() == hist.max():
        return None
    if base == "sleep_hours":
        label, unit, step = "Sleep tonight", "h", 0.25
    elif base == "tasks_planned":
        label, unit, step = "Tasks planned for tomorrow", "tasks", 1.0
    elif base.startswith("min_"):
        label, unit, step = f"{category_name(base, categories)} tomorrow", "min", 15.0
    else:
        return None
    lo, hi = float(np.floor(hist.min() / step) * step), float(np.ceil(hist.max() / step) * step)
    value = plan.get(key)
    value = float(np.clip(value, lo, hi)) if value is not None and not pd.isna(value) else lo
    return Control(key, label, unit, lo, hi, step, round(value / step) * step, src.get(key, ""))


def context(db: Session, user_id: uuid.UUID) -> Context:
    version = _version(db, user_id)
    with _lock:
        hit = _cache.get(user_id)
        if hit and hit[1] == version and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[2]

    from app.ml.pipeline import _planned_tomorrow  # same plan as tomorrow's prediction

    today = date.today()
    tomorrow = today + timedelta(days=1)
    ck, acts, msgs, categories = load_frames(db, user_id, until=today)
    f = build_features(ck, acts, msgs, categories)
    if f.empty:  # no data yet, so no model either
        ctx = Context(f, categories, {}, {}, {}, intraday.learn(ck), [])
        with _lock:
            _cache[user_id] = (time.monotonic(), version, ctx)
        return ctx
    planned = _planned_tomorrow(db, user_id, tomorrow, consent_map(db, user_id)["activities"])
    minutes = {
        f"min_{slug(c)}": float(g["planned_min"].fillna(0).sum())
        for c, g in planned.groupby("category")
    }
    plan, sources = predict.assumed_plan(f, tomorrow, minutes, len(planned) or None)
    models = {t: store.load_active(db, user_id, t) for t in predict.REG_TARGETS}
    models = {t: m for t, m in models.items() if m is not None}
    used = sorted(
        {c for m in models.values() if m.kind in LEARNED for c in m.features if c in plan}
        - {k for k in plan if k.startswith("next_is_")}  # calendar facts aren't choices
    )
    controls = [c for k in used if (c := _control(k, f, categories, plan, sources))]
    ctx = Context(f, categories, plan, sources, models, intraday.learn(ck), controls)
    with _lock:
        _cache[user_id] = (time.monotonic(), version, ctx)
    return ctx


def simulate(ctx: Context, overrides: dict[str, float]) -> dict:
    """Predictions with the given changes, next to the unchanged baseline."""
    allowed = {c.key: c for c in ctx.controls}
    clean, clipped = {}, []
    for k, v in overrides.items():
        c = allowed.get(k)
        if c is None:
            continue
        x = float(np.clip(v, c.min, c.max))
        if x != v:
            clipped.append(k)
        clean[k] = x
    plan = {**ctx.plan, **clean}
    sources = {**ctx.sources, **dict.fromkeys(clean, "set")}

    out = {}
    for target, t in ctx.models.items():
        base_v = predict.predict_value(t, predict.tonight_row(ctx.f, ctx.plan, t.features))
        row = predict.tonight_row(ctx.f, plan, t.features)
        v = predict.predict_value(t, row)
        lo, hi = predict.interval(t, v)
        ex = explain(t, row, ctx.categories, sources)
        tod = intraday.forecast(v, ctx.rhythm, target)
        out[target] = {
            "value": round(v, 2),
            "baseline": round(base_v, 2),
            "delta": round(v - base_v, 2),
            "low": round(lo, 2),
            "high": round(hi, 2),
            "model_kind": t.kind,
            "learned": t.kind in LEARNED,
            "contributors": ex.get("contributors", []),
            "summary": ex.get("summary"),
            "time_of_day": tod if tod["learned"] else None,
        }
    return {"results": out, "applied": clean, "clipped": clipped}


def forget(user_id: uuid.UUID) -> None:
    with _lock:
        _cache.pop(user_id, None)
