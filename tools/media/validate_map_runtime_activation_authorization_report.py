#!/usr/bin/env python3
"""Validate MapRuntime activation authorization report v0.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_VERSION = "map_runtime_activation_authorization_report.v0.1"
ALLOWED_REPORT_STATUSES = {
    "pending_developer_approval",
    "authorization_denied",
    "authorized_for_gate_review",
}
ALLOWED_AUTHORIZATION_STATUSES = {"pending", "denied", "approved_for_gate_review"}
ALLOWED_AUTHORIZATION_DECISIONS = {"pending", "denied", "approved"}
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


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"INVALID MapRuntimeActivationAuthorizationReport: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("INVALID MapRuntimeActivationAuthorizationReport: root must be object")
    return data


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
    require(report.get("schema_version") == REPORT_VERSION, f"schema_version must be {REPORT_VERSION}", errors)
    require(isinstance(report.get("report_id"), str), "report_id is required", errors)
    require(report.get("status") in ALLOWED_REPORT_STATUSES, "status is invalid", errors)

    scope = as_obj(report.get("scope"))
    require(scope.get("authorization_record_only") is True, "scope.authorization_record_only must be true", errors)
    require(scope.get("read_model_only") is True, "scope.read_model_only must be true", errors)
    require(scope.get("runtime_activation_allowed") is False, "scope.runtime_activation_allowed must be false", errors)
    require(
        scope.get("default_runtime_mutation_performed") is False,
        "scope.default_runtime_mutation_performed must be false",
        errors,
    )
    require(
        scope.get("backend_api_contract_mutation_performed") is False,
        "scope.backend_api_contract_mutation_performed must be false",
        errors,
    )
    require(
        scope.get("frontend_contract_mutation_performed") is False,
        "scope.frontend_contract_mutation_performed must be false",
        errors,
    )
    require(scope.get("provider_calls_allowed") is False, "scope.provider_calls_allowed must be false", errors)

    nodes = report.get("nodes")
    require(isinstance(nodes, list) and bool(nodes), "nodes must be a non-empty array", errors)
    if isinstance(nodes, list):
        seen: set[str] = set()
        for index, node in enumerate(nodes):
            where = f"nodes[{index}]"
            require(isinstance(node, dict), f"{where} must be object", errors)
            if not isinstance(node, dict):
                continue
            node_id = node.get("node_id")
            require(isinstance(node_id, str) and bool(node_id), f"{where}.node_id required", errors)
            if isinstance(node_id, str):
                require(node_id not in seen, f"{where}.node_id duplicate", errors)
                seen.add(node_id)
            require(
                node.get("authorization_record_present") is True,
                f"{where}.authorization_record_present must be true",
                errors,
            )
            require(
                node.get("authorization_decision") in ALLOWED_AUTHORIZATION_DECISIONS,
                f"{where}.authorization_decision invalid",
                errors,
            )
            require(
                node.get("authorization_status") in ALLOWED_AUTHORIZATION_STATUSES,
                f"{where}.authorization_status invalid",
                errors,
            )
            authorized = node.get("activation_authorized_for_gate")
            require(isinstance(authorized, bool), f"{where}.activation_authorized_for_gate must be bool", errors)
            if authorized:
                require(
                    node.get("authorization_status") == "approved_for_gate_review",
                    f"{where}.authorized node must have approved_for_gate_review status",
                    errors,
                )
            target = as_obj(node.get("target_candidate"))
            require(isinstance(target.get("to_package_id"), str), f"{where}.target_candidate.to_package_id required", errors)
            require(
                target.get("to_schema_version") == "map_runtime_package.v0.2",
                f"{where}.target_candidate.to_schema_version must be map_runtime_package.v0.2",
                errors,
            )
            safety = as_obj(node.get("safety"))
            require(
                safety.get("authorization_is_not_activation") is True,
                f"{where}.safety.authorization_is_not_activation must be true",
                errors,
            )
            require(
                safety.get("runtime_activation_allowed") is False,
                f"{where}.safety.runtime_activation_allowed must be false",
                errors,
            )
            require(
                safety.get("default_runtime_mutation_performed") is False,
                f"{where}.safety.default_runtime_mutation_performed must be false",
                errors,
            )
            require(
                safety.get("provider_call_count_by_report") == 0,
                f"{where}.safety.provider_call_count_by_report must be 0",
                errors,
            )

    summary = as_obj(report.get("summary"))
    if isinstance(nodes, list):
        require(summary.get("node_count") == len(nodes), "summary.node_count mismatch", errors)
        approved_count = sum(1 for node in nodes if isinstance(node, dict) and node.get("activation_authorized_for_gate") is True)
        require(summary.get("approved_count") == approved_count, "summary.approved_count mismatch", errors)
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

    safety_summary = as_obj(report.get("safety_summary"))
    require(safety_summary.get("reads_env_file") is False, "safety_summary.reads_env_file must be false", errors)
    require(
        safety_summary.get("provider_call_count_by_report") == 0,
        "safety_summary.provider_call_count_by_report must be 0",
        errors,
    )
    require(
        safety_summary.get("stores_prompt_body") is False,
        "safety_summary.stores_prompt_body must be false",
        errors,
    )
    require(
        safety_summary.get("stores_provider_body") is False,
        "safety_summary.stores_provider_body must be false",
        errors,
    )
    require(
        safety_summary.get("default_runtime_mutation_performed") is False,
        "safety_summary.default_runtime_mutation_performed must be false",
        errors,
    )

    walk_forbidden_keys(report, "$", errors)
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a MapRuntime activation authorization report.")
    parser.add_argument("report", help="Report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    errors = validate(report)
    if errors:
        print("INVALID MapRuntimeActivationAuthorizationReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"valid map runtime activation authorization report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
