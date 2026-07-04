#!/usr/bin/env python3
"""Validate MapRuntime promotion readiness report v0.1."""

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

ALLOWED_GATE_STATUSES = {"passed", "warning", "failed", "blocked"}
ALLOWED_NODE_STATUSES = {
    "blocked_failed_gate",
    "promotion_candidate_activation_required",
    "promotion_candidate_with_warnings",
    "promotion_candidate",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"INVALID MapRuntimePromotionReadinessReport: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("INVALID MapRuntimePromotionReadinessReport: root must be object")
    return data


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


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(
        report.get("schema_version") == "map_runtime_promotion_readiness_report.v0.1",
        "schema_version must be map_runtime_promotion_readiness_report.v0.1",
        errors,
    )
    require(isinstance(report.get("report_id"), str), "report_id is required", errors)
    require(isinstance(report.get("status"), str), "status is required", errors)
    scope = report.get("scope")
    require(isinstance(scope, dict), "scope must be object", errors)
    if isinstance(scope, dict):
        require(scope.get("read_model_only") is True, "scope.read_model_only must be true", errors)
        require(
            scope.get("runtime_activation_allowed") is False,
            "scope.runtime_activation_allowed must be false",
            errors,
        )
        require(
            scope.get("default_runtime_mutation_allowed") is False,
            "scope.default_runtime_mutation_allowed must be false",
            errors,
        )
        require(
            scope.get("provider_calls_allowed") is False,
            "scope.provider_calls_allowed must be false",
            errors,
        )

    summary = report.get("summary")
    require(isinstance(summary, dict), "summary must be object", errors)
    nodes = report.get("nodes")
    require(isinstance(nodes, list) and bool(nodes), "nodes must be non-empty array", errors)
    if isinstance(summary, dict) and isinstance(nodes, list):
        require(summary.get("node_count") == len(nodes), "summary.node_count mismatch", errors)
        require(
            summary.get("activation_allowed_count") == 0,
            "summary.activation_allowed_count must be 0",
            errors,
        )
        require(
            summary.get("provider_call_count_by_report") == 0,
            "summary.provider_call_count_by_report must be 0",
            errors,
        )
        require(
            summary.get("world_mutation_count_by_report") == 0,
            "summary.world_mutation_count_by_report must be 0",
            errors,
        )
        require(
            summary.get("runtime_mutation_count_by_report") == 0,
            "summary.runtime_mutation_count_by_report must be 0",
            errors,
        )

    if isinstance(nodes, list):
        for index, node in enumerate(nodes):
            where = f"nodes[{index}]"
            require(isinstance(node, dict), f"{where} must be object", errors)
            if not isinstance(node, dict):
                continue
            require(isinstance(node.get("node_id"), str), f"{where}.node_id required", errors)
            require(
                node.get("status") in ALLOWED_NODE_STATUSES,
                f"{where}.status invalid: {node.get('status')}",
                errors,
            )
            gates = node.get("readiness_gates")
            require(
                isinstance(gates, list) and bool(gates),
                f"{where}.readiness_gates must be non-empty",
                errors,
            )
            if isinstance(gates, list):
                gate_ids = set()
                for gate_index, gate in enumerate(gates):
                    gate_where = f"{where}.readiness_gates[{gate_index}]"
                    require(isinstance(gate, dict), f"{gate_where} must be object", errors)
                    if not isinstance(gate, dict):
                        continue
                    gate_id = gate.get("gate_id")
                    status = gate.get("status")
                    require(isinstance(gate_id, str), f"{gate_where}.gate_id required", errors)
                    require(
                        status in ALLOWED_GATE_STATUSES,
                        f"{gate_where}.status invalid: {status}",
                        errors,
                    )
                    if isinstance(gate_id, str):
                        gate_ids.add(gate_id)
                require(
                    "activation_gate_required" in gate_ids,
                    f"{where} must keep activation_gate_required",
                    errors,
                )
            activation = node.get("activation_policy")
            require(isinstance(activation, dict), f"{where}.activation_policy required", errors)
            if isinstance(activation, dict):
                require(
                    activation.get("runtime_activation_allowed") is False,
                    f"{where}.activation_policy.runtime_activation_allowed must be false",
                    errors,
                )
                require(
                    activation.get("default_runtime_mutation_allowed") is False,
                    f"{where}.activation_policy.default_runtime_mutation_allowed must be false",
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
            safety.get("player_runtime_update_performed") is False,
            "safety player_runtime_update_performed must be false",
            errors,
        )

    walk_forbidden_keys(report, "$", errors)
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a MapRuntime promotion readiness report."
    )
    parser.add_argument("report", help="Report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    errors = validate(report)
    if errors:
        print("INVALID MapRuntimePromotionReadinessReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"valid map runtime promotion readiness report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
