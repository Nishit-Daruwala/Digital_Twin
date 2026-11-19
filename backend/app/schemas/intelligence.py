import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    key: str | None
    text: str
    evidence: dict
    confidence: float | None
    rank: float | None
    first_seen: date | None
    last_seen: date | None
    is_new: bool = False


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    for_date: date
    target: str
    task_id: uuid.UUID | None
    task_title: str | None = None
    predicted: float
    baseline: float | None
    low: float | None
    high: float | None
    model_kind: str | None
    backtest: bool
    actual: float | None
    confirmed_at: datetime | None
    explanation: dict
    suggested_actual: float | None = None  # pre-filled from the day's check-in / task state


class ConfirmIn(BaseModel):
    actual: float = Field(ge=0, le=5)


class AccuracyOut(BaseModel):
    accuracy: float | None
    baseline_accuracy: float | None
    n: int
    backtest_share: float = 0.0
    by_target: dict = Field(default_factory=dict)
    by_slot: dict = Field(default_factory=dict)  # time-of-day forecasts: {accuracy, n}


class ConfirmOut(BaseModel):
    prediction: PredictionOut
    accuracy: AccuracyOut


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    steps: dict
    error: str | None


class SeriesPoint(BaseModel):
    date: date
    mood: float | None = None
    energy: float | None = None
    focus: float | None = None
    stress: float | None = None
    sleep_hours: float | None = None


class CategoryMinutes(BaseModel):
    category: str
    minutes: int


class DashboardOut(BaseModel):
    data_days: int
    learning: dict  # {days, target, phase}
    accuracy: AccuracyOut
    tomorrow: list[PredictionOut]
    insights: list[InsightOut]
    anomalies: list[InsightOut]
    rhythm: list[InsightOut] = Field(default_factory=list)  # time-of-day statements
    traits: dict
    series: list[SeriesPoint]
    minutes_by_category: list[CategoryMinutes]
    last_run: JobRunOut | None
    pending_count: int
