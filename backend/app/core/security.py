import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# Used when the email doesn't exist, so login takes the same time either way
# (prevents discovering registered emails by timing).
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_token(user_id: uuid.UUID, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    if token_type == "access":
        expires = now + timedelta(minutes=settings.access_token_minutes)
    else:
        expires = now + timedelta(days=settings.refresh_token_days)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> uuid.UUID:
    """Return the user id inside a valid token, or raise jwt.InvalidTokenError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("bad subject") from exc
