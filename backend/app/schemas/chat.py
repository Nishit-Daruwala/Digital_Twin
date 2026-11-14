import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.activity import ActivityOut
from app.schemas.checkin import CheckinOut
from app.schemas.decision import DecisionOut

Scale = Field(default=None, ge=1, le=5)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    today: date | None = None  # client's local date, so "today" matches the user's day

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


# ---------- extraction card (what the user reviews, edits and confirms) ----------


class CardCheckin(BaseModel):
    mood: int | None = Scale
    energy: int | None = Scale
    stress: int | None = Scale
    focus: int | None = Scale
    sleep_hours: float | None = Field(default=None, ge=0, le=24)

    def is_empty(self) -> bool:
        return all(v is None for v in self.model_dump().values())


class CardActivity(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=60)
    duration_min: int | None = Field(default=None, ge=0, le=1440)
    planned: bool = False
    completed: bool = True
    start_time: time | None = None

    @field_validator("title", "category")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class CardDecision(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=8)
    choice: str | None = Field(default=None, max_length=200)
    reasoning: str | None = Field(default=None, max_length=1000)

    @field_validator("options")
    @classmethod
    def clean_options(cls, v: list[str]) -> list[str]:
        return [o.strip()[:120] for o in v if o and o.strip()]


class ExtractionCard(BaseModel):
    date: date
    checkin: CardCheckin = Field(default_factory=CardCheckin)
    activities: list[CardActivity] = Field(default_factory=list, max_length=20)
    decisions: list[CardDecision] = Field(default_factory=list, max_length=10)

    def is_empty(self) -> bool:
        return self.checkin.is_empty() and not self.activities and not self.decisions


# ---------- responses ----------


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    text: str
    created_at: datetime
    learnable: bool
    extraction: dict | None
    extraction_status: str | None


class ConfirmOut(BaseModel):
    message: MessageOut
    checkin: CheckinOut | None
    activities: list[ActivityOut]
    decisions: list[DecisionOut]
