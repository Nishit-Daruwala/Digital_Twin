import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TwinProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    goals: list[str]
    categories: list[str]
    onboarding: dict
    traits: dict
    accuracy_score: float | None
    data_days: int
    updated_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: str | None
    timezone: str | None
    email_reminders: bool
    created_at: datetime


class MeUpdateIn(BaseModel):
    timezone: str | None = Field(default=None, min_length=1, max_length=64)  # IANA name
    email_reminders: bool | None = None  # the 8 PM "you haven't checked in" email


class MeOut(BaseModel):
    user: UserOut
    profile: TwinProfileOut
    onboarded: bool


class QuizAnswers(BaseModel):
    """Five onboarding questions. They act as a trait prior until ~14 days of data exist."""

    best_time: Literal["morning", "afternoon", "evening", "night"]
    plans_ahead: int = Field(ge=1, le=5)  # 1 = improvise, 5 = plan everything
    estimate_bias: Literal["faster", "accurate", "slower", "much_slower"]
    routine: int = Field(ge=1, le=5)  # 1 = every day different, 5 = same every day
    stress_source: Literal["deadlines", "people", "sleep", "uncertainty", "workload"]


def _clean_list(values: list[str], max_items: int) -> list[str]:
    seen: list[str] = []
    for v in values:
        v = v.strip()
        if v and v.lower() not in {s.lower() for s in seen}:
            seen.append(v[:60])
    if len(seen) > max_items:
        raise ValueError(f"at most {max_items} items")
    return seen


class OnboardingIn(BaseModel):
    role: str = Field(min_length=1, max_length=120)
    goals: list[str] = Field(min_length=1)
    categories: list[str] = Field(min_length=1)
    quiz: QuizAnswers

    @field_validator("role")
    @classmethod
    def strip_role(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("role must not be blank")
        return v

    @field_validator("goals")
    @classmethod
    def clean_goals(cls, v: list[str]) -> list[str]:
        v = _clean_list(v, 5)
        if not v:
            raise ValueError("add at least one goal")
        return v

    @field_validator("categories")
    @classmethod
    def clean_categories(cls, v: list[str]) -> list[str]:
        v = _clean_list(v, 12)
        if not v:
            raise ValueError("add at least one category")
        return v
