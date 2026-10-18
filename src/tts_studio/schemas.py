"""Pydantic request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoadRequest(BaseModel):
    variant: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class InstallRequest(BaseModel):
    spec: str = "base"


class GenerateRequest(BaseModel):
    engine: str
    model: str | None = None
    voice: str
    text: str
    options: dict[str, Any] = Field(default_factory=dict)


class PreviewRequest(BaseModel):
    engine: str
    model: str | None = None
    voice: str
    options: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)
