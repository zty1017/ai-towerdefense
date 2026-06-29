"""Pydantic v2 models for session API responses and request bodies."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateRequest(BaseModel):
    """Optional body for POST /api/sessions. All fields optional for anonymity."""

    display_name: Optional[str] = Field(
        default=None,
        description="Optional human-readable label for the session. Not required.",
    )


class SessionInfo(BaseModel):
    """Public representation of an anonymous session."""

    session_id: str = Field(..., description="Opaque, randomly generated session id.")
    display_name: Optional[str] = Field(
        default=None, description="Optional human-readable label for the session."
    )
    created_at: datetime
    last_active_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionCreateResponse(BaseModel):
    session_id: str
    session: SessionInfo


class SessionResetResponse(BaseModel):
    session_id: str
    session: SessionInfo
    reset: bool = True


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
