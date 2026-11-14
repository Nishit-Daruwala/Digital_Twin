import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DecisionIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=8)
    choice: str | None = Field(default=None, max_length=200)
    reasoning: str | None = Field(default=None, max_length=1000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("options")
    @classmethod
    def clean_options(cls, v: list[str]) -> list[str]:
        return [o.strip()[:120] for o in v if o and o.strip()]


class DecisionPatch(BaseModel):
    choice: str | None = Field(default=None, max_length=200)
    reasoning: str | None = Field(default=None, max_length=1000)
    outcome_rating: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def not_empty(self) -> "DecisionPatch":
        if not self.model_fields_set:
            raise ValueError("nothing to update")
        return self


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    options: list[str]
    choice: str | None
    reasoning: str | None
    outcome_rating: int | None
    source: str
    created_at: datetime
