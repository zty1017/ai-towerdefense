"""Generation scheduler routes for the MVP playable flow.

All routes in this module are scoped under ``/api/sessions/{session_id}/generation-schedule``
and delegate to ``generation_scheduler_service``. The private
``_transition_generation_schedule_queue_item`` helper is migrated here alongside
its queue routes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..models import FrontendMockPayloadResponse, GenerationScheduleQueueTransitionRequest
from ..services import frontend_mock_service, generation_scheduler_service
from ..services.generation_scheduler_service import (
    GenerationSchedulerFixtureNotFoundError,
    InvalidQueueTransitionError,
)
from ._frontend_runtime_common import (
    _payload,
    _queue_transition_409,
    _require_session,
    _scheduler_fixture_404,
)

router = APIRouter()


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
    "/api/sessions/{session_id}/generation-schedule/daemon-readiness",
    response_model=FrontendMockPayloadResponse,
)
def get_generation_daemon_readiness(session_id: str) -> FrontendMockPayloadResponse:
    """Return the safe readiness view for future background executor daemons."""
    _require_session(session_id)
    return _payload(
        session_id,
        generation_scheduler_service.get_generation_daemon_readiness(session_id),
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


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/prepare-runtime-build-request",
    response_model=FrontendMockPayloadResponse,
)
def prepare_generation_runtime_build_request(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record a review-only request for a future runtime/world-delta builder."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.prepare_generation_runtime_build_request(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-runtime-artifact-build-report",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_runtime_artifact_build_report(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record review-only resolved runtime artifact targets for a build request."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_generation_runtime_artifact_build_report(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/record-runtime-activation-authorization",
    response_model=FrontendMockPayloadResponse,
)
def record_generation_runtime_activation_authorization(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Record review-only explicit authorization before any runtime activation."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = (
            generation_scheduler_service
            .record_generation_runtime_activation_authorization(
                session_id,
                metadata,
            )
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/apply-runtime-activation",
    response_model=FrontendMockPayloadResponse,
)
def apply_generation_runtime_activation(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Apply one explicitly authorized scheduler runtime package."""

    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.apply_generation_runtime_activation(
            session_id,
            metadata,
        )
    except (InvalidQueueTransitionError, ValueError) as exc:
        raise _queue_transition_409(exc) from exc
    feature_runtime = frontend_mock_service.get_feature_runtime(session_id)
    data["activated_runtime_bundle"] = feature_runtime["activated_runtime_bundle"]
    return _payload(session_id, data)


@router.post(
    "/api/sessions/{session_id}/generation-schedule/workers/run-runtime-activation-readiness-chain",
    response_model=FrontendMockPayloadResponse,
)
def run_generation_runtime_activation_readiness_chain(
    session_id: str,
    body: GenerationScheduleQueueTransitionRequest | None = None,
) -> FrontendMockPayloadResponse:
    """Run the bounded review-only runtime readiness chain for one item."""
    _require_session(session_id)
    metadata = body.model_dump() if body is not None else {}
    try:
        data = generation_scheduler_service.run_generation_runtime_activation_readiness_chain(
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
