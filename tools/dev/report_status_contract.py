#!/usr/bin/env python3
"""Shared status constants for local dev reports."""

from __future__ import annotations


STATUS_PASSED = "passed"
STATUS_DRY_RUN = "dry_run"
STATUS_FAILED = "failed"
REPORT_VALID_STATUSES = frozenset(
    {
        STATUS_PASSED,
        STATUS_DRY_RUN,
        STATUS_FAILED,
    }
)
