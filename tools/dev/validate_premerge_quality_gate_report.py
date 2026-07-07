#!/usr/bin/env python3
"""Validate pre-merge quality gate reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.premerge_quality_gate_contract import (  # noqa: E402
    COMMAND_DEMO_EVIDENCE_FULL_EXPORT,
    FULL_COMMAND_ORDER,
    FULL_REQUIRED_COMMANDS,
    PREMERGE_COMMAND_ORDER,
    PREMERGE_QUALITY_GATE_PROFILES,
    PREMERGE_QUALITY_GATE_REPORT_ID,
    PREMERGE_QUALITY_GATE_SCHEMA_VERSION,
    PREMERGE_REQUIRED_BOUNDARY_FLAGS,
    PREMERGE_REQUIRED_COMMANDS,
    PREMERGE_REQUIRED_ZERO_FIELDS,
    PROFILE_FULL,
    PROFILE_PREMERGE,
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
    expect_profile: str | None,
    expect_failed_count: int | None,
) -> dict[str, Any]:
    require(
        report.get("schema_version") == PREMERGE_QUALITY_GATE_SCHEMA_VERSION,
        "schema_version mismatch",
    )
    require(report.get("report_id") == PREMERGE_QUALITY_GATE_REPORT_ID, "report_id mismatch")
    status = report.get("status")
    require(status in VALID_STATUSES, f"invalid status: {status!r}")
    if expect_status is not None:
        require(status == expect_status, f"status must be {expect_status!r}")

    profile = report.get("profile")
    require(profile in PREMERGE_QUALITY_GATE_PROFILES, f"invalid profile: {profile!r}")
    if expect_profile is not None:
        require(profile == expect_profile, f"profile must be {expect_profile!r}")

    summary = as_obj(report.get("summary"))
    results = as_list(report.get("results"))
    configured_count = int(summary.get("configured_command_count") or 0)
    executed_count = int(summary.get("executed_command_count") or 0)
    failed_count = int(summary.get("failed_count") or 0)
    passed_count = int(summary.get("passed_count") or 0)
    actual_failed_count = sum(
        1 for item in results if isinstance(item, dict) and item.get("status") != "passed"
    )
    require(executed_count == len(results), "executed_command_count must match results length")
    require(passed_count + failed_count == executed_count, "summary status counts must sum")
    require(failed_count == actual_failed_count, "failed_count must match results")
    if expect_failed_count is not None:
        require(failed_count == expect_failed_count, f"failed_count must be {expect_failed_count}")

    names = command_names(results)
    name_set = set(names)
    fail_fast = bool(summary.get("fail_fast"))
    required = FULL_REQUIRED_COMMANDS if profile == PROFILE_FULL else PREMERGE_REQUIRED_COMMANDS
    if not fail_fast or status == "passed":
        missing = sorted(required.difference(name_set))
        require(not missing, f"missing required command results: {missing}")
    expected_order = FULL_COMMAND_ORDER if profile == PROFILE_FULL else PREMERGE_COMMAND_ORDER
    if fail_fast and status != "passed":
        expected_prefix = expected_order[: len(names)]
        require(
            names == expected_prefix,
            "command order prefix mismatch: expected "
            + json.dumps(expected_prefix, ensure_ascii=False)
            + ", got "
            + json.dumps(names, ensure_ascii=False),
        )
    else:
        require(
            names == expected_order,
            "command order mismatch: expected "
            + json.dumps(expected_order, ensure_ascii=False)
            + ", got "
            + json.dumps(names, ensure_ascii=False),
        )
    if profile == PROFILE_PREMERGE:
        require(
            COMMAND_DEMO_EVIDENCE_FULL_EXPORT not in name_set,
            "premerge profile must not run full evidence export",
        )
        require(
            summary.get("full_evidence_included") is False,
            "premerge profile must mark full_evidence_included=false",
        )
    if profile == PROFILE_FULL:
        require(
            summary.get("full_evidence_included") is True,
            "full profile must mark full_evidence_included=true",
        )
    if not bool(summary.get("fail_fast")):
        require(configured_count == executed_count, "non-fail-fast run must execute every command")

    boundary = as_obj(report.get("boundary"))
    for field in PREMERGE_REQUIRED_BOUNDARY_FLAGS:
        require(boundary.get(field) is True, f"boundary.{field} must be true")
    for field, expected in PREMERGE_REQUIRED_ZERO_FIELDS:
        require(summary.get(field) == expected, f"summary.{field} must be {expected!r}")

    return {
        "status": status,
        "profile": profile,
        "configured_command_count": configured_count,
        "executed_command_count": executed_count,
        "failed_count": failed_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expect-status", choices=sorted(VALID_STATUSES))
    parser.add_argument("--expect-profile", choices=sorted(PREMERGE_QUALITY_GATE_PROFILES))
    parser.add_argument("--expect-failed-count", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = validate_report(
            load_json(args.report),
            expect_status=args.expect_status,
            expect_profile=args.expect_profile,
            expect_failed_count=args.expect_failed_count,
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"premerge quality gate report validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "premerge quality gate report validation passed: "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
