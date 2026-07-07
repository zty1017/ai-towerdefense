#!/usr/bin/env python3
"""Small shared helpers for local quality gate reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tools.dev.report_status_contract import STATUS_FAILED, STATUS_PASSED


def collect_command_failures(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in results if item.get("status") != STATUS_PASSED]


def report_status_from_failures(failed: list[dict[str, Any]]) -> str:
    return STATUS_FAILED if failed else STATUS_PASSED


def summarize_command_results(
    *,
    results: list[dict[str, Any]],
    configured_count: int,
    fail_fast: bool,
    configured_count_field: str,
    executed_count_field: str,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed = collect_command_failures(results)
    summary: dict[str, Any] = {
        configured_count_field: configured_count,
        executed_count_field: len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "fail_fast": bool(fail_fast),
    }
    if extra_fields:
        summary.update(extra_fields)
    return summary


def print_failed_command_details(failed: list[dict[str, Any]]) -> None:
    for item in failed:
        print(f"failed: {item['name']}", file=sys.stderr)
        if item.get("stderr_tail"):
            print(item["stderr_tail"], file=sys.stderr)


def write_json_report(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
