"""What-if simulator API (plan section 11)."""

from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser
from app.ml import whatif
from app.services.rate_limit import RateLimiter

router = APIRouter(prefix="/whatif", tags=["what-if"])
limiter = RateLimiter(limit=120, window_s=60)  # sliders send many small requests


class ControlOut(BaseModel):
    key: str
    label: str
    unit: str
    min: float
    max: float
    step: float
    value: float
    source: str


class WhatIfIn(BaseModel):
    overrides: dict[str, float] = Field(default_factory=dict, max_length=20)


class WhatIfOut(BaseModel):
    controls: list[ControlOut]
    results: dict
    applied: dict[str, float]
    clipped: list[str]
    note: str | None
    ms: int


def _note(ctx: whatif.Context) -> str | None:
    if not ctx.models:
        return "Your twin needs a few days of check-ins before it can predict anything."
    if not ctx.controls:
        return (
            "So far your twin predicts tomorrow from your recent average: nothing you can "
            "plan (sleep, activities, tasks) has shown a reliable effect yet. Keep logging; "
            "sliders appear here once one does."
        )
    return None


def _run(db, user, overrides: dict[str, float]) -> WhatIfOut:
    t0 = time.perf_counter()
    ctx = whatif.context(db, user.id)
    res = (
        whatif.simulate(ctx, overrides)
        if ctx.models
        else {"results": {}, "applied": {}, "clipped": []}
    )
    return WhatIfOut(
        controls=[ControlOut(**asdict(c)) for c in ctx.controls],
        note=_note(ctx),
        ms=int((time.perf_counter() - t0) * 1000),
        **res,
    )


@router.get("", response_model=WhatIfOut)
def options(user: CurrentUser, db: DB) -> WhatIfOut:
    """The sliders, and tomorrow's prediction with nothing changed."""
    return _run(db, user, {})


@router.post("", response_model=WhatIfOut)
def simulate(body: WhatIfIn, user: CurrentUser, db: DB) -> WhatIfOut:
    allowed, retry = limiter.allow(str(user.id))
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many changes at once. Try again in {retry}s.",
            headers={"Retry-After": str(retry)},
        )
    return _run(db, user, body.overrides)
