"""Phase 3 API: insights, predictions, accuracy, dashboard, retrain."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser
from app.db import get_session_factory
from app.ml import accuracy as acc
from app.ml.pipeline import Busy, run_user
from app.models import Activity, Checkin, Insight, JobRun, Prediction, TwinProfile, User
from app.schemas.intelligence import (
    AccuracyOut,
    CategoryMinutes,
    ConfirmIn,
    ConfirmOut,
    DashboardOut,
    InsightOut,
    JobRunOut,
    PredictionOut,
    SeriesPoint,
)
from app.services.rate_limit import RateLimiter

router = APIRouter(tags=["intelligence"])
retrain_limiter = RateLimiter(limit=2, window_s=60)
SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]

LEARNING_TARGET_DAYS = 7  # "twin is learning: n/7 days"


def _insight_out(i: Insight, today: date) -> InsightOut:
    out = InsightOut.model_validate(i)
    out.is_new = bool(i.first_seen and (today - i.first_seen).days <= 3)
    return out


def _pred_out(db: Session, p: Prediction, user: User) -> PredictionOut:
    out = PredictionOut.model_validate(p)
    out.task_title = (p.explanation or {}).get("task", {}).get("title")
    if p.actual is None:
        if p.target in ("mood", "energy"):
            c = db.scalar(
                select(Checkin).where(Checkin.user_id == user.id, Checkin.date == p.for_date)
            )
            v = getattr(c, p.target) if c else None
            out.suggested_actual = float(v) if v is not None else None
        elif p.target == "task" and p.task_id:
            a = db.get(Activity, p.task_id)
            if a and a.user_id == user.id and p.for_date <= date.today():
                out.suggested_actual = 1.0 if a.completed else 0.0
    return out


def _active_insights(db: Session, user: User, type_: str, limit: int) -> list[Insight]:
    return list(
        db.scalars(
            select(Insight)
            .where(Insight.user_id == user.id, Insight.type == type_, Insight.active)
            .order_by(Insight.rank.desc().nullslast())
            .limit(limit)
        )
    )


@router.get("/insights", response_model=list[InsightOut])
def insights(user: CurrentUser, db: DB) -> list[InsightOut]:
    today = date.today()
    rows = _active_insights(db, user, "anomaly", 10) + _active_insights(db, user, "pattern", 20)
    return [_insight_out(i, today) for i in rows]


@router.get("/predictions/tomorrow", response_model=list[PredictionOut])
def predictions_tomorrow(user: CurrentUser, db: DB) -> list[PredictionOut]:
    tomorrow = date.today() + timedelta(days=1)
    rows = db.scalars(
        select(Prediction)
        .where(
            Prediction.user_id == user.id,
            Prediction.for_date == tomorrow,
            Prediction.backtest.is_(False),
        )
        .order_by(Prediction.target)
    )
    return [_pred_out(db, p, user) for p in rows]


@router.get("/predictions/pending", response_model=list[PredictionOut])
def predictions_pending(user: CurrentUser, db: DB) -> list[PredictionOut]:
    """Recent predictions whose day has started and that still need their real value."""
    today = date.today()
    rows = db.scalars(
        select(Prediction)
        .where(
            Prediction.user_id == user.id,
            Prediction.actual.is_(None),
            Prediction.backtest.is_(False),
            Prediction.for_date <= today,
            Prediction.for_date >= today - timedelta(days=3),
        )
        .order_by(Prediction.for_date.desc(), Prediction.target)
    )
    return [_pred_out(db, p, user) for p in rows]


@router.post("/predictions/{prediction_id}/confirm", response_model=ConfirmOut)
def confirm_prediction(
    prediction_id: uuid.UUID, body: ConfirmIn, user: CurrentUser, db: DB
) -> ConfirmOut:
    p = db.get(Prediction, prediction_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prediction not found")
    if p.for_date > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That day hasn't happened yet")
    if p.target == "task":
        if body.actual not in (0, 1):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Use 1 (done) or 0 (not done)"
            )
    elif not (1 <= body.actual <= 5) or body.actual != int(body.actual):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use a whole number from 1 to 5")
    acc.confirm(p, body.actual)
    score = acc.score(db, user.id, date.today())
    profile = db.get(TwinProfile, user.id)
    if profile:
        profile.accuracy_score = score["accuracy"]
    db.commit()
    db.refresh(p)
    return ConfirmOut(prediction=_pred_out(db, p, user), accuracy=AccuracyOut(**score))


@router.post("/jobs/retrain", response_model=JobRunOut)
def retrain(user: CurrentUser, session_factory: SessionFactory) -> JobRun:
    allowed, retry = retrain_limiter.allow(str(user.id))
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Your twin just updated. Try again in {retry}s.",
            headers={"Retry-After": str(retry)},
        )
    try:
        return run_user(session_factory, user.id, trigger="retrain")
    except Busy as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.get("/jobs/last", response_model=JobRunOut | None)
def last_run(user: CurrentUser, db: DB) -> JobRun | None:
    return db.scalar(
        select(JobRun).where(JobRun.user_id == user.id).order_by(JobRun.started_at.desc()).limit(1)
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    user: CurrentUser, db: DB, days: int = Query(default=30, ge=7, le=120)
) -> DashboardOut:
    today = date.today()
    profile = db.get(TwinProfile, user.id)
    data_days = profile.data_days if profile else 0
    if not data_days:  # before the first pipeline run, count check-in days directly
        data_days = (
            db.scalar(
                select(func.count(func.distinct(Checkin.date))).where(Checkin.user_id == user.id)
            )
            or 0
        )

    since = today - timedelta(days=days - 1)
    series = [
        SeriesPoint(
            date=c.date,
            mood=c.mood,
            energy=c.energy,
            focus=c.focus,
            stress=c.stress,
            sleep_hours=c.sleep_hours,
        )
        for c in db.scalars(
            select(Checkin)
            .where(Checkin.user_id == user.id, Checkin.date >= since, Checkin.date <= today)
            .order_by(Checkin.date)
        )
    ]
    mins = db.execute(
        select(Activity.category, func.sum(Activity.duration_min))
        .where(
            Activity.user_id == user.id,
            Activity.completed,
            Activity.date >= today - timedelta(days=13),
            Activity.date <= today,
        )
        .group_by(Activity.category)
        .order_by(func.sum(Activity.duration_min).desc())
    ).all()
    pending = (
        db.scalar(
            select(func.count())
            .select_from(Prediction)
            .where(
                Prediction.user_id == user.id,
                Prediction.actual.is_(None),
                Prediction.backtest.is_(False),
                Prediction.for_date <= today,
                Prediction.for_date >= today - timedelta(days=3),
            )
        )
        or 0
    )

    return DashboardOut(
        data_days=data_days,
        learning={
            "days": min(data_days, LEARNING_TARGET_DAYS),
            "target": LEARNING_TARGET_DAYS,
            "phase": "learning" if data_days < LEARNING_TARGET_DAYS else "predicting",
        },
        accuracy=AccuracyOut(**acc.score(db, user.id, today)),
        tomorrow=predictions_tomorrow(user, db),
        insights=[_insight_out(i, today) for i in _active_insights(db, user, "pattern", 6)],
        anomalies=[_insight_out(i, today) for i in _active_insights(db, user, "anomaly", 3)],
        traits=profile.traits if profile else {},
        series=series,
        minutes_by_category=[CategoryMinutes(category=c, minutes=int(m or 0)) for c, m in mins],
        last_run=last_run(user, db),
        pending_count=pending,
    )
