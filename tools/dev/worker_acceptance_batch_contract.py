#!/usr/bin/env python3
"""Shared contract constants for WorkerTaskPack batch reports."""

from __future__ import annotations

from pathlib import Path

from tools.dev.worker_acceptance_report_contract import (
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_PASSED,
    WORKER_ACCEPTANCE_VALID_STATUSES,
)


WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION = (
    "worker_acceptance_batch_run_report.v0.1"
)
WORKER_ACCEPTANCE_BATCH_DEFAULT_OUTPUT = Path(
    "/tmp/worker_acceptance_batch_run_report.v0.1.json"
)
WORKER_ACCEPTANCE_BATCH_VALID_STATUSES = WORKER_ACCEPTANCE_VALID_STATUSES
