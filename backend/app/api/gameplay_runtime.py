"""Gameplay runtime routes for the MVP playable flow.

This module hosts the non-scheduler frontend routes: world instance/catalog,
frontend mock pack, opening, animation seeds, runtime art kit, campaign router,
feature snapshots, strategic map, node briefing, battle config/runtime/map
packages, settlement, and the Studio/evidence surface. All routes are
fixture-backed and share the session guard and payload wrapper from
``_frontend_runtime_common``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ..models import (
    BattleResultSubmitRequest,
    FrontendMockPayloadResponse,
    GenerationScheduleQueueTransitionRequest,
    WorldInstanceCreateRequest,
)
from ..services import (
    campaign_router_service,
    frontend_mock_service,
    map_render_plan_service,
    map_runtime_service,
    world_catalog_service,
)
from ..services.frontend_mock_service import FixtureNotFoundError
from ..services.generation_scheduler_service import InvalidQueueTransitionError
from ..services.map_render_plan_service import MapRenderPlanNotFoundError
from ..services.map_runtime_service import MapRuntimePackageNotFoundError
from ._frontend_runtime_common import (
    _fixture_404,
    _map_render_plan_fixture_404,
    _map_runtime_fixture_404,
    _payload,
    _queue_transition_409,
    _require_session,
)

router = APIRouter()


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
    world_id = body.world_id if body is not None else "long_night_lanterns"
    try:
        data = frontend_mock_service.create_world_instance(
            session_id, selected, world_id=world_id
        )
    except world_catalog_service.WorldCatalogNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"world is not ready: {world_id}",
        ) from exc
    return _payload(session_id, data)


@router.get("/api/world-catalog")
def get_world_catalog() -> dict[str, Any]:
    """Return reviewed and compiled worlds that are ready for a new session."""
    return world_catalog_service.get_catalog()


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
    "/api/sessions/{session_id}/runtime-art-kit",
    response_model=FrontendMockPayloadResponse,
)
def get_runtime_art_kit(session_id: str) -> FrontendMockPayloadResponse:
    """Return developer-compiled runtime art for the frontend battle mock."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_runtime_art_kit(session_id))


@router.get(
    "/api/sessions/{session_id}/campaign-router",
    response_model=FrontendMockPayloadResponse,
)
def get_campaign_router(session_id: str) -> FrontendMockPayloadResponse:
    """Return the thin campaign cursor, next node, and prefetch window."""
    _require_session(session_id)
    return _payload(session_id, campaign_router_service.get_campaign_router(session_id))


@router.post(
    "/api/sessions/{session_id}/campaign-router/prefetch-next",
    response_model=FrontendMockPayloadResponse,
)
def prefetch_next_campaign_node(session_id: str) -> FrontendMockPayloadResponse:
    """Ask the fixture-backed scheduler to dry-run one lookahead prefetch step."""
    _require_session(session_id)
    return _payload(session_id, campaign_router_service.prefetch_next(session_id))


@router.post(
    "/api/sessions/{session_id}/campaign-router/prefetch-next-dispatcher-drain",
    response_model=FrontendMockPayloadResponse,
)
def prefetch_next_campaign_node_dispatcher_drain(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Ask the scheduler dispatcher to drain bounded lookahead prefetch work."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = campaign_router_service.prefetch_next_dispatcher_drain(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.get(
    "/api/sessions/{session_id}/runtime/feature-snapshots",
    response_model=FrontendMockPayloadResponse,
)
def get_feature_runtime(
    session_id: str,
    node_id: str | None = None,
) -> FrontendMockPayloadResponse:
    """Return the activated, player-safe FeatureSnapshot runtime projection."""
    _require_session(session_id)
    return _payload(
        session_id,
        frontend_mock_service.get_feature_runtime(session_id, node_id=node_id),
    )


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


@router.get(
    "/api/sessions/{session_id}/battles/{node_id}/map-runtime-package",
    response_model=FrontendMockPayloadResponse,
)
def get_map_runtime_package(session_id: str, node_id: str) -> FrontendMockPayloadResponse:
    """Return the runtime-safe logical map package for a mock battle node."""
    _require_session(session_id)
    try:
        data = map_runtime_service.get_map_runtime_package(session_id, node_id)
    except MapRuntimePackageNotFoundError as exc:
        raise _map_runtime_fixture_404(exc) from exc
    return _payload(session_id, data)


