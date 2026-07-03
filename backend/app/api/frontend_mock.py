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
    GenerationScheduleQueueTransitionRequest,
    WorldInstanceCreateRequest,
)
from ..services import (
    campaign_router_service,
    frontend_mock_service,
    generation_scheduler_service,
    map_runtime_service,
)
from ..services.generation_scheduler_service import (
    GenerationSchedulerFixtureNotFoundError,
    InvalidQueueTransitionError,
)
from ..services.map_runtime_service import MapRuntimePackageNotFoundError
from ..services.frontend_mock_service import (
    FixtureNotFoundError,
)

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


def _queue_transition_409(exc: InvalidQueueTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
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
    "/api/sessions/{session_id}/runtime-art-kit",
    response_model=FrontendMockPayloadResponse,
)
def get_runtime_art_kit(session_id: str) -> FrontendMockPayloadResponse:
    """Return developer-compiled runtime art for the frontend battle mock."""
    _require_session(session_id)
    return _payload(session_id, frontend_mock_service.get_runtime_art_kit(session_id))


@router.get(
    "/api/sessions/{session_id}/generation-schedule",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_schedule(session_id: str) -> FrontendMockPayloadResponse:
    """Return the fixture-backed generation scheduler buffer for this session."""
    _require_session(session_id)
    return _payload(session_id, generation_scheduler_service.get_generation_schedule(session_id))


@router.post(
    "/api/sessions/{session_id}/generation-schedule/runs",
    response_model=FrontendMockPayloadResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_generation_schedule_run(session_id: str) -> FrontendMockPayloadResponse:
    """Persist a fixture-backed dry-run generation scheduler execution."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.create_generation_schedule_run(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/runs/latest",
    response_model=FrontendMockPayloadResponse,
)
def get_latest_generation_schedule_run(session_id: str) -> FrontendMockPayloadResponse:
    """Return the latest persisted scheduler dry-run for this session."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_latest_generation_schedule_run(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/queue",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_schedule_queue(session_id: str) -> FrontendMockPayloadResponse:
    """Return queue items derived from the latest persisted scheduler run."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_schedule_queue(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/worker-cache",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_schedule_worker_cache(session_id: str) -> FrontendMockPayloadResponse:
    """Return review-only worker cache records derived from scheduler worker steps."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_schedule_worker_cache(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/artifact-ledger",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_artifact_ledger(session_id: str) -> FrontendMockPayloadResponse:
    """Return review-only provider artifact ledger records for this session."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_artifact_ledger(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/prefetch-cache",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_prefetch_cache(session_id: str) -> FrontendMockPayloadResponse:
    """Return a read-only prefetch cache view derived from queue and ledger rows."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_prefetch_cache(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/activation-gate",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_activation_gate(session_id: str) -> FrontendMockPayloadResponse:
    """Return the read-only activation gate view for generated candidates."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_activation_gate(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/shared-prefetch-cache",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_shared_prefetch_cache(
    session_id: str,
) -> FrontendMockPayloadResponse:
    """Return the cross-session shared prefetch cache index."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_shared_prefetch_cache(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/generation-schedule/shared-prefetch-cache/hits",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_shared_prefetch_cache_hits(
    session_id: str,
) -> FrontendMockPayloadResponse:
    """Return current-run hits against the shared prefetch cache."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_shared_prefetch_cache_hits(
            session_id
        ),
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/index-shared-prefetch-cache",
    response_model=FrontendMockPayloadResponse,
)
def index_generation_shared_prefetch_cache(
    session_id: str,
) -> FrontendMockPayloadResponse:
    """Index promotion-allowed candidates into the shared prefetch cache."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.index_generation_shared_prefetch_cache(session_id),
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/record-shared-prefetch-cache-reuse-candidate",
    response_model=FrontendMockPayloadResponse,
)
def record_generation_shared_prefetch_cache_reuse_candidate(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record a current-run shared-cache hit as a review-only reuse candidate."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.record_shared_prefetch_cache_reuse_candidate(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


def _transition_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    transition: str,
    body: GenerationScheduleQueueTransitionRequest | None,
) -> FrontendMockPayloadResponse:
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.transition_generation_schedule_queue_item(
            session_id,
            schedule_item_id,
            transition,
            metadata,
        )
    except GenerationSchedulerFixtureNotFoundError as exc:
        raise _scheduler_fixture_404(exc) from exc
    except InvalidQueueTransitionError as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/claim",
    response_model=FrontendMockPayloadResponse,
)
def claim_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Claim a queued scheduler item for a future worker."""
    return _transition_generation_schedule_queue_item(
        session_id,
        schedule_item_id,
        "claim",
        body,
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/complete",
    response_model=FrontendMockPayloadResponse,
)
def complete_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Mark a claimed or queued scheduler item as completed."""
    return _transition_generation_schedule_queue_item(
        session_id,
        schedule_item_id,
        "complete",
        body,
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fail",
    response_model=FrontendMockPayloadResponse,
)
def fail_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Mark a claimed or queued scheduler item as failed."""
    return _transition_generation_schedule_queue_item(
        session_id,
        schedule_item_id,
        "fail",
        body,
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/retry",
    response_model=FrontendMockPayloadResponse,
)
def retry_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Requeue a failed scheduler item if its retry budget allows it."""
    return _transition_generation_schedule_queue_item(
        session_id,
        schedule_item_id,
        "retry",
        body,
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fallback",
    response_model=FrontendMockPayloadResponse,
)
def fallback_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Select the static fallback for a failed or review-blocked scheduler item."""
    return _transition_generation_schedule_queue_item(
        session_id,
        schedule_item_id,
        "fallback",
        body,
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/dry-run-step",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_dry_worker_step(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Process one queued scheduler item without provider calls or world writes."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    return _payload(
        session_id,
        generation_scheduler_service.run_generation_schedule_dry_worker_step(
            session_id,
            metadata,
        ),
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/live-executor-guard",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_live_executor_guard(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record a blocked live-executor intent without provider calls or world writes."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    return _payload(
        session_id,
        generation_scheduler_service.run_generation_schedule_live_executor_guard(
            session_id,
            metadata,
        ),
    )


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/prepare-executor-request",
    response_model=FrontendMockPayloadResponse,
)
def prepare_generation_executor_run_request(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Prepare a guarded, review-only executor request without provider calls."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.prepare_generation_executor_run_request(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/grant-provider-authorization",
    response_model=FrontendMockPayloadResponse,
)
def grant_provider_execution_authorization(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record explicit provider execution authorization without provider calls."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.grant_provider_execution_authorization(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-fixture",
    response_model=FrontendMockPayloadResponse,
)
def run_provider_adapter_fixture(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record a fixture-backed provider adapter receipt without provider calls."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_provider_adapter_fixture(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-runner-fixture",
    response_model=FrontendMockPayloadResponse,
)
def run_provider_adapter_runner_fixture(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record provider adapter runner dry-run artifacts without live provider calls."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_provider_adapter_runner_fixture(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/export-provider-adapter-runner-handoff",
    response_model=FrontendMockPayloadResponse,
)
def export_provider_adapter_runner_handoff(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Export a read-only handoff bundle for an external provider adapter runner."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.export_provider_adapter_runner_handoff(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-step",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_review_only_dispatcher_step(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Dispatch one queued item through the review-only runner boundary."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_review_only_dispatcher_step(
            session_id,
            metadata,
        )
    except GenerationSchedulerFixtureNotFoundError as exc:
        raise _scheduler_fixture_404(exc) from exc
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-drain",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_review_only_dispatcher_drain(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Dispatch several queued review-only items through the runner boundary."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_review_only_dispatcher_drain(
            session_id,
            metadata,
        )
    except GenerationSchedulerFixtureNotFoundError as exc:
        raise _scheduler_fixture_404(exc) from exc
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-executor-tick",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_review_only_background_executor_tick(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Run one bounded review-only background executor tick."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_review_only_background_executor_tick(
            session_id,
            metadata,
        )
    except GenerationSchedulerFixtureNotFoundError as exc:
        raise _scheduler_fixture_404(exc) from exc
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-handoff-tick",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_review_only_background_handoff_tick(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Run one background tick and export external runner handoffs."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_review_only_background_handoff_tick(
            session_id,
            metadata,
        )
    except GenerationSchedulerFixtureNotFoundError as exc:
        raise _scheduler_fixture_404(exc) from exc
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/import-provider-adapter-runner-output",
    response_model=FrontendMockPayloadResponse,
)
def import_provider_adapter_runner_output(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Validate and import local runner receipt/envelope files into the ledger."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.import_provider_adapter_runner_outputs(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/import-provider-artifact-review-output",
    response_model=FrontendMockPayloadResponse,
)
def import_provider_artifact_review_output(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Validate and import local staging/promotion review files into the ledger."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.import_provider_artifact_review_outputs(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/stage-provider-artifacts",
    response_model=FrontendMockPayloadResponse,
)
def stage_generation_schedule_provider_artifacts(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record reviewed provider artifact fixtures without provider calls or activation."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.stage_provider_artifacts_fixture(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-fixture-executor-chain",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_schedule_fixture_executor_chain(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Run the guarded fixture executor chain without provider calls or activation."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_fixture_executor_chain(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _payload(session_id, data)


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
