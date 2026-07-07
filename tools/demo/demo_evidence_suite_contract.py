#!/usr/bin/env python3
"""Shared contract constants for the demo evidence suite."""

from __future__ import annotations


DEMO_EVIDENCE_SUITE_SCHEMA_VERSION = "demo_evidence_suite_report.v0.1"
DEMO_EVIDENCE_SUITE_ID = "mvp_demo_evidence_suite"

REPORT_NAME = "demo_evidence_suite_report.v0.1.json"
BROWSER_PREFLIGHT_REPORT_NAME = "browser_smoke_environment_report.v0.1.json"
FRONTEND_FLOW_REPORT_NAME = "frontend_flow_visual_smoke_report.v0.1.json"
FRONTEND_MULTINODE_REPORT_NAME = "frontend_multinode_visual_smoke_report.v0.1.json"
FRONTEND_BATTLE_DRAG_REPORT_NAME = "battle_drag_interaction_smoke_report.v0.1.json"
SCHEDULER_PIPELINE_REPORT_NAME = (
    "generation_scheduler_review_only_pipeline_smoke_report.v0.1.json"
)
OUTBOX_IMPORT_REPORT_NAME = "provider_runner_handoff_outbox_import_pipeline_report.v0.1.json"

COMMAND_BROWSER_PREFLIGHT = "browser_smoke_environment_preflight"
COMMAND_SCHEDULER_PIPELINE_SMOKE = "generation_scheduler_review_only_pipeline_smoke"
COMMAND_SCHEDULER_PIPELINE_SMOKE_REPORT_VALIDATOR = (
    "generation_scheduler_review_only_pipeline_smoke_report_validator"
)
COMMAND_OUTBOX_IMPORT_SMOKE = "provider_runner_handoff_outbox_import_smoke"
COMMAND_OUTBOX_IMPORT_SMOKE_REPORT_VALIDATOR = (
    "provider_runner_handoff_outbox_import_smoke_report_validator"
)
COMMAND_FRONTEND_FLOW_CAPTURE = "frontend_flow_visual_smoke_capture"
COMMAND_FRONTEND_MULTINODE_CAPTURE = "frontend_multinode_visual_smoke_capture"
COMMAND_FRONTEND_BATTLE_DRAG_CAPTURE = "frontend_battle_drag_interaction_smoke_capture"
COMMAND_FRONTEND_FLOW_VALIDATE = "frontend_flow_visual_smoke_validate"
COMMAND_FRONTEND_MULTINODE_VALIDATE = "frontend_multinode_visual_smoke_validate"
COMMAND_FRONTEND_BATTLE_DRAG_VALIDATE = "frontend_battle_drag_interaction_smoke_validate"
COMMAND_DEMO_EVIDENCE_EXPORT = "demo_evidence_export"
