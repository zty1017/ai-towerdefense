#!/usr/bin/env python3
"""Shared contract constants for the fast quality gate."""

from __future__ import annotations


FAST_QUALITY_GATE_SCHEMA_VERSION = "fast_quality_gate_report.v0.1"
FAST_QUALITY_GATE_REPORT_ID = "fast_quality_gate_report_v0_1"

COMMAND_PYTHON_COMPILE_CORE_TOOLS = "python_compile_core_tools"
COMMAND_FRONTEND_APP_SYNTAX = "frontend_app_syntax"
COMMAND_BATTLE_VISUAL_CONTRACT = "battle_visual_contract"
COMMAND_BATTLE_INTERACTION_CONTRACT = "battle_interaction_contract"
COMMAND_CAMPAIGN_ROUTER_FRONTEND_CONTRACT = "campaign_router_frontend_contract"
COMMAND_MAP_COMPONENT_FRONTEND_CONTRACT = "map_component_frontend_contract"
COMMAND_MAP_DECORATION_ZONE_POLICY_VALIDATOR = "map_decoration_zone_policy_validator"
COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE = "worker_profile_env_assignment_smoke"
COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT = "worker_acceptance_profile_audit"
COMMAND_RELEASE_GATE_PROFILE_AUDIT = "release_gate_profile_audit"
COMMAND_MVP_DEMO_READINESS_BUILD = "mvp_demo_readiness_build"
COMMAND_MVP_DEMO_READINESS_VALIDATOR_REPO_FIXTURE = "mvp_demo_readiness_validator_repo_fixture"
COMMAND_MVP_DEMO_READINESS_VALIDATOR_REBUILT_REPORT = (
    "mvp_demo_readiness_validator_rebuilt_report"
)

FAST_QUALITY_GATE_COMMAND_ORDER = [
    COMMAND_PYTHON_COMPILE_CORE_TOOLS,
    COMMAND_FRONTEND_APP_SYNTAX,
    COMMAND_BATTLE_VISUAL_CONTRACT,
    COMMAND_BATTLE_INTERACTION_CONTRACT,
    COMMAND_CAMPAIGN_ROUTER_FRONTEND_CONTRACT,
    COMMAND_MAP_COMPONENT_FRONTEND_CONTRACT,
    COMMAND_MAP_DECORATION_ZONE_POLICY_VALIDATOR,
    COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
    COMMAND_RELEASE_GATE_PROFILE_AUDIT,
    COMMAND_MVP_DEMO_READINESS_BUILD,
    COMMAND_MVP_DEMO_READINESS_VALIDATOR_REPO_FIXTURE,
    COMMAND_MVP_DEMO_READINESS_VALIDATOR_REBUILT_REPORT,
]

FAST_QUALITY_GATE_REQUIRED_BOUNDARY_FLAGS = (
    "no_browser_automation",
    "no_provider_calls",
    "no_env_file_reads",
    "no_world_state_writes",
    "no_runtime_activation",
    "does_not_replace_full_demo_evidence_export",
)

FAST_QUALITY_GATE_REQUIRED_ZERO_FIELDS = (
    ("provider_call_count", 0),
    ("reads_env_file", False),
    ("world_mutation_count", 0),
    ("runtime_activation_allowed", False),
)
