import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    for_date: date
    type: str
    text: str
    reason: str | None
    rank: int | None
    feedback: int | None
    created_at: datetime


class TypeLearning(BaseModel):
    """What the twin has learned about one kind of advice from the user's thumbs."""

    type: str
    label: str
    likes: int
    dislikes: int
    preference: float  # posterior mean, 0..1 (0.5 = no opinion yet)


class RecommendationsOut(BaseModel):
    for_date: date | None
    items: list[RecommendationOut]
    learning: list[TypeLearning]
    policy: str


class FeedbackIn(BaseModel):
    value: Literal[1, -1, 0]  # helpful / not for me / undo
