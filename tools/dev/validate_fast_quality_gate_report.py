#!/usr/bin/env python3
"""Validate fast quality gate reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "fast_quality_gate_report.v0.1"
VALID_STATUSES = {"passed", "failed"}
EXPECTED_COMMAND_ORDER = [
    "python_compile_core_tools",
    "frontend_app_syntax",
    "battle_visual_contract",
    "battle_interaction_contract",
    "campaign_router_frontend_contract",
    "map_component_frontend_contract",
    "map_decoration_zone_policy_validator",
    "worker_profile_env_assignment_smoke",
    "release_gate_profile_audit",
    "mvp_demo_readiness_build",
    "mvp_demo_readiness_validator_repo_fixture",
    "mvp_demo_readiness_validator_rebuilt_report",
]
REQUIRED_BOUNDARY_FLAGS = (
    "no_browser_automation",
    "no_provider_calls",
    "no_env_file_reads",
    "no_world_state_writes",
    "no_runtime_activation",
    "does_not_replace_full_demo_evidence_export",
)
REQUIRED_ZERO_FIELDS = (
    ("provider_call_count", 0),
    ("reads_env_file", False),
    ("world_mutation_count", 0),
    ("runtime_activation_allowed", False),
)


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
    require_release_gate_audit: bool,
    require_complete_command_order: bool,
) -> dict[str, Any]:
    require(report.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch")
    require(report.get("report_id") == "fast_quality_gate_report_v0_1", "report_id mismatch")
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
    for field in REQUIRED_BOUNDARY_FLAGS:
        require(boundary.get(field) is True, f"boundary.{field} must be true")
    for field, expected in REQUIRED_ZERO_FIELDS:
        require(summary.get(field) == expected, f"summary.{field} must be {expected!r}")

    names = command_names(results)
    name_set = set(names)
    if require_complete_command_order or status == "passed":
        require(
            names == EXPECTED_COMMAND_ORDER,
            "command order mismatch: expected "
            + json.dumps(EXPECTED_COMMAND_ORDER, ensure_ascii=False)
            + ", got "
            + json.dumps(names, ensure_ascii=False),
        )
    if require_worker_env_smoke:
        require(
            "worker_profile_env_assignment_smoke" in name_set,
            "missing worker_profile_env_assignment_smoke",
        )
        worker_smoke = next(
            item
            for item in results
            if isinstance(item, dict) and item.get("name") == "worker_profile_env_assignment_smoke"
        )
        require(worker_smoke.get("status") == "passed", "worker env smoke must pass")
    if require_release_gate_audit:
        require("release_gate_profile_audit" in name_set, "missing release_gate_profile_audit")
        release_audit = next(
            item
            for item in results
            if isinstance(item, dict) and item.get("name") == "release_gate_profile_audit"
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
