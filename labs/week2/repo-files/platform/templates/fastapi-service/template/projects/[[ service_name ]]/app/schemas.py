"""Typed request/response models: the API contract, validated on the way in and on the way out."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Ready(BaseModel):
    status: Literal["ready", "not-ready"]
    checks: dict[str, bool]


class Info(BaseModel):
    service: str
    version: str
    environment: str


class EchoIn(BaseModel):
    message: str = Field(min_length=1, max_length=200)


class EchoOut(BaseModel):
    message: str
    length: int
    service: str
