from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.common import date_range
from app.api.deps import DB, CurrentUser
from app.core.timeutil import local_now
from app.ml.intraday import SLOT_LABEL, SLOT_WINDOW, SLOTS, slot_for, slot_started
from app.models import Checkin
from app.schemas.checkin import CheckinDayOut, CheckinIn, CheckinOut, SlotOut

router = APIRouter(prefix="/checkins", tags=["checkins"])

FULL_FIELDS = ("stress", "focus", "sleep_hours")


def _order(rows: list[Checkin]) -> list[Checkin]:
    return sorted(rows, key=lambda c: (c.date, SLOTS.index(c.slot)))


@router.post("", response_model=CheckinOut)
def upsert_checkin(body: CheckinIn, user: CurrentUser, db: DB) -> Checkin:
    """One check-in per slot of a day; saving the same slot again updates it.
    Fields left out (e.g. sleep in a quick check-in) keep their saved value."""
    now = local_now(user)
    today, current = slot_for(now)
    day = body.date or today
    # Without a saved timezone, allow a day of slack for the browser's local date.
    latest = today if user.timezone else today + timedelta(days=1)
    if day > latest:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is in the future")
    slot = body.slot or (current if day == today else "evening")
    if user.timezone and not slot_started(day, slot, now):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The {slot} hasn't started yet")

    given = body.model_dump(exclude_unset=True, exclude={"date", "slot"})
    values = {
        **given,
        "user_id": user.id,
        "date": day,
        "slot": slot,
        "source": "manual",
        "checked_at": datetime.now(UTC),
    }
    stmt = insert(Checkin).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_checkins_user_date_slot",
        set_={k: stmt.excluded[k] for k in values if k not in ("user_id", "date", "slot")}
        | {"updated_at": stmt.excluded.updated_at},
    ).returning(Checkin.id)
    checkin_id = db.execute(stmt).scalar_one()
    db.commit()
    return db.get(Checkin, checkin_id, populate_existing=True)


@router.get("/today", response_model=CheckinDayOut)
def today_slots(user: CurrentUser, db: DB) -> CheckinDayOut:
    now = local_now(user)
    today, current = slot_for(now)
    rows = {
        c.slot: c
        for c in db.scalars(
            select(Checkin).where(Checkin.user_id == user.id, Checkin.date == today)
        )
    }
    full_done = any(getattr(c, f) is not None for c in rows.values() for f in FULL_FIELDS)
    return CheckinDayOut(
        date=today,
        current_slot=current,
        timezone=user.timezone or "UTC",
        full_done=full_done,
        slots=[
            SlotOut(
                slot=s,
                label=SLOT_LABEL[s],
                window=SLOT_WINDOW[s],
                started=slot_started(today, s, now),
                current=s == current,
                checkin=CheckinOut.model_validate(rows[s]) if s in rows else None,
            )
            for s in SLOTS
        ],
    )


@router.get("", response_model=list[CheckinOut])
def list_checkins(
    user: CurrentUser,
    db: DB,
    rng: Annotated[tuple[date | None, date | None], Depends(date_range)],
) -> list[Checkin]:
    from_, to = rng
    q = select(Checkin).where(Checkin.user_id == user.id)
    if from_:
        q = q.where(Checkin.date >= from_)
    if to:
        q = q.where(Checkin.date <= to)
    return _order(list(db.scalars(q)))
