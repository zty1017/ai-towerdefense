"""Shared helpers and exception translators for frontend runtime API routers.

This module centralizes the session guard, payload wrapper, and the
HTTPException translations that several frontend-facing routers reuse
(404 conversions for missing fixtures, scheduler entries, and map runtime
packages, plus the 409 conversion for invalid queue transitions).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ..models import FrontendMockPayloadResponse
from ..services.frontend_mock_service import FixtureNotFoundError
from ..services.generation_scheduler_service import (
    GenerationSchedulerFixtureNotFoundError,
    InvalidQueueTransitionError,
)
from ..services.map_render_plan_service import MapRenderPlanNotFoundError
from ..services.map_runtime_service import MapRuntimePackageNotFoundError
from ._session_guard import require_session as _require_session


def _payload(session_id: str, data: dict[str, Any]) -> FrontendMockPayloadResponse:
    mode = str(data.pop("mode", "frontend_mock_fixture"))
    data.pop("session_id", None)
    return FrontendMockPayloadResponse(session_id=session_id, mode=mode, payload=data)


def _fixture_404(exc: FixtureNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"mock fixture not found for: {exc}",
    )


def _scheduler_fixture_404(exc: GenerationSchedulerFixtureNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"scheduler fixture not found for: {exc}",
    )


def _map_runtime_fixture_404(exc: MapRuntimePackageNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"map runtime package not found for: {exc}",
    )


def _map_render_plan_fixture_404(exc: MapRenderPlanNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"map render plan not found for: {exc}",
    )


def _queue_transition_409(exc: InvalidQueueTransitionError | ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    )
