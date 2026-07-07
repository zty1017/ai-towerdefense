#!/usr/bin/env python3
"""Validate fast quality gate reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.fast_quality_gate_contract import (  # noqa: E402
    COMMAND_RELEASE_GATE_PROFILE_AUDIT,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
    COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE,
    FAST_QUALITY_GATE_COMMAND_ORDER,
    FAST_QUALITY_GATE_REPORT_ID,
    FAST_QUALITY_GATE_REQUIRED_BOUNDARY_FLAGS,
    FAST_QUALITY_GATE_REQUIRED_ZERO_FIELDS,
    FAST_QUALITY_GATE_SCHEMA_VERSION,
)

VALID_STATUSES = {"passed", "failed"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def command_names(results: list[Any]) -> list[str]:
    names: list[str] = []
    for item in results:
        if isinstance(item, dict):
            names.append(str(item.get("name")))
    return names


def validate_report(
    report: dict[str, Any],
    *,
    expect_status: str | None,
    expect_failed_count: int | None,
    require_worker_env_smoke: bool,
    require_worker_profile_audit: bool,
    require_release_gate_audit: bool,
    require_complete_command_order: bool,
) -> dict[str, Any]:
    require(
        report.get("schema_version") == FAST_QUALITY_GATE_SCHEMA_VERSION,
        "schema_version mismatch",
    )
    require(report.get("report_id") == FAST_QUALITY_GATE_REPORT_ID, "report_id mismatch")
    status = report.get("status")
    require(status in VALID_STATUSES, f"invalid status: {status!r}")
    if expect_status is not None:
        require(status == expect_status, f"status must be {expect_status!r}")

    summary = as_obj(report.get("summary"))
    results = as_list(report.get("results"))
    configured_count = int(summary.get("configured_command_count") or 0)
    command_count = int(summary.get("command_count") or 0)
    failed_count = int(summary.get("failed_count") or 0)
    passed_count = int(summary.get("passed_count") or 0)
    fail_fast = bool(summary.get("fail_fast"))
    actual_failed_count = sum(
        1 for item in results if isinstance(item, dict) and item.get("status") != "passed"
    )
    require(configured_count >= 1, "configured_command_count must be positive")
    require(command_count == len(results), "command_count must match results length")
    require(command_count <= configured_count, "command_count cannot exceed configured count")
    require(passed_count + failed_count == command_count, "summary status counts must sum")
    require(failed_count == actual_failed_count, "failed_count must match results")
    require((status == "passed") == (failed_count == 0), "status must match failed_count")
    if expect_failed_count is not None:
        require(failed_count == expect_failed_count, f"failed_count must be {expect_failed_count}")
    if not fail_fast:
        require(configured_count == command_count, "non-fail-fast run must execute every command")

    boundary = as_obj(report.get("boundary"))
    for field in FAST_QUALITY_GATE_REQUIRED_BOUNDARY_FLAGS:
        require(boundary.get(field) is True, f"boundary.{field} must be true")
    for field, expected in FAST_QUALITY_GATE_REQUIRED_ZERO_FIELDS:
        require(summary.get(field) == expected, f"summary.{field} must be {expected!r}")

    names = command_names(results)
    name_set = set(names)
    if require_complete_command_order or status == "passed":
        require(
            names == FAST_QUALITY_GATE_COMMAND_ORDER,
            "command order mismatch: expected "
            + json.dumps(FAST_QUALITY_GATE_COMMAND_ORDER, ensure_ascii=False)
            + ", got "
            + json.dumps(names, ensure_ascii=False),
        )
    if require_worker_env_smoke:
        require(
            COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE in name_set,
            f"missing {COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE}",
        )
        worker_smoke = next(
            item
            for item in results
            if isinstance(item, dict)
            and item.get("name") == COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE
        )
        require(worker_smoke.get("status") == "passed", "worker env smoke must pass")
    if require_worker_profile_audit:
        require(
            COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT in name_set,
            f"missing {COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT}",
        )
        worker_audit = next(
            item
            for item in results
            if isinstance(item, dict)
            and item.get("name") == COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT
        )
        require(worker_audit.get("status") == "passed", "worker acceptance profile audit must pass")
    if require_release_gate_audit:
        require(
            COMMAND_RELEASE_GATE_PROFILE_AUDIT in name_set,
            f"missing {COMMAND_RELEASE_GATE_PROFILE_AUDIT}",
        )
        release_audit = next(
            item
            for item in results
            if isinstance(item, dict) and item.get("name") == COMMAND_RELEASE_GATE_PROFILE_AUDIT
        )
        require(release_audit.get("status") == "passed", "release gate audit must pass")

    return {
        "status": status,
        "configured_command_count": configured_count,
        "command_count": command_count,
        "failed_count": failed_count,
        "fail_fast": fail_fast,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expect-status", choices=sorted(VALID_STATUSES))
    parser.add_argument("--expect-failed-count", type=int)
    parser.add_argument("--require-worker-env-smoke", action="store_true")
    parser.add_argument("--require-worker-profile-audit", action="store_true")
    parser.add_argument("--require-release-gate-audit", action="store_true")
    parser.add_argument(
        "--require-complete-command-order",
        action="store_true",
        help="Require the current full fast gate command order even for failed reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = validate_report(
            load_json(args.report),
            expect_status=args.expect_status,
            expect_failed_count=args.expect_failed_count,
            require_worker_env_smoke=args.require_worker_env_smoke,
            require_worker_profile_audit=args.require_worker_profile_audit,
            require_release_gate_audit=args.require_release_gate_audit,
            require_complete_command_order=args.require_complete_command_order,
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"fast quality gate report validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "fast quality gate report validation passed: "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
