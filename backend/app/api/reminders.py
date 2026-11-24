"""Check-in reminder emails: one-click unsubscribe (from the email) and a test send."""

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.security import decode_token
from app.core.timeutil import local_now
from app.jobs.reminders import build_email
from app.models import User
from app.services import email as mail
from app.services.rate_limit import RateLimiter

router = APIRouter(prefix="/reminders", tags=["reminders"])
test_limiter = RateLimiter(limit=3, window_s=3600)


class UnsubscribeIn(BaseModel):
    token: str = Field(min_length=10, max_length=2000)


class UnsubscribeOut(BaseModel):
    email_reminders: bool


class TestOut(BaseModel):
    sent_to: str
    provider: str


@router.post("/unsubscribe", response_model=UnsubscribeOut)
def unsubscribe(body: UnsubscribeIn, db: DB) -> UnsubscribeOut:
    """No login needed: the signed token in the email's link identifies the user and can
    only switch reminders off. (A POST from a page, so link scanners can't trigger it.)"""
    try:
        user_id = decode_token(body.token, "unsubscribe")
    except jwt.InvalidTokenError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This link has expired. Turn reminders off in Settings."
        ) from None
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    user.email_reminders = False
    db.commit()
    return UnsubscribeOut(email_reminders=False)


@router.post("/test", response_model=TestOut)
def send_test(user: CurrentUser, db: DB) -> TestOut:
    """Send today's reminder to yourself now, to check that email works."""
    test_limiter.enforce(str(user.id), "Test emails are limited to 3 an hour.")
    if not mail.deliverable(user.email):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{user.email} can't receive mail (reserved domain)."
        )
    try:
        mail.send(build_email(db, user, local_now(user).date()))
    except mail.EmailError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The email server refused the message. Check SMTP settings.",
        ) from exc
    return TestOut(sent_to=user.email, provider=settings.email_provider)
