"""Research job API routes.

Exposes three endpoints scoped under a session:

- POST   /api/sessions/{session_id}/research/proposals
- POST   /api/sessions/{session_id}/research/proposals/{proposal_id}/confirm
- GET    /api/sessions/{session_id}/research/jobs/{job_id}

Player-facing responses never carry provider/trace/schema vocabulary; internal
errors are stored on the job row's payload, not echoed to the player.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..db import db_cursor
from ..models import (
    ResearchJobInfo,
    ResearchJobResponse,
    ResearchProposalRequest,
    ResearchProposalResponse,
    RuntimeActivationListResponse,
    RuntimeActivationResponse,
)
from ..services import frontend_mock_service, research_service, runtime_activation_service

router = APIRouter()


def _require_session(session_id: str) -> None:
    """Raise 404 if the session does not exist."""
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


@router.post(
    "/api/sessions/{session_id}/research/proposals",
    response_model=ResearchProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_proposal(
    session_id: str, body: ResearchProposalRequest
) -> ResearchProposalResponse:
    """Create a deterministic research proposal for this session."""
    _require_session(session_id)
    row = research_service.create_proposal(
        session_id, body.intent_text, body.node_id
    )
    return ResearchProposalResponse(**row)


@router.post(
    "/api/sessions/{session_id}/research/proposals/{proposal_id}/confirm",
    response_model=ResearchJobResponse,
)
def confirm_proposal(session_id: str, proposal_id: str) -> ResearchJobResponse:
    """Confirm a proposal and synchronously run the AssetGraph workflows."""
    _require_session(session_id)
    result = research_service.confirm_proposal(session_id, proposal_id)
    if isinstance(result, dict) and result.get("error") == "session_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session not found: {session_id}",
        )
    if isinstance(result, dict) and result.get("error") == "proposal_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"proposal not found: {proposal_id}",
        )
    return ResearchJobResponse(**result)


@router.get(
    "/api/sessions/{session_id}/research/jobs/{job_id}",
    response_model=ResearchJobInfo,
)
def get_job(session_id: str, job_id: str) -> ResearchJobInfo:
    """Return a research job's public representation, or 404."""
    _require_session(session_id)
    job = research_service.get_job(session_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job not found: {job_id}",
        )
    return ResearchJobInfo(**job)


def _runtime_bundle(session_id: str) -> dict:
    return frontend_mock_service.get_feature_runtime(session_id)[
        "activated_runtime_bundle"
    ]


@router.post(
    "/api/sessions/{session_id}/research/jobs/{job_id}/activate",
    response_model=RuntimeActivationResponse,
)
def activate_research_job(
    session_id: str, job_id: str
) -> RuntimeActivationResponse:
    """Apply one validated compiled package to this anonymous session."""
    _require_session(session_id)
    try:
        receipt = runtime_activation_service.activate_research_job(session_id, job_id)
    except runtime_activation_service.RuntimeActivationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"research job not found: {job_id}",
        ) from exc
    except runtime_activation_service.RuntimeActivationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return RuntimeActivationResponse(
        activation_receipt=receipt,
        activated_runtime_bundle=_runtime_bundle(session_id),
    )


@router.get(
    "/api/sessions/{session_id}/runtime/activations",
    response_model=RuntimeActivationListResponse,
)
def list_runtime_activations(session_id: str) -> RuntimeActivationListResponse:
    """List auditable activation receipts for this session."""
    _require_session(session_id)
    return RuntimeActivationListResponse(
        session_id=session_id,
        activation_receipts=runtime_activation_service.list_activation_receipts(
            session_id
        ),
    )


@router.post(
    "/api/sessions/{session_id}/runtime/activations/{activation_id}/rollback",
    response_model=RuntimeActivationResponse,
)
def rollback_runtime_activation(
    session_id: str, activation_id: str
) -> RuntimeActivationResponse:
    """Remove one activated patch while preserving its audit receipt."""
    _require_session(session_id)
    try:
        receipt = runtime_activation_service.rollback_activation(
            session_id, activation_id
        )
    except runtime_activation_service.RuntimeActivationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"runtime activation not found: {activation_id}",
        ) from exc
    except runtime_activation_service.RuntimeActivationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return RuntimeActivationResponse(
        activation_receipt=receipt,
        activated_runtime_bundle=_runtime_bundle(session_id),
    )
