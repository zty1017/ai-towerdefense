#!/usr/bin/env python3
"""Shared contract constants for WorkerTaskPack profile reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.dev.worker_acceptance_report_contract import (
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_PASSED,
    WORKER_ACCEPTANCE_VALID_STATUSES,
)


WORKER_ACCEPTANCE_PROFILE_REPORT_SCHEMA_VERSION = (
    "worker_acceptance_profile_run_report.v0.1"
)
WORKER_ACCEPTANCE_PROFILE_DEFAULT_OUTPUT = Path(
    "/tmp/worker_acceptance_profile_run_report.v0.1.json"
)
WORKER_ACCEPTANCE_PROFILE_VALID_STATUSES = WORKER_ACCEPTANCE_VALID_STATUSES


def profile_result_status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass": sum(1 for item in results if item.get("status") == STATUS_PASSED),
        "fail": sum(1 for item in results if item.get("status") == STATUS_FAILED),
        "dry_run": sum(
            1 for item in results if item.get("status") == STATUS_DRY_RUN
        ),
    }


def summarize_profile_results(
    results: list[dict[str, Any]],
    *,
    fail_fast: bool,
    configured_command_count: int | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "command_count": len(results),
        **profile_result_status_counts(results),
        "fail_fast": bool(fail_fast),
    }
    if configured_command_count is not None:
        summary["configured_command_count"] = int(configured_command_count)
    return summary


def profile_status_from_summary(summary: dict[str, Any], *, dry_run: bool) -> str:
    failed_count = int(summary.get("fail") or 0)
    if failed_count:
        return STATUS_FAILED
    return STATUS_DRY_RUN if dry_run else STATUS_PASSED
