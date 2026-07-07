#!/usr/bin/env python3
"""Shared contract constants for the pre-merge quality gate."""

from __future__ import annotations


PREMERGE_QUALITY_GATE_SCHEMA_VERSION = "premerge_quality_gate_report.v0.1"
PREMERGE_QUALITY_GATE_REPORT_ID = "premerge_quality_gate_report_v0_1"

PROFILE_PREMERGE = "premerge"
PROFILE_FULL = "full"
PREMERGE_QUALITY_GATE_PROFILES = {PROFILE_PREMERGE, PROFILE_FULL}

COMMAND_PYTHON_COMPILE_PREMERGE_TOOLS = "python_compile_premerge_tools"
COMMAND_FAST_QUALITY_GATE = "fast_quality_gate"
COMMAND_FAST_QUALITY_GATE_REPORT_VALIDATOR = "fast_quality_gate_report_validator"
COMMAND_WORKER_ACCEPTANCE_BATCH_ALL_DRY_RUN = "worker_acceptance_batch_all_dry_run"
COMMAND_WORKER_ACCEPTANCE_BATCH_REPORT_VALIDATOR = "worker_acceptance_batch_report_validator"
COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT = "worker_acceptance_profile_audit"
COMMAND_RELEASE_GATE_PROFILE_AUDIT = "release_gate_profile_audit"
COMMAND_WORKER_ACCEPTANCE_PROFILE_MIGRATION_DRY_RUN = (
    "worker_acceptance_profile_migration_dry_run"
)
COMMAND_GIT_DIFF_CHECK = "git_diff_check"
COMMAND_DEMO_EVIDENCE_FULL_EXPORT = "demo_evidence_full_export"

PREMERGE_REQUIRED_COMMANDS = {
    COMMAND_PYTHON_COMPILE_PREMERGE_TOOLS,
    COMMAND_FAST_QUALITY_GATE,
    COMMAND_FAST_QUALITY_GATE_REPORT_VALIDATOR,
    COMMAND_WORKER_ACCEPTANCE_BATCH_ALL_DRY_RUN,
    COMMAND_WORKER_ACCEPTANCE_BATCH_REPORT_VALIDATOR,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
    COMMAND_RELEASE_GATE_PROFILE_AUDIT,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_MIGRATION_DRY_RUN,
    COMMAND_GIT_DIFF_CHECK,
}
FULL_REQUIRED_COMMANDS = PREMERGE_REQUIRED_COMMANDS | {COMMAND_DEMO_EVIDENCE_FULL_EXPORT}

PREMERGE_REQUIRED_BOUNDARY_FLAGS = (
    "no_provider_calls",
    "no_env_file_reads",
    "no_world_state_writes",
    "no_runtime_activation",
    "does_not_replace_demo_evidence_suite",
)
PREMERGE_REQUIRED_ZERO_FIELDS = (
    ("provider_call_count", 0),
    ("reads_env_file", False),
    ("world_mutation_count", 0),
    ("runtime_activation_allowed", False),
)
