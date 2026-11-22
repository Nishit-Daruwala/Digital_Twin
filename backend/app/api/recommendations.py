"""Recommendations with thumbs feedback (plan section 9). A thumbs-down immediately refills
the day's list from the remaining candidates, so feedback visibly changes what you see."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.ml import recommend
from app.models import Recommendation
from app.schemas.recommendation import (
    FeedbackIn,
    RecommendationOut,
    RecommendationsOut,
    TypeLearning,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _out(db, user) -> RecommendationsOut:
    today = date.today()
    latest = db.scalar(
        select(Recommendation.for_date)
        .where(Recommendation.user_id == user.id, Recommendation.for_date >= today)
        .order_by(Recommendation.for_date.desc())
        .limit(1)
    )
    items = []
    if latest:
        items = db.scalars(
            select(Recommendation)
            .where(
                Recommendation.user_id == user.id,
                Recommendation.for_date == latest,
                (Recommendation.feedback.is_(None)) | (Recommendation.feedback == 1),
            )
            .order_by(Recommendation.rank.nullslast())
        ).all()
    counts = recommend.feedback_stats(db, user.id)  # plain counts, for display
    decay = recommend.DECAY if settings.recommend_policy == "thompson" else 1.0
    stats = recommend.feedback_stats(db, user.id, today, decay)  # what the policy uses
    learning = [
        TypeLearning(
            type=t,
            label=label,
            likes=int(counts.get(t, (0, 0))[0]),
            dislikes=int(counts.get(t, (0, 0))[1]),
            preference=recommend.type_weight(stats, t),
        )
        for t, label in recommend.TYPES.items()
    ]
    return RecommendationsOut(
        for_date=latest,
        items=[RecommendationOut.model_validate(r) for r in items],
        learning=learning,
        policy=settings.recommend_policy,
    )


@router.get("", response_model=RecommendationsOut)
def list_recommendations(user: CurrentUser, db: DB) -> RecommendationsOut:
    return _out(db, user)


@router.post("/{rec_id}/feedback", response_model=RecommendationsOut)
def feedback(rec_id: uuid.UUID, body: FeedbackIn, user: CurrentUser, db: DB) -> RecommendationsOut:
    rec = db.get(Recommendation, rec_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    recommend.give_feedback(db, rec, body.value)
    if body.value == -1:  # refill with the next best suggestion right away
        recommend.generate(
            db, user.id, rec.for_date - timedelta(days=1), policy=settings.recommend_policy
        )
    return _out(db, user)
