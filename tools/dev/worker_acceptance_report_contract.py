#!/usr/bin/env python3
"""Shared status constants for WorkerTaskPack acceptance reports."""

from __future__ import annotations


STATUS_PASSED = "passed"
STATUS_DRY_RUN = "dry_run"
STATUS_FAILED = "failed"
WORKER_ACCEPTANCE_VALID_STATUSES = frozenset(
    {
        STATUS_PASSED,
        STATUS_DRY_RUN,
        STATUS_FAILED,
    }
)
