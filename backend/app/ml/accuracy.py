"""Feedback loop and accuracy score (plan section 10).

- A regression prediction is a hit when |predicted - actual| <= 0.5; a task prediction is a
  hit when the predicted class (p >= 0.5) matches whether the task was done.
- Accuracy = hit rate over the last 14 days. The same is computed for the naive baseline,
  so the dashboard can say honestly whether the twin beats "your 7-day average".
- Past predictions are resolved from the user's own data: that day's check-ins (mood,
  energy; several a day are adjusted for time of day and averaged, as the model learns them)
  and whether the planned task was completed. Users can also confirm by hand.
- Time-of-day forecasts (explanation["time_of_day"]) are scored against the check-in made in
  that slot, the same 1/2-point rule.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml import intraday
from app.models import Activity, Checkin, Prediction

WINDOW_DAYS = 14
TOLERANCE = 0.5


def is_hit(target: str, predicted: float | None, actual: float | None) -> bool | None:
    if predicted is None or actual is None:
        return None
    if target == "task":
        return (predicted >= 0.5) == (actual >= 0.5)
    return abs(predicted - actual) <= TOLERANCE


def checkin_frame(db: Session, user_id: uuid.UUID, until: date | None = None) -> pd.DataFrame:
    cols = ["date", "slot", *intraday.METRICS]
    q = select(*[getattr(Checkin, c) for c in cols]).where(Checkin.user_id == user_id)
    if until:
        q = q.where(Checkin.date <= until)
    return pd.DataFrame(
        [dict(zip(cols, r, strict=True)) for r in db.execute(q).all()], columns=cols
    )


def daily_actuals(db: Session, user_id: uuid.UUID, until: date | None = None) -> dict:
    """{day: {"mood": x, "energy": y, ...}}: the day's slot-adjusted check-in values."""
    ck = checkin_frame(db, user_id, until)
    if ck.empty:
        return {}
    days = intraday.daily(ck)
    return {r["date"]: r for r in days.to_dict("records")}


def resolve_past(db: Session, user_id: uuid.UUID, today: date) -> int:
    """Fill in `actual` for predictions about days that are over. Returns how many."""
    pending = db.scalars(
        select(Prediction).where(
            Prediction.user_id == user_id, Prediction.actual.is_(None), Prediction.for_date < today
        )
    ).all()
    n = 0
    days = daily_actuals(db, user_id, today) if pending else {}
    for p in pending:
        if p.target in ("mood", "energy"):
            v = days.get(p.for_date, {}).get(p.target)
            if v is not None and not pd.isna(v):
                p.actual, n = round(float(v), 3), n + 1
        elif p.target == "task" and p.task_id:
            a = db.get(Activity, p.task_id)
            if a is not None and a.user_id == user_id:
                p.actual, n = (1.0 if a.completed else 0.0), n + 1
    return n


def confirm(p: Prediction, actual: float) -> None:
    p.actual = float(actual)
    p.confirmed_at = datetime.now(UTC)


def score(db: Session, user_id: uuid.UUID, today: date) -> dict:
    rows = db.scalars(
        select(Prediction).where(
            Prediction.user_id == user_id,
            Prediction.actual.is_not(None),
            Prediction.for_date >= today - timedelta(days=WINDOW_DAYS),
            Prediction.for_date <= today,
        )
    ).all()
    hits = [is_hit(p.target, p.predicted, p.actual) for p in rows]
    base = [is_hit(p.target, p.baseline, p.actual) for p in rows if p.baseline is not None]
    n = len(rows)
    acc = sum(hits) / n if n else None
    base_acc = sum(base) / len(base) if base else None
    slot_hits = _slot_hits(db, user_id, rows)
    return {
        "accuracy": round(acc, 3) if acc is not None else None,
        "baseline_accuracy": round(base_acc, 3) if base_acc is not None else None,
        "n": n,
        "backtest_share": round(sum(p.backtest for p in rows) / n, 2) if n else 0.0,
        "by_target": {
            t: round(
                sum(h for h, p in zip(hits, rows, strict=True) if p.target == t)
                / max(1, sum(p.target == t for p in rows)),
                3,
            )
            for t in sorted({p.target for p in rows})
        },
        "by_slot": {
            "accuracy": round(sum(slot_hits) / len(slot_hits), 3) if slot_hits else None,
            "n": len(slot_hits),
        },
    }


def _slot_hits(db: Session, user_id: uuid.UUID, rows: list[Prediction]) -> list[bool]:
    """Each time-of-day forecast vs the check-in made in that slot (when there is one)."""
    rows = [p for p in rows if (p.explanation or {}).get("time_of_day")]
    if not rows:
        return []
    days = {p.for_date for p in rows}
    ck = db.scalars(select(Checkin).where(Checkin.user_id == user_id, Checkin.date.in_(days))).all()
    seen = {(c.date, c.slot): c for c in ck}
    hits = []
    for p in rows:
        for slot, f in p.explanation["time_of_day"].get("slots", {}).items():
            c = seen.get((p.for_date, slot))
            v = getattr(c, p.target, None) if c else None
            if v is not None:
                hits.append(abs(float(f["value"]) - float(v)) <= TOLERANCE)
    return hits
