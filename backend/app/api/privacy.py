"""Privacy: consents per data source, export of everything, and deleting the twin."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, select

from app.api.deps import DB, CurrentUser
from app.models import (
    CONSENT_SOURCES,
    Activity,
    Checkin,
    Consent,
    Decision,
    Insight,
    JobRun,
    Message,
    MLModel,
    Prediction,
    Recommendation,
    TwinProfile,
)
from app.schemas.privacy import ConsentIn, ConsentOut, DeleteMeIn

router = APIRouter(prefix="/privacy", tags=["privacy"])
me_router = APIRouter(tags=["privacy"])

# Everything stored about a user. Secrets and machine-only columns are left out.
EXPORT = [
    ("checkins", Checkin, ()),
    ("activities", Activity, ()),
    ("decisions", Decision, ()),
    ("chat_messages", Message, ("embedding",)),
    ("insights", Insight, ()),
    ("predictions", Prediction, ()),
    ("recommendations", Recommendation, ()),
    ("consents", Consent, ()),
    ("models", MLModel, ("path",)),
    ("pipeline_runs", JobRun, ()),
]


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


def _row(obj, exclude=()) -> dict:
    return {
        a.key: getattr(obj, a.key)
        for a in inspect(obj).mapper.column_attrs
        if a.key not in exclude and a.key != "user_id"
    }


@router.get("/export")
def export(user: CurrentUser, db: DB) -> JSONResponse:
    """All of your data as one JSON file (a download)."""
    profile = db.get(TwinProfile, user.id)
    data = {
        "exported_at": datetime.now(UTC),
        "user": _row(user, ("password_hash",)),
        "profile": _row(profile) if profile else None,
    }
    for name, model, exclude in EXPORT:
        rows = db.scalars(select(model).where(model.user_id == user.id)).all()
        data[name] = [_row(r, exclude) for r in rows]
    filename = f"twin-export-{date.today().isoformat()}.json"
    return JSONResponse(
        jsonable_encoder(data),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@me_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(body: DeleteMeIn, user: CurrentUser, db: DB) -> Response:
    """Delete the account and every row about it (cascade), plus saved model files."""
    from app.ml import store, whatif

    if body.confirm_email.strip().lower() != user.email.lower():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Type your account email to confirm"
        )
    user_id = user.id
    db.delete(user)
    db.commit()
    store.delete_user_models(user_id)
    whatif.forget(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
