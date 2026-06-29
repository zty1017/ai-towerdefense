"""Health check router."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import get_app_version
from ..models import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=get_app_version())
