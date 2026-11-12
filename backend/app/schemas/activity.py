import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ActivityIn(BaseModel):
    date: date
    category: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    start_time: time | None = None
    duration_min: int | None = Field(default=None, ge=0, le=1440)  # actual minutes
    planned_min: int | None = Field(default=None, ge=0, le=1440)  # estimate
    planned: bool = False
    completed: bool = False

    @field_validator("title", "category")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ActivityPatch(BaseModel):
    """Only fields present in the body are changed. `completed` may be omitted but not null;
    `duration_min` may be null (clears it)."""

    completed: bool | None = None
    duration_min: int | None = Field(default=None, ge=0, le=1440)

    @field_validator("completed")
    @classmethod
    def completed_not_null(cls, v: bool | None) -> bool:
        if v is None:
            raise ValueError("completed cannot be null")
        return v

    @model_validator(mode="after")
    def not_empty(self) -> "ActivityPatch":
        if not self.model_fields_set:
            raise ValueError("nothing to update")
        return self


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    category: str
    title: str
    start_time: time | None
    duration_min: int | None
    planned_min: int | None
    planned: bool
    completed: bool
    source: str
    created_at: datetime
