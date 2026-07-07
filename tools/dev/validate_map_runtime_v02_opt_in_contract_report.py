#!/usr/bin/env python3
"""Validate MapRuntimePackage v0.2 opt-in contract smoke report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_VERSION = "map_runtime_v02_opt_in_contract_smoke_report.v0.1"
V02_COUNT_KEYS = (
    "resource_nodes_count",
    "hazard_zones_count",
    "defense_anchors_count",
    "blocked_areas_count",
)
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
        raise SystemExit(f"INVALID MapRuntimeV02OptInContractReport: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("INVALID MapRuntimeV02OptInContractReport: root must be object")
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
    require(report.get("status") == "passed", "status must be passed", errors)
    require(report.get("review_only") is True, "review_only must be true", errors)
    node_count = report.get("node_count")
    default_api = [item for item in as_list(report.get("default_api")) if isinstance(item, dict)]
    approved_service = [
        item
        for item in as_list(report.get("approved_service_contract"))
        if isinstance(item, dict)
    ]
    approved_selector = [
        item
        for item in as_list(report.get("approved_activation_selector"))
        if isinstance(item, dict)
    ]
    require(isinstance(node_count, int) and node_count > 0, "node_count must be positive", errors)
    require(len(default_api) == node_count, "default_api length must match node_count", errors)
    require(len(approved_service) == node_count, "approved_service_contract length must match node_count", errors)
    if "approved_activation_selector" in report:
        require(
            len(approved_selector) == node_count,
            "approved_activation_selector length must match node_count",
            errors,
        )

    for index, item in enumerate(default_api):
        where = f"default_api[{index}]"
        require(
            item.get("default_runtime_schema_version") == "map_runtime_package.v0.1",
            f"{where}.default_runtime_schema_version must be v0.1",
            errors,
        )
        require(
            item.get("default_runtime_v02_field_leak_count") == 0,
            f"{where}.default_runtime_v02_field_leak_count must be 0",
            errors,
        )
        require(
            item.get("api_dry_run_authorization_status") == "pending",
            f"{where}.api_dry_run_authorization_status must be pending",
            errors,
        )
        require(
            item.get("api_dry_run_candidate_available") is False,
            f"{where}.api_dry_run_candidate_available must be false",
            errors,
        )
        require(
            item.get("api_runtime_activation_allowed") is False,
            f"{where}.api_runtime_activation_allowed must be false",
            errors,
        )

    for index, item in enumerate(approved_service):
        where = f"approved_service_contract[{index}]"
        require(
            item.get("approved_authorization_status") == "approved_for_gate_review",
            f"{where}.approved_authorization_status must be approved_for_gate_review",
            errors,
        )
        require(
            item.get("approved_candidate_available") is True,
            f"{where}.approved_candidate_available must be true",
            errors,
        )
        require(
            item.get("approved_candidate_schema_version") == "map_runtime_package.v0.2",
            f"{where}.approved_candidate_schema_version must be v0.2",
            errors,
        )
        require(
            item.get("runtime_activation_allowed") is False,
            f"{where}.runtime_activation_allowed must be false",
            errors,
        )
        require(
            item.get("default_runtime_preserved") is True,
            f"{where}.default_runtime_preserved must be true",
            errors,
        )
        require(
            item.get("default_runtime_v02_field_leak_count") == 0,
            f"{where}.default_runtime_v02_field_leak_count must be 0",
            errors,
        )
        counts = as_obj(item.get("strong_semantic_counts"))
        for key in V02_COUNT_KEYS:
            require(int(counts.get(key) or 0) > 0, f"{where}.{key} must be positive", errors)

    for index, item in enumerate(approved_selector):
        where = f"approved_activation_selector[{index}]"
        require(
            item.get("activation_applied") is True,
            f"{where}.activation_applied must be true",
            errors,
        )
        require(
            item.get("selected_schema_version") == "map_runtime_package.v0.2",
            f"{where}.selected_schema_version must be v0.2",
            errors,
        )
        require(
            item.get("authorization_status") == "approved_for_gate_review",
            f"{where}.authorization_status must be approved_for_gate_review",
            errors,
        )
        require(
            item.get("target_matches_candidate") is True,
            f"{where}.target_matches_candidate must be true",
            errors,
        )
        require(item.get("provider_call_count") == 0, f"{where}.provider_call_count must be 0", errors)
        require(item.get("reads_env") is False, f"{where}.reads_env must be false", errors)
        counts = as_obj(item.get("strong_semantic_counts"))
        for key in V02_COUNT_KEYS:
            require(int(counts.get(key) or 0) > 0, f"{where}.{key} must be positive", errors)

    summary = as_obj(report.get("summary"))
    require(
        summary.get("default_runtime_v01_preserved_count") == node_count,
        "summary.default_runtime_v01_preserved_count mismatch",
        errors,
    )
    require(
        summary.get("api_pending_authorization_count") == node_count,
        "summary.api_pending_authorization_count mismatch",
        errors,
    )
    require(
        summary.get("approved_candidate_available_count") == node_count,
        "summary.approved_candidate_available_count mismatch",
        errors,
    )
    if approved_selector:
        require(
            summary.get("approved_selector_selected_v02_count") == node_count,
            "summary.approved_selector_selected_v02_count mismatch",
            errors,
        )
        require(
            summary.get("approved_selector_activation_applied_count") == node_count,
            "summary.approved_selector_activation_applied_count mismatch",
            errors,
        )
    require(
        summary.get("runtime_activation_allowed_count") == 0,
        "summary.runtime_activation_allowed_count must be 0",
        errors,
    )
    require(summary.get("provider_call_count") == 0, "summary.provider_call_count must be 0", errors)
    require(
        summary.get("default_runtime_mutation_count") == 0,
        "summary.default_runtime_mutation_count must be 0",
        errors,
    )

    safety = as_obj(report.get("safety"))
    require(safety.get("reads_env_file") is False, "safety.reads_env_file must be false", errors)
    require(safety.get("provider_call_count") == 0, "safety.provider_call_count must be 0", errors)
    require(
        safety.get("default_runtime_mutation_count") == 0,
        "safety.default_runtime_mutation_count must be 0",
        errors,
    )
    require(
        safety.get("backend_default_runtime_endpoint_modified") is False,
        "safety.backend_default_runtime_endpoint_modified must be false",
        errors,
    )
    require(
        safety.get("frontend_default_runtime_modified") is False,
        "safety.frontend_default_runtime_modified must be false",
        errors,
    )
    require(report.get("unknown_node_status_code") == 404, "unknown_node_status_code must be 404", errors)
    walk_forbidden_keys(report, "$", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", help="Report JSON path.")
    args = parser.parse_args()
    report = load_json(Path(args.report))
    errors = validate(report)
    if errors:
        print("INVALID MapRuntimeV02OptInContractReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"valid map runtime v0.2 opt-in contract report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
