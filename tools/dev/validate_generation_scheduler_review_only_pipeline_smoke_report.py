#!/usr/bin/env python3
"""Validate Generation Scheduler review-only pipeline smoke reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA_VERSION = (
    "generation_scheduler_review_only_pipeline_smoke_report.v0.1"
)
EXPECTED_REPORT_ID = "generation_scheduler_review_only_pipeline_smoke_report_v0_1"
VALID_STATUSES = {"passed"}
FORBIDDEN_KEYS = {
    "raw_prompt",
    "provider_response",
    "provider_body",
    "api_key",
    "secret",
}
REQUIRED_RUNTIME_LEDGER_COUNTS = {
    "generation_runtime_build_request": 1,
    "generation_runtime_artifact_build_report": 1,
    "generation_runtime_activation_authorization": 1,
}
REQUIRED_SESSION_FLAGS = (
    "handoff_session_id_present",
    "fixture_session_id_present",
    "image_failure_session_id_present",
    "runtime_readiness_session_id_present",
    "target_session_id_present",
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


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(walk_keys(item))
    return keys


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    require(
        report.get("schema_version") == EXPECTED_SCHEMA_VERSION,
        f"schema_version is {report.get('schema_version')!r}",
        failures,
    )
    require(
        report.get("report_id") == EXPECTED_REPORT_ID,
        f"report_id is {report.get('report_id')!r}",
        failures,
    )
    require(report.get("status") in VALID_STATUSES, f"status is {report.get('status')!r}", failures)
    require(report.get("transport") == "local_uvicorn_http", "transport is not local_uvicorn_http", failures)

    step_count = int_value(report.get("step_count"))
    passed_step_count = int_value(report.get("passed_step_count"))
    require(step_count > 0, "step_count must be positive", failures)
    require(passed_step_count == step_count, "passed_step_count must equal step_count", failures)

    endpoint_steps = as_list(report.get("endpoint_steps"))
    require(len(endpoint_steps) == step_count, "endpoint_steps length must equal step_count", failures)
    for step in endpoint_steps:
        if not isinstance(step, dict):
            failures.append("endpoint_steps item must be an object")
            continue
        require(step.get("passed") is True, f"endpoint step {step.get('step_id')} did not pass", failures)

    forbidden = sorted(set(walk_keys(report)).intersection(FORBIDDEN_KEYS))
    require(not forbidden, f"forbidden keys leaked: {forbidden}", failures)

    sessions = as_obj(report.get("sessions"))
    for field in REQUIRED_SESSION_FLAGS:
        require(sessions.get(field) is True, f"sessions.{field} must be true", failures)

    checks = as_obj(report.get("checks"))
    require(bool(checks), "checks missing", failures)
    for key, value in checks.items():
        require(value is True, f"check failed: {key}", failures)

    summary = as_obj(report.get("summary"))
    require(
        summary.get("background_handoff_status") == "handoff_tick_exported",
        "background handoff status is not handoff_tick_exported",
        failures,
    )
    require(
        int_value(summary.get("background_handoff_runner_handoff_count")) == 2,
        "background handoff runner count is not 2",
        failures,
    )
    require(
        summary.get("background_handoff_outbox_schema_version")
        == "provider_adapter_runner_handoff_outbox.v0.1",
        "background handoff outbox schema mismatch",
        failures,
    )
    require(
        summary.get("image_chain_staging_status") == "validation_failed",
        "image chain staging status is not validation_failed",
        failures,
    )
    require(
        summary.get("positive_shared_cache_reuse_path")
        == "not_exercised_no_approved_promotion_fixture",
        "positive shared cache reuse path must remain not exercised",
        failures,
    )
    require(
        summary.get("runtime_readiness_chain_status") == "completed_review_only",
        "runtime readiness chain is not completed_review_only",
        failures,
    )
    require(
        int_value(summary.get("runtime_readiness_chain_step_count")) == 3,
        "runtime readiness chain step count is not 3",
        failures,
    )
    require(
        summary.get("runtime_readiness_chain_schedule_item_id")
        == "sched_next_map_visual_prefetch",
        "runtime readiness chain schedule item mismatch",
        failures,
    )
    require(
        int_value(summary.get("runtime_readiness_chain_activation_allowed_count")) == 0,
        "runtime readiness chain activation allowed count is not 0",
        failures,
    )
    post_actions = {
        str(action)
        for action in as_list(summary.get("runtime_readiness_chain_post_actions"))
    }
    require(
        "wait_for_runtime_activation_apply_gate" in post_actions,
        "runtime readiness chain apply gate action missing",
        failures,
    )
    require(
        "run_runtime_activation_readiness_chain" not in post_actions,
        "runtime readiness chain should not be recommended again after completion",
        failures,
    )
    ledger_counts = as_obj(summary.get("runtime_readiness_chain_ledger_kind_counts"))
    for kind, expected in REQUIRED_RUNTIME_LEDGER_COUNTS.items():
        require(
            int_value(ledger_counts.get(kind)) == expected,
            f"runtime readiness ledger count for {kind} is not {expected}",
            failures,
        )

    safety = as_obj(report.get("safety_summary"))
    require(safety.get("reads_env_file") is False, "reads_env_file must be false", failures)
    for field in (
        "external_provider_call_count",
        "world_mutation_count",
        "runtime_activation_allowed_count",
        "queue_completion_count",
        "runtime_package_write_count",
        "world_delta_transaction_write_count",
    ):
        require(int_value(safety.get(field)) == 0, f"safety.{field} is not 0", failures)
    for field in (
        "handoff_outbox_runs_provider_adapter",
        "handoff_outbox_stages_provider_artifacts",
        "handoff_outbox_promotes_provider_artifacts",
    ):
        require(safety.get(field) is False, f"safety.{field} must be false", failures)
    require(
        safety.get("shared_cache_positive_path_not_claimed") is True,
        "shared cache positive path must not be claimed",
        failures,
    )

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = load_json(args.report)
        failures = validate_report(report)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"generation scheduler pipeline smoke report validation failed: {exc}", file=sys.stderr)
        return 1
    if failures:
        print("generation scheduler pipeline smoke report validation failed", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"generation scheduler pipeline smoke report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
