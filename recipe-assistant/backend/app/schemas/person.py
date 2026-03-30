from __future__ import annotations

from pydantic import BaseModel


class PersonCreate(BaseModel):
    name: str
    preferences: str = ""


class PersonUpdate(BaseModel):
    name: str | None = None
    preferences: str | None = None


class PersonResponse(BaseModel):
    id: int
    name: str
    preferences: str

    model_config = {"from_attributes": True}
