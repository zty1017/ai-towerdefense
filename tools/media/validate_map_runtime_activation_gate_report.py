#!/usr/bin/env python3
"""Validate MapRuntime activation gate report v0.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FORBIDDEN_KEYS = {
    "api_key",
    "secret",
    "token",
    "raw_prompt",
    "full_prompt",
    "provider_response",
    "raw_response",
    "raw_json",
    "full_trace",
}

ALLOWED_REPORT_STATUSES = {"blocked", "allowed"}
ALLOWED_DECISIONS = {"blocked", "allowed"}
ALLOWED_CHECK_STATUSES = {"passed", "warning", "failed", "blocked"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"INVALID MapRuntimeActivationGateReport: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("INVALID MapRuntimeActivationGateReport: root must be object")
    return data


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def walk_forbidden_keys(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_KEYS or lowered.endswith("_api_key"):
                errors.append(f"{path}.{key}: forbidden key")
            walk_forbidden_keys(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            walk_forbidden_keys(item, f"{path}[{index}]", errors)


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(
        report.get("schema_version") == "map_runtime_activation_gate_report.v0.1",
        "schema_version must be map_runtime_activation_gate_report.v0.1",
        errors,
    )
    require(isinstance(report.get("report_id"), str), "report_id is required", errors)
    require(report.get("status") in ALLOWED_REPORT_STATUSES, "status is invalid", errors)

    scope = report.get("scope")
    require(isinstance(scope, dict), "scope must be object", errors)
    if isinstance(scope, dict):
        require(scope.get("gate_only") is True, "scope.gate_only must be true", errors)
        require(scope.get("read_model_only") is True, "scope.read_model_only must be true", errors)
        require(
            scope.get("runtime_activation_allowed") is False,
            "scope.runtime_activation_allowed must be false for current gate report",
            errors,
        )
        require(
            scope.get("default_runtime_mutation_performed") is False,
            "scope.default_runtime_mutation_performed must be false",
            errors,
        )
        require(
            scope.get("provider_calls_allowed") is False,
            "scope.provider_calls_allowed must be false",
            errors,
        )

    decisions = report.get("decisions")
    require(
        isinstance(decisions, list) and bool(decisions),
        "decisions must be a non-empty array",
        errors,
    )
    if isinstance(decisions, list):
        for index, decision in enumerate(decisions):
            where = f"decisions[{index}]"
            require(isinstance(decision, dict), f"{where} must be object", errors)
            if not isinstance(decision, dict):
                continue
            require(isinstance(decision.get("node_id"), str), f"{where}.node_id required", errors)
            require(
                decision.get("activation_decision") in ALLOWED_DECISIONS,
                f"{where}.activation_decision invalid",
                errors,
            )
            require(
                decision.get("activation_decision") == "blocked",
                f"{where}.activation_decision must remain blocked in this report",
                errors,
            )
            blockers = decision.get("blockers")
            require(
                isinstance(blockers, list) and bool(blockers),
                f"{where}.blockers must be non-empty while blocked",
                errors,
            )
            checks = decision.get("checks")
            require(
                isinstance(checks, list) and bool(checks),
                f"{where}.checks must be non-empty",
                errors,
            )
            if isinstance(checks, list):
                check_ids = set()
                for check_index, item in enumerate(checks):
                    check_where = f"{where}.checks[{check_index}]"
                    require(isinstance(item, dict), f"{check_where} must be object", errors)
                    if not isinstance(item, dict):
                        continue
                    check_id = item.get("check_id")
                    status = item.get("status")
                    require(isinstance(check_id, str), f"{check_where}.check_id required", errors)
                    require(
                        status in ALLOWED_CHECK_STATUSES,
                        f"{check_where}.status invalid: {status}",
                        errors,
                    )
                    if isinstance(check_id, str):
                        check_ids.add(check_id)
                for required_check in (
                    "explicit_developer_activation_approval",
                    "api_frontend_contract_update",
                    "post_activation_evidence_required",
                ):
                    require(
                        required_check in check_ids,
                        f"{where} missing required check {required_check}",
                        errors,
                    )
            safety = decision.get("safety")
            require(isinstance(safety, dict), f"{where}.safety must be object", errors)
            if isinstance(safety, dict):
                require(
                    safety.get("activation_allowed") is False,
                    f"{where}.safety.activation_allowed must be false",
                    errors,
                )
                require(
                    safety.get("default_runtime_mutation_performed") is False,
                    f"{where}.safety.default_runtime_mutation_performed must be false",
                    errors,
                )
                require(
                    safety.get("provider_call_count_by_gate") == 0,
                    f"{where}.safety.provider_call_count_by_gate must be 0",
                    errors,
                )

    summary = report.get("summary")
    require(isinstance(summary, dict), "summary must be object", errors)
    if isinstance(summary, dict) and isinstance(decisions, list):
        require(summary.get("node_count") == len(decisions), "summary.node_count mismatch", errors)
        require(
            summary.get("activation_allowed_count") == 0,
            "summary.activation_allowed_count must be 0",
            errors,
        )
        require(
            summary.get("runtime_mutation_count_by_report") == 0,
            "summary.runtime_mutation_count_by_report must be 0",
            errors,
        )
        require(
            summary.get("world_mutation_count_by_report") == 0,
            "summary.world_mutation_count_by_report must be 0",
            errors,
        )
        require(
            summary.get("provider_call_count_by_report") == 0,
            "summary.provider_call_count_by_report must be 0",
            errors,
        )

    safety = report.get("safety_summary")
    require(isinstance(safety, dict), "safety_summary must be object", errors)
    if isinstance(safety, dict):
        require(safety.get("reads_env_file") is False, "safety reads_env_file must be false", errors)
        require(
            safety.get("provider_call_count_by_report") == 0,
            "safety provider_call_count_by_report must be 0",
            errors,
        )
        require(
            safety.get("stores_prompt_body") is False,
            "safety stores_prompt_body must be false",
            errors,
        )
        require(
            safety.get("stores_provider_body") is False,
            "safety stores_provider_body must be false",
            errors,
        )
        require(
            safety.get("default_runtime_mutation_performed") is False,
            "safety default_runtime_mutation_performed must be false",
            errors,
        )
        require(
            safety.get("backend_api_contract_mutation_performed") is False,
            "safety backend_api_contract_mutation_performed must be false",
            errors,
        )
        require(
            safety.get("frontend_contract_mutation_performed") is False,
            "safety frontend_contract_mutation_performed must be false",
            errors,
        )

    walk_forbidden_keys(report, "$", errors)
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a MapRuntime activation gate report.")
    parser.add_argument("report", help="Report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    errors = validate(report)
    if errors:
        print("INVALID MapRuntimeActivationGateReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"valid map runtime activation gate report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
