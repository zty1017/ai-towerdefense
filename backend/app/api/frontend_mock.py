"""Frontend mock routes for the MVP playable flow.

The routes in this module are deliberately fixture-backed. They expose the
reviewed MVP content package, generated media manifest, map, briefing, battle
config, runtime package, settlement, and simple evidence surface through the
same backend namespace the real game will use later.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ..db import db_cursor
from ..models import (
    BattleResultSubmitRequest,
    FrontendMockPayloadResponse,
    WorldInstanceCreateRequest,
)
from ..services import frontend_mock_service
from ..services.frontend_mock_service import FixtureNotFoundError

router = APIRouter()


def _require_session(session_id: str) -> None:
    """Raise 404 if the anonymous session does not exist."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session not found: {session_id}",
            )


def _payload(session_id: str, data: dict[str, Any]) -> FrontendMockPayloadResponse:
    mode = str(data.pop("mode", "frontend_mock_fixture"))
    data.pop("session_id", None)
    return FrontendMockPayloadResponse(session_id=session_id, mode=mode, payload=data)


def _fixture_404(exc: FixtureNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"mock fixture not found for: {exc}",
    )


@router.post(
    "/api/sessions/{session_id}/world-instance",
    response_model=FrontendMockPayloadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_world_instance(
    session_id: str, body: WorldInstanceCreateRequest | None = None
) -> FrontendMockPayloadResponse:
    """Create the fixture-backed world instance for this session."""
    _require_session(session_id)
    selected = body.selected_options if body is not None else None
    return _payload(
        session_id,
        frontend_mock_service.create_world_instance(session_id, selected),
    )


@router.get(
    "/api/sessions/{session_id}/frontend-mock-pack",
    response_model=FrontendMockPayloadResponse,
)
def get_frontend_mock_pack(session_id: str) -> FrontendMockPayloadResponse:
    """Return the player-safe frontend mock pack plus generated media manifest."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_frontend_mock_pack(session_id))


@router.get(
    "/api/sessions/{session_id}/opening",
    response_model=FrontendMockPayloadResponse,
)
def get_opening(session_id: str) -> FrontendMockPayloadResponse:
    """Return the prebuilt opening text/card sequence."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_opening(session_id))


@router.get(
    "/api/sessions/{session_id}/animation-seeds",
    response_model=FrontendMockPayloadResponse,
)
def get_animation_seeds(session_id: str) -> FrontendMockPayloadResponse:
    """Return seed images for the future image-to-video animation pipeline."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_animation_seeds(session_id))


@router.get(
    "/api/sessions/{session_id}/map",
    response_model=FrontendMockPayloadResponse,
)
def get_map(session_id: str) -> FrontendMockPayloadResponse:
    """Return the strategic map with current session world-state projection."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_map(session_id))


@router.get(
    "/api/sessions/{session_id}/nodes/{node_id}/briefing",
    response_model=FrontendMockPayloadResponse,
)
def get_node_briefing(session_id: str, node_id: str) -> FrontendMockPayloadResponse:
    """Return node briefing data for the MVP battle node."""
    _require_session(session_id)
    try:
        data = frontend_mock_service.get_node_briefing(session_id, node_id)
    except FixtureNotFoundError as exc:
        raise _fixture_404(exc) from exc
    return _payload(session_id, data)


@router.get(
    "/api/sessions/{session_id}/battles/{node_id}/config",
    response_model=FrontendMockPayloadResponse,
)
def get_battle_config(session_id: str, node_id: str) -> FrontendMockPayloadResponse:
    """Return battle config, toolbar assets, and media for a mock battle."""
    _require_session(session_id)
    try:
        data = frontend_mock_service.get_battle_config(session_id, node_id)
    except FixtureNotFoundError as exc:
        raise _fixture_404(exc) from exc
    return _payload(session_id, data)


@router.get(
    "/api/sessions/{session_id}/battles/{node_id}/runtime-package",
    response_model=FrontendMockPayloadResponse,
)
def get_runtime_package(session_id: str, node_id: str) -> FrontendMockPayloadResponse:
    """Return the reviewed runtime package for a mock battle node."""
    _require_session(session_id)
    try:
        data = frontend_mock_service.get_runtime_package(session_id, node_id)
    except FixtureNotFoundError as exc:
        raise _fixture_404(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/battles/{node_id}/results",
    response_model=FrontendMockPayloadResponse,
)
def submit_battle_result(
    session_id: str,
    node_id: str,
    body: BattleResultSubmitRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record a mock battle result and return settlement/world-state changes."""
    _require_session(session_id)
    result = body.model_dump() if body is not None else {}
    try:
        data = frontend_mock_service.record_battle_result(session_id, node_id, result)
    except FixtureNotFoundError as exc:
        raise _fixture_404(exc) from exc
    return _payload(session_id, data)


@router.get(
    "/api/sessions/{session_id}/settlement/latest",
    response_model=FrontendMockPayloadResponse,
)
def get_latest_settlement(session_id: str) -> FrontendMockPayloadResponse:
    """Return the latest settlement payload for the session, if any."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_latest_settlement(session_id))


@router.get(
    "/api/sessions/{session_id}/evidence",
    response_model=FrontendMockPayloadResponse,
)
def get_evidence(session_id: str) -> FrontendMockPayloadResponse:
    """Return a compact Studio/evidence payload for demos and video capture."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_evidence(session_id))