@router.get(
    "/api/sessions/{session_id}/battles/{node_id}/map-render-plan",
    response_model=FrontendMockPayloadResponse,
)
def get_map_render_plan(session_id: str, node_id: str) -> FrontendMockPayloadResponse:
    """Return the reviewed procedural map render plan bundle for a battle node."""
    _require_session(session_id)
    try:
        runtime_selection = map_runtime_service.map_runtime_activation_selection(node_id)
        data = map_render_plan_service.get_map_render_plan_bundle(
            session_id,
            node_id,
            runtime_schema_version=runtime_selection.get("selected_schema_version"),
            runtime_selection=runtime_selection,
        )
    except MapRuntimePackageNotFoundError as exc:
        raise _map_runtime_fixture_404(exc) from exc
    except MapRenderPlanNotFoundError as exc:
        raise _map_render_plan_fixture_404(exc) from exc
    return _payload(session_id, data)


@router.get(
    "/api/sessions/{session_id}/battles/{node_id}/map-v02-preview",
    response_model=FrontendMockPayloadResponse,
)
def get_map_v02_preview(session_id: str, node_id: str) -> FrontendMockPayloadResponse:
    """Return review-only MapRuntimePackage v0.2 and RenderPlan preview data."""
    _require_session(session_id)
    try:
        map_package = map_runtime_service.load_map_runtime_package_v02(node_id)
        render_bundle = map_render_plan_service.load_map_render_plan_bundle_v02(node_id)
    except MapRuntimePackageNotFoundError as exc:
        raise _map_runtime_fixture_404(exc) from exc
    except MapRenderPlanNotFoundError as exc:
        raise _map_render_plan_fixture_404(exc) from exc
    preview_report = render_bundle["procedural_map_preview_report"]
    refs = dict(render_bundle.get("refs") or {})
    return _payload(
        session_id,
        {
            "session_id": session_id,
            "mode": "frontend_mock_fixture",
            "node_id": node_id,
            "preview_mode": "review_only_map_v02",
            "review_only": True,
            "runtime_activation_allowed": False,
            "usage_policy": [
                "review_only",
                "not_player_runtime",
                "not_published_visual_layer",
                "does_not_modify_map_runtime_package",
            ],
            "source_refs": {
                "map_runtime_package_v02": (
                    map_runtime_service.map_runtime_package_v02_ref(node_id)
                ),
                "map_style_pack": refs.get("map_style_pack"),
                "procedural_map_render_plan": refs.get("procedural_map_render_plan"),
                "semantic_visual_consistency_report": refs.get(
                    "semantic_visual_consistency_report"
                ),
                "procedural_map_preview_report": refs.get(
                    "procedural_map_preview_report"
                ),
                "procedural_map_preview_svg": refs.get("procedural_map_preview_svg"),
            },
            "map_runtime_package_v02": map_package,
            "map_render_plan_bundle_v02": render_bundle,
            "preview_report_v02": preview_report,
            "preview_svg_ref": refs.get("procedural_map_preview_svg"),
            "safety": {
                "player_default_runtime_mutation": False,
                "provider_call_count": 0,
                "reads_env": False,
                "review_only_boundary": (
                    "MapRuntimePackage v0.2 preview remains outside player runtime "
                    "until explicit promotion and frontend/backend upgrade gates pass."
                ),
            },
        },
    )


@router.get(
    "/api/sessions/{session_id}/battles/{node_id}/map-v02-opt-in-dry-run",
    response_model=FrontendMockPayloadResponse,
)
def get_map_v02_opt_in_dry_run(
    session_id: str, node_id: str
) -> FrontendMockPayloadResponse:
    """Return the review-only v0.2 opt-in contract without activating it."""
    _require_session(session_id)
    try:
        data = map_runtime_service.get_map_runtime_v02_opt_in_contract(
            session_id, node_id
        )
    except MapRuntimePackageNotFoundError as exc:
        raise _map_runtime_fixture_404(exc) from exc
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
