#!/usr/bin/env python3
"""Validate provider runner handoff outbox import pipeline smoke reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA_VERSION = "provider_runner_handoff_outbox_import_pipeline_report.v0.1"
EXPECTED_OUTBOX_SCHEMA_VERSION = "provider_adapter_runner_handoff_outbox.v0.1"
EXPECTED_CONSUMER_SCHEMA_VERSION = (
    "provider_adapter_runner_handoff_outbox_execution_report.v0.1"
)
EXPECTED_SCHEDULE_ITEM_IDS = {
    "sched_next_map_visual_prefetch",
    "sched_video_frame_background_compile",
}
FORBIDDEN_KEYS = {
    "raw_prompt",
    "provider_response",
    "provider_body",
    "api_key",
    "secret",
}


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


def validate_steps(report: dict[str, Any], failures: list[str]) -> None:
    step_count = int_value(report.get("step_count"))
    passed_step_count = int_value(report.get("passed_step_count"))
    steps = as_list(report.get("steps"))
    require(step_count > 0, "step_count must be positive", failures)
    require(passed_step_count == step_count, "passed_step_count must equal step_count", failures)
    require(len(steps) == step_count, "steps length must equal step_count", failures)
    for step in steps:
        if not isinstance(step, dict):
            failures.append("steps item must be an object")
            continue
        passed = step.get("passed") is True or step.get("status") == "passed"
        require(passed, f"step {step.get('step_id')} did not pass", failures)


def validate_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    require(
        report.get("schema_version") == EXPECTED_SCHEMA_VERSION,
        f"schema_version is {report.get('schema_version')!r}",
        failures,
    )
    require(report.get("status") == "passed", f"status is {report.get('status')!r}", failures)
    validate_steps(report, failures)

    forbidden = sorted(set(walk_keys(report)).intersection(FORBIDDEN_KEYS))
    require(not forbidden, f"forbidden keys leaked: {forbidden}", failures)

    summary = as_obj(report.get("summary"))
    require(
        summary.get("handoff_outbox_schema_version") == EXPECTED_OUTBOX_SCHEMA_VERSION,
        "handoff outbox schema version mismatch",
        failures,
    )
    require(int_value(summary.get("runner_handoff_count")) == 2, "runner handoff count is not 2", failures)
    require(summary.get("consumer_status") == "passed", "consumer status is not passed", failures)
    require(int_value(summary.get("consumer_executed_count")) == 2, "consumer executed count is not 2", failures)
    require(int_value(summary.get("imported_count")) == 2, "imported count is not 2", failures)
    require(
        int_value(summary.get("pre_import_review_only_envelope_ready_count")) == 0,
        "pre-import ready count is not 0",
        failures,
    )
    require(
        int_value(summary.get("prefetch_review_only_envelope_ready_count")) == 2,
        "post-import prefetch ready count is not 2",
        failures,
    )
    require(
        int_value(summary.get("activation_allowed_count")) == 0,
        "activation allowed count is not 0",
        failures,
    )
    statuses = [str(status) for status in as_list(summary.get("import_worker_statuses"))]
    require(len(statuses) == 2, "import worker status count is not 2", failures)
    require(all(status == "imported" for status in statuses), "not all import workers imported", failures)

    consumer = as_obj(report.get("consumer_report"))
    require(
        consumer.get("schema_version") == EXPECTED_CONSUMER_SCHEMA_VERSION,
        "consumer report schema version mismatch",
        failures,
    )
    require(consumer.get("status") == "passed", "consumer report status is not passed", failures)
    require(int_value(consumer.get("executed_count")) == 2, "consumer report executed count is not 2", failures)
    require(int_value(consumer.get("passed_count")) == 2, "consumer report passed count is not 2", failures)

    import_results = [item for item in as_list(report.get("import_results")) if isinstance(item, dict)]
    require(len(import_results) == 2, "import result count is not 2", failures)
    schedule_item_ids = {str(item.get("schedule_item_id")) for item in import_results}
    require(
        schedule_item_ids == EXPECTED_SCHEDULE_ITEM_IDS,
        f"import result schedule item ids mismatch: {sorted(schedule_item_ids)}",
        failures,
    )
    for item in import_results:
        schedule_item_id = item.get("schedule_item_id")
        require(item.get("status") == "imported", f"{schedule_item_id}: status is not imported", failures)
        require(
            item.get("worker_mode") == "provider_adapter_runner_output_import",
            f"{schedule_item_id}: worker mode mismatch",
            failures,
        )
        for field in (
            "provider_call_count",
            "world_mutation_count",
            "activation_allowed_count",
        ):
            require(int_value(item.get(field)) == 0, f"{schedule_item_id}: {field} is not 0", failures)

    safety = as_obj(report.get("safety_summary"))
    for field in (
        "external_provider_call_count",
        "consumer_reads_env_count",
        "consumer_imports_to_backend_count",
        "staging_count",
        "promotion_count",
        "world_mutation_count",
        "runtime_activation_allowed_count",
        "queue_complete_count",
    ):
        require(int_value(safety.get(field)) == 0, f"safety.{field} is not 0", failures)
    require(int_value(safety.get("api_import_count")) == 2, "safety.api_import_count is not 2", failures)

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
        print(f"provider runner outbox import report validation failed: {exc}", file=sys.stderr)
        return 1
    if failures:
        print("provider runner outbox import report validation failed", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"provider runner outbox import report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
