import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import Decision, User
from app.schemas.decision import DecisionIn, DecisionOut, DecisionPatch

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _own(db, user: User, decision_id: uuid.UUID) -> Decision:
    d = db.get(Decision, decision_id)
    if d is None or d.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Decision not found")
    return d


@router.get("", response_model=list[DecisionOut])
def list_decisions(
    user: CurrentUser, db: DB, limit: int = Query(default=100, ge=1, le=500)
) -> list[Decision]:
    return list(
        db.scalars(
            select(Decision)
            .where(Decision.user_id == user.id)
            .order_by(Decision.created_at.desc())
            .limit(limit)
        )
    )


@router.post("", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
def create_decision(body: DecisionIn, user: CurrentUser, db: DB) -> Decision:
    d = Decision(user_id=user.id, source="manual", **body.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.patch("/{decision_id}", response_model=DecisionOut)
def update_decision(
    decision_id: uuid.UUID, body: DecisionPatch, user: CurrentUser, db: DB
) -> Decision:
    d = _own(db, user, decision_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(decision_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    db.delete(_own(db, user, decision_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
