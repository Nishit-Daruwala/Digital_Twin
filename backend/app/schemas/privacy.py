from typing import Literal

from pydantic import BaseModel

ConsentSource = Literal["chat", "checkin", "activities", "decisions"]


class ConsentIn(BaseModel):
    source: ConsentSource
    allowed: bool


class ConsentOut(BaseModel):
    source: ConsentSource
    allowed: bool
