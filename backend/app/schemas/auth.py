from pydantic import BaseModel, EmailStr, Field, field_validator


def _check_password_bytes(v: str) -> str:
    # bcrypt only uses the first 72 BYTES; multi-byte characters count more than once.
    if len(v.encode("utf-8")) > 72:
        raise ValueError("password is too long (max 72 bytes)")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_rules(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("password must not be blank")
        return _check_password_bytes(v)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_bytes(cls, v: str) -> str:
        return _check_password_bytes(v)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
