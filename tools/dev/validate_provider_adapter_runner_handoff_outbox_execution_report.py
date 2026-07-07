#!/usr/bin/env python3
"""Validate provider runner handoff outbox consumer execution reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "provider_adapter_runner_handoff_outbox_execution_report.v0.1"


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


def validate_report(report: dict[str, Any], *, path: Path, expected_executed: int) -> dict[str, Any]:
    require(report.get("schema_version") == SCHEMA_VERSION, f"{path}: schema_version mismatch")
    require(report.get("status") == "passed", f"{path}: status must be passed")
    require(report.get("executed_count") == expected_executed, f"{path}: executed_count mismatch")
    require(report.get("passed_count") == expected_executed, f"{path}: passed_count mismatch")
    require(report.get("failed_count") == 0, f"{path}: failed_count must be 0")

    safety = as_obj(report.get("safety_summary"))
    expected_zero = (
        "provider_call_count",
        "runtime_activation_allowed_count",
        "imports_to_backend_count",
        "staging_count",
        "promotion_count",
        "queue_complete_count",
        "world_mutation_allowed_count",
    )
    for key in expected_zero:
        require(int(safety.get(key) or 0) == 0, f"{path}: safety_summary.{key} must be 0")
    require(safety.get("stores_prompt_body") is False, f"{path}: must not store prompt body")
    require(
        safety.get("stores_provider_response_body") is False,
        f"{path}: must not store provider response body",
    )

    executions = as_list(report.get("executions"))
    require(len(executions) == expected_executed, f"{path}: executions length mismatch")
    for index, execution in enumerate(executions):
        require(isinstance(execution, dict), f"{path}: executions[{index}] must be an object")
        require(execution.get("status") == "passed", f"{path}: executions[{index}].status must be passed")
        output_refs = as_obj(execution.get("output_refs"))
        for ref_name in ("receipt", "envelope"):
            ref = as_obj(output_refs.get(ref_name))
            require(ref.get("exists") is True, f"{path}: executions[{index}].output_refs.{ref_name} missing")
        import_after = as_obj(execution.get("import_after_runner"))
        require(
            import_after.get("not_performed_by_this_tool") is True,
            f"{path}: executions[{index}].import_after_runner must not be performed",
        )
    return {
        "path": str(path),
        "adapter_mode": report.get("adapter_mode"),
        "executed_count": expected_executed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--expected-executed", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summaries: list[dict[str, Any]] = []
    try:
        for path in args.reports:
            summaries.append(
                validate_report(
                    load_json(path),
                    path=path,
                    expected_executed=args.expected_executed,
                )
            )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"provider runner handoff outbox execution report validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "provider runner handoff outbox execution report validation passed: "
        + json.dumps(summaries, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
