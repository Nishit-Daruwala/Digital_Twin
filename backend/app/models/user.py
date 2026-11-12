import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import created_at_col, updated_at_col, user_fk, uuid_pk

CONSENT_SOURCES = ("chat", "checkin", "activities", "decisions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str | None] = mapped_column(Text)  # free text
    created_at: Mapped[datetime] = created_at_col()

    profile: Mapped["TwinProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )


class TwinProfile(Base):
    __tablename__ = "twin_profiles"

    user_id: Mapped[uuid.UUID] = user_fk(primary_key=True)
    goals: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    categories: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    onboarding: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    traits: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    accuracy_score: Mapped[float | None] = mapped_column(Float)
    data_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = updated_at_col()

    user: Mapped[User] = relationship(back_populates="profile")


class Consent(Base):
    __tablename__ = "consents"

    user_id: Mapped[uuid.UUID] = user_fk(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = updated_at_col()
