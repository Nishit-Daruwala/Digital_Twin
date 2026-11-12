"""Privacy endpoints. Phase 1: consents. Export and delete arrive in Phase 4 (week 7)."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.models import CONSENT_SOURCES, Consent
from app.schemas.privacy import ConsentIn, ConsentOut

router = APIRouter(prefix="/privacy", tags=["privacy"])


def consent_map(db, user_id) -> dict[str, bool]:
    """Missing rows count as allowed (the default at registration)."""
    rows = db.scalars(select(Consent).where(Consent.user_id == user_id))
    current = {c.source: c.allowed for c in rows}
    return {s: current.get(s, True) for s in CONSENT_SOURCES}


@router.get("/consents", response_model=list[ConsentOut])
def get_consents(user: CurrentUser, db: DB) -> list[ConsentOut]:
    return [ConsentOut(source=s, allowed=a) for s, a in consent_map(db, user.id).items()]


@router.put("/consents", response_model=list[ConsentOut])
def put_consent(body: ConsentIn, user: CurrentUser, db: DB) -> list[ConsentOut]:
    row = db.get(Consent, (user.id, body.source))
    if row is None:
        db.add(Consent(user_id=user.id, source=body.source, allowed=body.allowed))
    else:
        row.allowed = body.allowed
    db.commit()
    return get_consents(user, db)
