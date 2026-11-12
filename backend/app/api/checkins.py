from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.common import date_range
from app.api.deps import DB, CurrentUser
from app.models import Checkin
from app.schemas.checkin import CheckinIn, CheckinOut

router = APIRouter(prefix="/checkins", tags=["checkins"])


@router.post("", response_model=CheckinOut)
def upsert_checkin(body: CheckinIn, user: CurrentUser, db: DB) -> Checkin:
    """One check-in per day; a later check-in for the same date overwrites it."""
    if body.date > date.today() + timedelta(days=1):  # +1 tolerates timezone differences
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is in the future")

    values = body.model_dump() | {"user_id": user.id, "source": "manual"}
    stmt = insert(Checkin).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_checkins_user_date",
        set_={k: stmt.excluded[k] for k in values if k not in ("user_id", "date")}
        | {"updated_at": stmt.excluded.updated_at},
    ).returning(Checkin.id)
    checkin_id = db.execute(stmt).scalar_one()
    db.commit()
    return db.get(Checkin, checkin_id, populate_existing=True)


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
    return list(db.scalars(q.order_by(Checkin.date)))
