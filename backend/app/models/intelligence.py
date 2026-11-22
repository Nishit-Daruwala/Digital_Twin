"""Outputs of the nightly pipeline: insights, predictions, recommendations, plus the
pipeline's own bookkeeping (job runs, model registry)."""

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import created_at_col, updated_at_col, user_fk, uuid_pk


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (Index("ix_insights_user_key", "user_id", "key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # pattern / anomaly / daytype
    # Stable identity across nightly runs, e.g. "pattern:sleep_hours>focus@1"
    key: Mapped[str | None] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # {feature, target, r, p, p_adj, lag, n, effect...}
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[float | None] = mapped_column(Float)  # |rho| * sqrt(n)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen: Mapped[date_type | None] = mapped_column(Date)
    last_seen: Mapped[date_type | None] = mapped_column(Date)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_user_date", "user_id", "for_date"),
        # One prediction per user/day/target/task: nightly reruns update instead of duplicating.
        UniqueConstraint(
            "user_id",
            "for_date",
            "target",
            "task_id",
            name="uq_prediction_slot",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    for_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    target: Mapped[str] = mapped_column(String(20), nullable=False)  # energy / mood / task
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    predicted: Mapped[float] = mapped_column(Float, nullable=False)
    # What the naive "7-day mean" (or base rate for tasks) would have said: honest comparison.
    baseline: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)  # rough range from validation error
    high: Mapped[float | None] = mapped_column(Float)
    model_kind: Mapped[str | None] = mapped_column(String(20))  # mean / ridge / xgboost / ...
    backtest: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    actual: Mapped[float | None] = mapped_column(Float)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # SHAP
    created_at: Mapped[datetime] = created_at_col()


class Recommendation(Base):
    """Up to 3 per day (ml/recommend.py). Feedback 1 / -1 trains the per-type preference."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_user_date", "user_id", "for_date"),
        UniqueConstraint("user_id", "for_date", "key", name="uq_recommendation_key"),
        CheckConstraint("feedback IS NULL OR feedback IN (-1, 0, 1)", name="feedback_values"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    for_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    relevance: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(SmallInteger)
    policy: Mapped[str | None] = mapped_column(String(12))
    feedback: Mapped[int | None] = mapped_column(SmallInteger)  # -1 / 0 / 1
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class JobRun(Base):
    """One pipeline run for one user (nightly, retrain button, demo seed)."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_user_started", "user_id", "started_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # nightly / retrain / seed
    status: Mapped[str] = mapped_column(String(12), nullable=False)  # running/ok/error/skipped
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class MLModel(Base):
    """Registry of trained per-user models (the file lives in MODEL_STORE_DIR)."""

    __tablename__ = "ml_models"
    __table_args__ = (Index("ix_ml_models_user_target", "user_id", "target", "active"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    target: Mapped[str] = mapped_column(String(20), nullable=False)  # energy / mood / task
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str | None] = mapped_column(Text)  # None for the "mean" baseline
    features: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    n_train: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
