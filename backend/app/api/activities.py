import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.api.common import date_range
from app.api.deps import DB, CurrentUser
from app.models import Activity, TwinProfile, User
from app.schemas.activity import ActivityIn, ActivityOut, ActivityPatch

router = APIRouter(prefix="/activities", tags=["activities"])


def _own_activity(db, user: User, activity_id: uuid.UUID) -> Activity:
    act = db.get(Activity, activity_id)
    # 404 (not 403) so we never reveal that another user's row exists.
    if act is None or act.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found")
    return act


def _check_category(db, user: User, category: str) -> str:
    profile = db.get(TwinProfile, user.id)
    allowed = profile.categories if profile else []
    if not allowed:
        return category
    for c in allowed:  # case-insensitive match, store the canonical spelling
        if c.lower() == category.strip().lower():
            return c
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        f"Unknown category '{category}'. Use one of: {', '.join(allowed)}",
    )


@router.post("", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
def create_activity(body: ActivityIn, user: CurrentUser, db: DB) -> Activity:
    data = body.model_dump()
    data["category"] = _check_category(db, user, body.category)
    act = Activity(**data, user_id=user.id, source="manual")
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


@router.get("", response_model=list[ActivityOut])
def list_activities(
    user: CurrentUser,
    db: DB,
    rng: Annotated[tuple[date | None, date | None], Depends(date_range)],
) -> list[Activity]:
    from_, to = rng
    q = select(Activity).where(Activity.user_id == user.id)
    if from_:
        q = q.where(Activity.date >= from_)
    if to:
        q = q.where(Activity.date <= to)
    return list(db.scalars(q.order_by(Activity.date, Activity.start_time, Activity.created_at)))


@router.patch("/{activity_id}", response_model=ActivityOut)
def update_activity(
    activity_id: uuid.UUID, body: ActivityPatch, user: CurrentUser, db: DB
) -> Activity:
    act = _own_activity(db, user, activity_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(act, field, value)
    db.commit()
    db.refresh(act)
    return act


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(activity_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    act = _own_activity(db, user, activity_id)
    db.delete(act)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
