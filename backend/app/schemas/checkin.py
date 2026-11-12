import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

Scale = Field(ge=1, le=5)


class CheckinIn(BaseModel):
    date: date
    mood: int = Scale
    energy: int = Scale
    stress: int = Scale
    focus: int = Scale
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    note: str | None = Field(default=None, max_length=280)


class CheckinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    mood: int | None
    energy: int | None
    stress: int | None
    focus: int | None
    sleep_hours: float | None
    note: str | None
    source: str
    updated_at: datetime
