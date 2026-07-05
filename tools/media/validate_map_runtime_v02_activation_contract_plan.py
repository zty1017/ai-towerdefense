#!/usr/bin/env python3
"""Validate MapRuntimePackage v0.2 activation contract plan v0.1."""

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

REQUIRED_BACKEND_PATHS = {
    "backend/app/services/map_runtime_service.py",
    "backend/app/api/frontend_mock.py",
}
REQUIRED_FRONTEND_PATHS = {
    "frontend/app.js",
    "tools/frontend/validate_battle_visual_contract.py",
}
REQUIRED_COMMAND_IDS = {
    "preview_api_smoke",
    "primary_api_flow_smoke",
    "frontend_visual_contract",
    "browser_flow_visual_smoke",
    "demo_evidence_suite",
}
REQUIRED_NODE_BLOCKERS = {
    "api_frontend_contract_update_required",
    "post_activation_evidence_required",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"INVALID MapRuntimeV02ActivationContractPlan: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("INVALID MapRuntimeV02ActivationContractPlan: root must be object")
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


def validate_step_list(
    steps: Any,
    where: str,
    required_paths: set[str],
    errors: list[str],
) -> None:
    require(isinstance(steps, list) and bool(steps), f"{where} must be non-empty array", errors)
    if not isinstance(steps, list):
        return
    seen_paths: set[str] = set()
    for index, step in enumerate(steps):
        step_where = f"{where}[{index}]"
        require(isinstance(step, dict), f"{step_where} must be object", errors)
        if not isinstance(step, dict):
            continue
        require(isinstance(step.get("step_id"), str), f"{step_where}.step_id required", errors)
        require(step.get("status") == "not_applied", f"{step_where}.status must be not_applied", errors)
        require(step.get("apply_now") is False, f"{step_where}.apply_now must be false", errors)
        path = step.get("path")
        require(isinstance(path, str) and bool(path), f"{step_where}.path required", errors)
        if isinstance(path, str):
            seen_paths.add(path)
        require(isinstance(step.get("action"), str), f"{step_where}.action required", errors)
        require(isinstance(step.get("reason"), str), f"{step_where}.reason required", errors)
    missing = required_paths - seen_paths
    require(not missing, f"{where} missing required paths: {sorted(missing)}", errors)


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(
        report.get("schema_version")
        == "map_runtime_v02_activation_contract_plan.v0.1",
        "schema_version must be map_runtime_v02_activation_contract_plan.v0.1",
        errors,
    )
    require(isinstance(report.get("report_id"), str), "report_id is required", errors)
    require(
        report.get("status") == "plan_ready_activation_not_applied",
        "status must be plan_ready_activation_not_applied",
        errors,
    )

    scope = report.get("scope")
    require(isinstance(scope, dict), "scope must be object", errors)
    if isinstance(scope, dict):
        for key in (
            "plan_only",
            "read_model_only",
        ):
            require(scope.get(key) is True, f"scope.{key} must be true", errors)
        for key in (
            "runtime_activation_allowed",
            "activation_performed",
            "default_runtime_mutation_allowed",
            "default_runtime_mutation_performed",
            "backend_api_contract_mutation_allowed",
            "backend_api_contract_mutation_performed",
            "frontend_contract_mutation_allowed",
            "frontend_contract_mutation_performed",
            "provider_calls_allowed",
            "world_state_mutation_allowed",
        ):
            require(scope.get(key) is False, f"scope.{key} must be false", errors)

    inputs = report.get("inputs")
    require(isinstance(inputs, dict), "inputs must be object", errors)
    if isinstance(inputs, dict):
        for key in (
            "map_runtime_activation_gate_report",
            "map_runtime_activation_authorization_report",
            "map_runtime_v02_opt_in_contract_smoke_report",
            "map_runtime_promotion_readiness_report",
            "map_v02_preview_api_smoke_report",
        ):
            require(isinstance(inputs.get(key), str), f"inputs.{key} required", errors)

    nodes = report.get("nodes")
    require(isinstance(nodes, list) and bool(nodes), "nodes must be non-empty array", errors)
    if isinstance(nodes, list):
        for index, node in enumerate(nodes):
            where = f"nodes[{index}]"
            require(isinstance(node, dict), f"{where} must be object", errors)
            if not isinstance(node, dict):
                continue
            require(isinstance(node.get("node_id"), str), f"{where}.node_id required", errors)
            require(
                node.get("activation_contract_status")
                == "contract_planned_activation_not_applied",
                f"{where}.activation_contract_status invalid",
                errors,
            )
            require(node.get("activation_apply_now") is False, f"{where}.activation_apply_now must be false", errors)
            require(
                node.get("activation_decision_from_gate") == "blocked",
                f"{where}.activation_decision_from_gate must remain blocked",
                errors,
            )
            blockers = {str(item) for item in as_list(node.get("remaining_blockers_from_gate"))}
            require(
                REQUIRED_NODE_BLOCKERS.issubset(blockers),
                f"{where}.remaining_blockers_from_gate missing {sorted(REQUIRED_NODE_BLOCKERS - blockers)}",
                errors,
            )
            target = as_obj(node.get("target_candidate"))
            require(
                target.get("from_schema_version") == "map_runtime_package.v0.1",
                f"{where}.target_candidate.from_schema_version must be v0.1",
                errors,
            )
            require(
                target.get("to_schema_version") == "map_runtime_package.v0.2",
                f"{where}.target_candidate.to_schema_version must be v0.2",
                errors,
            )
            default_api = as_obj(node.get("default_api_contract"))
            require(
                default_api.get("default_runtime_schema_version")
                == "map_runtime_package.v0.1",
                f"{where}.default_api_contract.default_runtime_schema_version must be v0.1",
                errors,
            )
            require(
                default_api.get("default_runtime_v02_field_leak_count") == 0,
                f"{where}.default_api_contract.default_runtime_v02_field_leak_count must be 0",
                errors,
            )
            require(
                default_api.get("api_runtime_activation_allowed") is False,
                f"{where}.default_api_contract.api_runtime_activation_allowed must be false",
                errors,
            )
            approved = as_obj(node.get("approved_fixture_contract"))
            require(
                approved.get("approved_candidate_available") is True,
                f"{where}.approved_fixture_contract.approved_candidate_available must be true",
                errors,
            )
            require(
                approved.get("approved_candidate_schema_version")
                == "map_runtime_package.v0.2",
                f"{where}.approved_fixture_contract.approved_candidate_schema_version must be v0.2",
                errors,
            )
            require(
                approved.get("runtime_activation_allowed") is False,
                f"{where}.approved_fixture_contract.runtime_activation_allowed must be false",
                errors,
            )
            semantics = as_obj(approved.get("strong_semantic_counts"))
            for key in (
                "resource_nodes_count",
                "hazard_zones_count",
                "defense_anchors_count",
                "blocked_areas_count",
            ):
                require(
                    int(semantics.get(key) or 0) > 0,
                    f"{where}.approved_fixture_contract.strong_semantic_counts.{key} must be > 0",
                    errors,
                )
            safety = as_obj(node.get("safety"))
            for key in (
                "activation_allowed",
                "activation_performed",
                "default_runtime_mutation_performed",
                "backend_api_contract_mutation_performed",
                "frontend_contract_mutation_performed",
                "world_state_mutation_performed",
            ):
                require(safety.get(key) is False, f"{where}.safety.{key} must be false", errors)
            require(
                safety.get("provider_call_count_by_plan") == 0,
                f"{where}.safety.provider_call_count_by_plan must be 0",
                errors,
            )

    plan = report.get("contract_update_plan")
    require(isinstance(plan, dict), "contract_update_plan must be object", errors)
    if isinstance(plan, dict):
        require(plan.get("status") == "not_applied", "contract_update_plan.status must be not_applied", errors)
        require(plan.get("apply_now") is False, "contract_update_plan.apply_now must be false", errors)
        validate_step_list(
            plan.get("backend_required_changes"),
            "contract_update_plan.backend_required_changes",
            REQUIRED_BACKEND_PATHS,
            errors,
        )
        validate_step_list(
            plan.get("frontend_required_changes"),
            "contract_update_plan.frontend_required_changes",
            REQUIRED_FRONTEND_PATHS,
            errors,
        )
        commands = plan.get("post_activation_required_commands")
        require(
            isinstance(commands, list) and bool(commands),
            "contract_update_plan.post_activation_required_commands must be non-empty array",
            errors,
        )
        seen_command_ids: set[str] = set()
        if isinstance(commands, list):
            for index, item in enumerate(commands):
                where = f"contract_update_plan.post_activation_required_commands[{index}]"
                require(isinstance(item, dict), f"{where} must be object", errors)
                if not isinstance(item, dict):
                    continue
                command_id = item.get("command_id")
                require(isinstance(command_id, str), f"{where}.command_id required", errors)
                if isinstance(command_id, str):
                    seen_command_ids.add(command_id)
                require(isinstance(item.get("argv"), list), f"{where}.argv must be array", errors)
                require(
                    item.get("required_after_activation") is True,
                    f"{where}.required_after_activation must be true",
                    errors,
                )
                require(
                    item.get("status") == "not_run_by_this_plan",
                    f"{where}.status must be not_run_by_this_plan",
                    errors,
                )
        missing_commands = REQUIRED_COMMAND_IDS - seen_command_ids
        require(
            not missing_commands,
            f"contract_update_plan.post_activation_required_commands missing {sorted(missing_commands)}",
            errors,
        )

    summary = report.get("summary")
    require(isinstance(summary, dict), "summary must be object", errors)
    if isinstance(summary, dict) and isinstance(nodes, list):
        require(summary.get("node_count") == len(nodes), "summary.node_count mismatch", errors)
        require(
            summary.get("contract_plan_status") == "not_applied",
            "summary.contract_plan_status must be not_applied",
            errors,
        )
        require(
            summary.get("activation_apply_now_count") == 0,
            "summary.activation_apply_now_count must be 0",
            errors,
        )
        require(
            summary.get("activation_allowed_count") == 0,
            "summary.activation_allowed_count must be 0",
            errors,
        )
        for key in (
            "provider_call_count_by_plan",
            "runtime_mutation_count_by_plan",
            "world_mutation_count_by_plan",
        ):
            require(summary.get(key) == 0, f"summary.{key} must be 0", errors)

    safety = report.get("safety_summary")
    require(isinstance(safety, dict), "safety_summary must be object", errors)
    if isinstance(safety, dict):
        require(safety.get("reads_env_file") is False, "safety reads_env_file must be false", errors)
        require(
            safety.get("provider_call_count_by_plan") == 0,
            "safety provider_call_count_by_plan must be 0",
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
    parser = argparse.ArgumentParser(
        description="Validate a MapRuntimePackage v0.2 activation contract plan."
    )
    parser.add_argument("report", help="Report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_json(Path(args.report))
    errors = validate(report)
    if errors:
        print("INVALID MapRuntimeV02ActivationContractPlan")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"valid map runtime v0.2 activation contract plan: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
