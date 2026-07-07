#!/usr/bin/env python3
"""Shared contract constants for WorkerTaskPack profile reports."""

from __future__ import annotations

from pathlib import Path

from tools.dev.worker_acceptance_report_contract import (
    WORKER_ACCEPTANCE_VALID_STATUSES,
)


WORKER_ACCEPTANCE_PROFILE_REPORT_SCHEMA_VERSION = (
    "worker_acceptance_profile_run_report.v0.1"
)
WORKER_ACCEPTANCE_PROFILE_DEFAULT_OUTPUT = Path(
    "/tmp/worker_acceptance_profile_run_report.v0.1.json"
)
WORKER_ACCEPTANCE_PROFILE_VALID_STATUSES = WORKER_ACCEPTANCE_VALID_STATUSES
