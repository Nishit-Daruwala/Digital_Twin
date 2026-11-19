"""Raw data the twin learns from: check-ins, activities, decisions, chat messages."""

import uuid
from datetime import date as date_type
from datetime import datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db import Base
from app.models.base import created_at_col, updated_at_col, user_fk, uuid_pk


def _scale_1_5(col: str) -> CheckConstraint:
    return CheckConstraint(f"{col} IS NULL OR {col} BETWEEN 1 AND 5", name=f"{col}_1_5")


class Checkin(Base):
    """Up to three per day, one per slot (morning / afternoon / evening, see ml.intraday).
    The first of the day asks everything; later ones may be quick (mood + energy only)."""

    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "date", "slot", name="uq_checkins_user_date_slot"),
        CheckConstraint("slot IN ('morning', 'afternoon', 'evening')", name="slot_valid"),
        _scale_1_5("mood"),
        _scale_1_5("energy"),
        _scale_1_5("stress"),
        _scale_1_5("focus"),
        CheckConstraint("sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 24", name="sleep_0_24"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    slot: Mapped[str] = mapped_column(String(10), nullable=False, server_default="morning")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mood: Mapped[int | None] = mapped_column(SmallInteger)
    energy: Mapped[int | None] = mapped_column(SmallInteger)
    stress: Mapped[int | None] = mapped_column(SmallInteger)
    focus: Mapped[int | None] = mapped_column(SmallInteger)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_user_date", "user_id", "date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    duration_min: Mapped[int | None] = mapped_column(Integer)  # actual minutes
    planned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    planned_min: Mapped[int | None] = mapped_column(Integer)  # estimated minutes
    source: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class Decision(Base):  # stretch
    __tablename__ = "decisions"
    __table_args__ = (_scale_1_5("outcome_rating"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    created_at: Mapped[datetime] = created_at_col()
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    choice: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    outcome_rating: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[str] = mapped_column(
        String(10), default="manual", server_default="manual", nullable=False
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_user_created", "user_id", "created_at"),
        Index(
            "ix_messages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = user_fk()
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user / twin
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    sentiment: Mapped[float | None] = mapped_column(Float)  # -1 .. 1
    topics: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Chat consent at the moment the message was sent. False = saved for history only,
    # never used for memory recall or features.
    learnable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    # Pending confirmation card produced by extraction (user messages only).
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    extraction_status: Mapped[str | None] = mapped_column(String(12))  # pending/confirmed/dismissed
    created_at: Mapped[datetime] = created_at_col()
