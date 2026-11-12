"""Outputs of the nightly pipeline: insights, predictions, recommendations."""

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Date, Float, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import created_at_col, user_fk, uuid_pk


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # pattern / anomaly / trait
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # {feature, target, r, p, lag, n, effect...}
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_user_date", "user_id", "for_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    for_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    target: Mapped[str] = mapped_column(String(20), nullable=False)  # energy / mood / task
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    predicted: Mapped[float] = mapped_column(Float, nullable=False)
    actual: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # SHAP
    created_at: Mapped[datetime] = created_at_col()


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_user_date", "user_id", "for_date"),
        CheckConstraint("feedback IS NULL OR feedback IN (-1, 0, 1)", name="feedback_values"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    for_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[int | None] = mapped_column(SmallInteger)  # -1 / 0 / 1
    created_at: Mapped[datetime] = created_at_col()
