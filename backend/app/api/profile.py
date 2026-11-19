from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.core.timeutil import valid_timezone
from app.ml.traits import quiz_prior
from app.models import TwinProfile
from app.schemas.profile import MeOut, MeUpdateIn, OnboardingIn, TwinProfileOut, UserOut

router = APIRouter(tags=["profile"])


def _profile(db, user) -> TwinProfile:
    profile = db.get(TwinProfile, user.id)
    if profile is None:  # defensive: register always creates one
        profile = TwinProfile(user_id=user.id, goals=[], categories=[], onboarding={}, traits={})
        db.add(profile)
        db.commit()
    return profile


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, db: DB) -> MeOut:
    profile = _profile(db, user)
    return MeOut(
        user=UserOut.model_validate(user),
        profile=TwinProfileOut.model_validate(profile),
        onboarded=bool(profile.onboarding),
    )


@router.patch("/me", response_model=MeOut)
def update_me(body: MeUpdateIn, user: CurrentUser, db: DB) -> MeOut:
    """Set the timezone (the browser sends it), so check-in slots follow local time."""
    if not valid_timezone(body.timezone):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown timezone")
    user.timezone = body.timezone
    db.commit()
    return me(user, db)


@router.post("/onboarding", response_model=TwinProfileOut)
def onboarding(body: OnboardingIn, user: CurrentUser, db: DB) -> TwinProfileOut:
    profile = _profile(db, user)
    user.role = body.role
    profile.goals = body.goals
    profile.categories = body.categories
    profile.onboarding = {"quiz": body.quiz.model_dump()}
    # Data-driven traits (Phase 3) overwrite these; until then the quiz is the prior.
    profile.traits = quiz_prior(body.quiz)
    db.commit()
    db.refresh(profile)
    return TwinProfileOut.model_validate(profile)
