#!/usr/bin/env python3
"""Shared contract constants for WorkerTaskPack batch reports."""

from __future__ import annotations

from pathlib import Path


WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION = (
    "worker_acceptance_batch_run_report.v0.1"
)
WORKER_ACCEPTANCE_BATCH_DEFAULT_OUTPUT = Path(
    "/tmp/worker_acceptance_batch_run_report.v0.1.json"
)

STATUS_PASSED = "passed"
STATUS_DRY_RUN = "dry_run"
STATUS_FAILED = "failed"
WORKER_ACCEPTANCE_BATCH_VALID_STATUSES = {
    STATUS_PASSED,
    STATUS_DRY_RUN,
    STATUS_FAILED,
}
