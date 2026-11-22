import jwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DB
from app.core.config import settings
from app.core.security import (
    burn_password_check,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import CONSENT_SOURCES, Consent, TwinProfile, User
from app.schemas.auth import AccessToken, LoginIn, RefreshIn, RegisterIn, TokenPair
from app.services.rate_limit import RateLimiter, client_ip

router = APIRouter(prefix="/auth", tags=["auth"])

# Password guessing: a cap per account (any IP) and per IP (any account).
login_per_account = RateLimiter(settings.login_rate_limit_per_min, window_s=60)
login_per_ip = RateLimiter(settings.login_rate_limit_per_min * 3, window_s=60)
register_per_ip = RateLimiter(settings.register_rate_limit_per_hour, window_s=3600)


def _tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DB, request: Request) -> TokenPair:
    register_per_ip.enforce(client_ip(request), "Too many new accounts from this network.")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password), name=body.name)
    try:
        db.add(user)
        db.flush()  # assigns user.id; the unique-email check fires here
        db.add(TwinProfile(user_id=user.id, goals=[], categories=[], onboarding={}, traits={}))
        # Every data source starts allowed; the user can switch any off in Settings.
        db.add_all(Consent(user_id=user.id, source=s, allowed=True) for s in CONSENT_SOURCES)
        db.commit()
    except IntegrityError:  # two simultaneous registrations with the same email
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return _tokens(user)


@router.post("/login", response_model=TokenPair)
def login(body: LoginIn, db: DB, request: Request) -> TokenPair:
    login_per_ip.enforce(client_ip(request), "Too many login attempts.")
    login_per_account.enforce(body.email.lower(), "Too many login attempts for this account.")
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        burn_password_check(body.password)  # same response time as a wrong password
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _tokens(user)


@router.post("/refresh", response_model=AccessToken)
def refresh(body: RefreshIn, db: DB) -> AccessToken:
    try:
        user_id = decode_token(body.refresh_token, "refresh")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return AccessToken(access_token=create_token(user_id, "access"))
