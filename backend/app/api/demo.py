from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.db import get_session_factory
from app.ml.pipeline import Busy, run_user
from app.seed.synthetic_users import PERSONAS, seed_persona_into_user

router = APIRouter(prefix="/demo", tags=["demo"])


class SeedIn(BaseModel):
    persona: Literal["student", "developer", "founder", "noise"]
    days: int = Field(default=60, ge=14, le=180)


class SeedOut(BaseModel):
    persona: str
    days: int
    checkins: int
    activities: int
    messages: int
    decisions: int
    planted_patterns: list[str]
    pipeline: str  # status of the twin update that ran right after seeding


@router.get("/personas")
def personas() -> list[dict]:
    if not settings.demo_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return [{"key": k, "name": v["name"], "patterns": v["patterns"]} for k, v in PERSONAS.items()]


@router.post("/seed", response_model=SeedOut)
def seed(
    body: SeedIn,
    user: CurrentUser,
    db: DB,
    session_factory: Annotated[Callable[[], Session], Depends(get_session_factory)],
) -> SeedOut:
    """Replace the current user's data with a synthetic persona's history, then run the
    twin's pipeline (with a 14-day back-test) so insights and predictions appear at once."""
    if not settings.demo_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    counts = seed_persona_into_user(db, user, body.persona, body.days)
    try:
        run = run_user(
            session_factory,
            user.id,
            trigger="seed",
            backtest_days=settings.demo_backtest_days,
        )
        pipeline = run.status
    except Busy:
        pipeline = "busy"
    return SeedOut(persona=body.persona, days=body.days, pipeline=pipeline, **counts)
