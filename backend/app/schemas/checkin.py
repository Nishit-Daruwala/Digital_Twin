import uuid
from datetime import date as Date
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Scale = Field(ge=1, le=5)
OptScale = Field(default=None, ge=1, le=5)
Slot = Literal["morning", "afternoon", "evening"]


class CheckinIn(BaseModel):
    """Full check-in (everything) or quick check-in (mood + energy). Date and slot default
    to the user's current local day and part of the day."""

    date: Date | None = None
    slot: Slot | None = None
    mood: int = Scale
    energy: int = Scale
    stress: int | None = OptScale
    focus: int | None = OptScale
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    note: str | None = Field(default=None, max_length=280)


class CheckinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: Date
    slot: Slot
    checked_at: datetime | None
    mood: int | None
    energy: int | None
    stress: int | None
    focus: int | None
    sleep_hours: float | None
    note: str | None
    source: str
    updated_at: datetime


class SlotOut(BaseModel):
    slot: Slot
    label: str
    window: str
    started: bool
    current: bool
    checkin: CheckinOut | None


class CheckinDayOut(BaseModel):
    """Today's three slots, for the check-in page and the "how are you now?" prompt."""

    date: Date
    current_slot: Slot
    timezone: str
    full_done: bool  # today's long check-in (sleep, stress, focus) is done
    slots: list[SlotOut]
