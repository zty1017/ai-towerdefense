#!/usr/bin/env python3
"""Shared contract constants for WorkerTaskPack batch reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def pack_status_counts(pack_results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed_pack_count": sum(
            1 for item in pack_results if item.get("status") == STATUS_PASSED
        ),
        "failed_pack_count": sum(
            1 for item in pack_results if item.get("status") == STATUS_FAILED
        ),
        "dry_run_pack_count": sum(
            1 for item in pack_results if item.get("status") == STATUS_DRY_RUN
        ),
    }


def summarize_batch_packs(
    pack_results: list[dict[str, Any]],
    *,
    selected_pack_count: int,
) -> dict[str, int]:
    summary = {
        "selected_pack_count": int(selected_pack_count),
        "executed_pack_count": len(pack_results),
        **pack_status_counts(pack_results),
        "configured_command_count": sum(
            int(item.get("summary", {}).get("configured_command_count") or 0)
            for item in pack_results
            if isinstance(item.get("summary"), dict)
        ),
        "command_result_count": sum(
            int(item.get("summary", {}).get("command_count") or 0)
            for item in pack_results
            if isinstance(item.get("summary"), dict)
        ),
    }
    return summary


def batch_status_from_summary(summary: dict[str, Any], *, dry_run: bool) -> str:
    failed_count = int(summary.get("failed_pack_count") or 0)
    if failed_count:
        return STATUS_FAILED
    return STATUS_DRY_RUN if dry_run else STATUS_PASSED
