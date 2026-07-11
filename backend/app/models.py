"""Pydantic v2 models for session API responses and request bodies."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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


# ---------------------------------------------------------------------------
# Research job / proposal models
# ---------------------------------------------------------------------------

# Status values a research job may hold over its lifecycle. MVP runs
# synchronously to "completed" but the field is reserved for future async
# workers.
JOB_STATUSES = ("queued", "running", "completed", "failed", "delayed", "unstable")


class ResearchProposalRequest(BaseModel):
    """Body for POST /api/sessions/{session_id}/research/proposals."""

    intent_text: str = Field(
        ..., description="Player-authored description of the desired asset behavior."
    )
    node_id: str = Field(
        ..., description="World node the proposal targets (e.g. gray_lantern_station)."
    )


class ResearchProposalResponse(BaseModel):
    proposal_id: str
    session_id: str
    node_id: str
    display_name: str
    summary: str
    risk_note: str
    player_state_message: str
    compiler_metadata: dict[str, Any] = Field(default_factory=dict)
    compiled_candidate: Optional[dict[str, Any]] = None


class ResearchJobResponse(BaseModel):
    """Shared shape for confirm and get-job responses."""

    job_id: str
    session_id: str
    proposal_id: str
    status: str
    player_state_message: str
    runtime_package_path: Optional[str] = None
    delivery_payload_path: Optional[str] = None
    trace_paths: list[str] = Field(default_factory=list)
    compiler_metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchJobInfo(ResearchJobResponse):
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class RuntimeActivationResponse(BaseModel):
    """Result of applying or rolling back one session runtime patch."""

    activation_receipt: dict[str, Any]
    activated_runtime_bundle: dict[str, Any]


class RuntimeActivationListResponse(BaseModel):
    session_id: str
    activation_receipts: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontend mock API models
# ---------------------------------------------------------------------------


class WorldInstanceCreateRequest(BaseModel):
    """Optional world-instance selections from the frontend start flow."""

    selected_options: dict[str, Any] = Field(default_factory=dict)
    world_id: str = Field(default="long_night_lanterns", min_length=1, max_length=64)


class FrontendMockPayloadResponse(BaseModel):
    """Generic fixture-backed response for the frontend mock API surface."""

    session_id: str
    mode: str = "frontend_mock_fixture"
    payload: dict[str, Any]


class BattleResultSubmitRequest(BaseModel):
    """Player/battle simulation result posted by the frontend mock battle."""

    result: str = Field(default="victory")
    protected_core_hp: Optional[int] = None
    optional_target_state: Optional[str] = None
    deployed_asset_ids: list[str] = Field(default_factory=list)
    leaked_enemy_count: int = 0
    notes: Optional[str] = None


class GenerationScheduleQueueTransitionRequest(BaseModel):
    """Optional metadata for fixture-backed scheduler queue transitions."""

    worker_id: Optional[str] = Field(default=None)
    note: Optional[str] = Field(default=None)
    schedule_item_id: Optional[str] = Field(
        default=None,
        description="Optional scheduler queue item to target for worker actions.",
    )
    max_items: Optional[int] = Field(
        default=None,
        ge=1,
        le=16,
        description="Optional maximum number of queue items for bounded worker drains.",
    )
    artifact_profile: Optional[str] = Field(
        default=None,
        description="Optional provider artifact fixture profile for staging workers.",
    )
    authorization_ref: Optional[str] = Field(
        default=None,
        description="Optional explicit provider authorization reference.",
    )
    receipt_path: Optional[str] = Field(
        default=None,
        description="Optional local ProviderAdapterExecutionReceipt JSON path.",
    )
    envelope_path: Optional[str] = Field(
        default=None,
        description="Optional local ProviderOutputEnvelope JSON path.",
    )
    staging_path: Optional[str] = Field(
        default=None,
        description="Optional local ProviderArtifactStagingManifest JSON path.",
    )
    promotion_report_path: Optional[str] = Field(
        default=None,
        description="Optional local ProviderArtifactPromotionReport JSON path.",
    )
    activation_decision: Optional[str] = Field(
        default=None,
        description=(
            "Optional review-only runtime activation decision for activation "
            "authorization workers."
        ),
    )
