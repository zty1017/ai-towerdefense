#!/usr/bin/env python3
"""Build the MapRuntimePackage v0.2 activation contract plan.

This report is a review-only bridge between "v0.2 candidate can be read" and
"v0.2 is safe to make default". It records the exact backend/frontend/evidence
contract work still required, but it never applies that work and never mutates
the default player runtime.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    ROOT / "examples/review_packs/map_runtime_v02_activation_contract_plan.v0.1.json"
)
ACTIVATION_GATE_REPORT = (
    ROOT / "examples/review_packs/map_runtime_activation_gate_report.v0.1.json"
)
ACTIVATION_AUTHORIZATION_REPORT = (
    ROOT / "examples/review_packs/map_runtime_activation_authorization_report.v0.1.json"
)
OPT_IN_CONTRACT_REPORT = (
    ROOT / "examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json"
)
READINESS_REPORT = (
    ROOT / "examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json"
)
MAP_V02_API_SMOKE_REPORT = (
    ROOT / "examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json"
)


NODE_SORT_ORDER = {
    "gray_lantern_station": 0,
    "lamp_wick_store": 1,
    "old_signal_tower": 2,
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def index_by_node(items: Any) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in as_list(items):
        if not isinstance(item, dict):
            continue
        node_id = item.get("node_id")
        if isinstance(node_id, str) and node_id:
            indexed[node_id] = item
    return indexed


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def planned_step(
    step_id: str,
    owner: str,
    path: str,
    action: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "owner": owner,
        "path": path,
        "action": action,
        "reason": reason,
        "status": "not_applied",
        "apply_now": False,
    }


def command(command_id: str, argv: list[str], reason: str) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "argv": argv,
        "reason": reason,
        "required_after_activation": True,
        "status": "not_run_by_this_plan",
    }


def contract_update_plan() -> dict[str, Any]:
    backend_steps = [
        planned_step(
            "backend_default_map_runtime_selector",
            "backend",
            "backend/app/services/map_runtime_service.py",
            "Introduce an explicit approved activation selector before v0.2 can become the default map runtime source.",
            "Default `/map-runtime-package` must not switch from v0.1 to v0.2 by accident.",
        ),
        planned_step(
            "backend_frontend_mock_contract",
            "backend",
            "backend/app/api/frontend_mock.py",
            "Update the default battle map endpoints only after activation is approved, while preserving review-only preview endpoints.",
            "The player API contract must make the activated schema version explicit.",
        ),
        planned_step(
            "backend_runtime_package_aggregation",
            "backend",
            "backend/app/services/frontend_mock_service.py",
            "If v0.2 becomes default, aggregate resource nodes, hazard zones, defense anchors, and blocked areas into the battle runtime payload from the activated map package.",
            "The frontend should not have to infer strong semantics from visual layers.",
        ),
    ]
    frontend_steps = [
        planned_step(
            "frontend_v02_semantic_consumption",
            "frontend",
            "frontend/app.js",
            "Consume v0.2 resource nodes, hazard zones, defense anchors, and blocked areas only from an activated MapRuntimePackage.",
            "Player rendering must keep path, slots, objective, spawn, resources, hazards, and collision tied to structured runtime truth.",
        ),
        planned_step(
            "frontend_default_fetch_contract",
            "frontend",
            "frontend/app.js",
            "Keep preview and opt-in dry-run fetches out of the default player flow; use the default map runtime endpoint only after activation.",
            "Review-only endpoints must remain Studio/evidence surfaces rather than player runtime dependencies.",
        ),
        planned_step(
            "frontend_visual_contract_update",
            "frontend",
            "tools/frontend/validate_battle_visual_contract.py",
            "After activation, replace the current no-v0.2-default assertions with source-of-truth assertions for activated v0.2 semantics.",
            "The static frontend guard must prove the new default path is intentional.",
        ),
    ]
    evidence_commands = [
        command(
            "preview_api_smoke",
            ["python3", "tools/dev/check_map_v02_preview_api.py"],
            "Preview and default runtime safety must remain visible after contract changes.",
        ),
        command(
            "primary_api_flow_smoke",
            ["python3", "tools/dev/check_mvp_primary_api_flow.py"],
            "The full player API path must pass with the activated/default map contract.",
        ),
        command(
            "frontend_visual_contract",
            ["python3", "tools/frontend/validate_battle_visual_contract.py"],
            "Static frontend contract must prove review-only endpoints are not accidentally used as default runtime.",
        ),
        command(
            "browser_flow_visual_smoke",
            [
                "python3",
                "tools/frontend/capture_frontend_flow_visual_smoke.py",
                "--output-root",
                "/tmp/map_runtime_v02_activation_frontend_flow",
            ],
            "The player-facing battle must still render correctly after any activation task.",
        ),
        command(
            "demo_evidence_suite",
            [
                "python3",
                "tools/demo/run_demo_evidence_suite.py",
                "--output-root",
                "/tmp/demo_evidence_suite_after_map_runtime_activation",
            ],
            "Final demo evidence must be rebuilt from fresh API and browser evidence.",
        ),
    ]
    return {
        "plan_id": "map_runtime_v02_default_activation_contract_update",
        "status": "not_applied",
        "apply_now": False,
        "backend_required_changes": backend_steps,
        "frontend_required_changes": frontend_steps,
        "post_activation_required_commands": evidence_commands,
        "non_goals": [
            "Do not create a competing PathGraph or LevelBundle runtime source.",
            "Do not infer path, build slots, resources, hazards, anchors, blocked areas, or collision from images, SVG previews, or AI map candidates.",
            "Do not make review-only `/map-v02-preview` or `/map-v02-opt-in-dry-run` a player default dependency.",
        ],
    }


def build_node(
    node_id: str,
    gate_decision: dict[str, Any],
    authorization_node: dict[str, Any],
    default_api_node: dict[str, Any],
    approved_service_node: dict[str, Any],
    readiness_node: dict[str, Any],
) -> dict[str, Any]:
    target = as_obj(gate_decision.get("target_candidate"))
    blockers = as_list(gate_decision.get("blockers"))
    remaining = sorted({str(item) for item in blockers if item})
    return {
        "node_id": node_id,
        "activation_contract_status": "contract_planned_activation_not_applied",
        "activation_apply_now": False,
        "activation_decision_from_gate": gate_decision.get("activation_decision"),
        "decision_reason_from_gate": gate_decision.get("decision_reason"),
        "remaining_blockers_from_gate": remaining,
        "target_candidate": {
            "from_package_id": target.get("from_package_id"),
            "from_schema_version": target.get("from_schema_version"),
            "to_package_id": target.get("to_package_id"),
            "to_schema_version": target.get("to_schema_version"),
            "readiness_status": target.get("readiness_status"),
        },
        "authorization": {
            "authorization_status": authorization_node.get("authorization_status"),
            "activation_authorized_for_gate": authorization_node.get(
                "activation_authorized_for_gate"
            ),
            "record_present": authorization_node.get("authorization_record_present"),
        },
        "default_api_contract": {
            "default_runtime_schema_version": default_api_node.get(
                "default_runtime_schema_version"
            ),
            "default_runtime_v02_field_leak_count": default_api_node.get(
                "default_runtime_v02_field_leak_count"
            ),
            "api_dry_run_authorization_status": default_api_node.get(
                "api_dry_run_authorization_status"
            ),
            "api_dry_run_candidate_available": default_api_node.get(
                "api_dry_run_candidate_available"
            ),
            "api_runtime_activation_allowed": default_api_node.get(
                "api_runtime_activation_allowed"
            ),
        },
        "approved_fixture_contract": {
            "approved_candidate_available": approved_service_node.get(
                "approved_candidate_available"
            ),
            "approved_candidate_schema_version": approved_service_node.get(
                "approved_candidate_schema_version"
            ),
            "strong_semantic_counts": as_obj(
                approved_service_node.get("strong_semantic_counts")
            ),
            "runtime_activation_allowed": approved_service_node.get(
                "runtime_activation_allowed"
            ),
            "default_runtime_preserved": approved_service_node.get(
                "default_runtime_preserved"
            ),
            "default_runtime_v02_field_leak_count": approved_service_node.get(
                "default_runtime_v02_field_leak_count"
            ),
        },
        "readiness": {
            "status": readiness_node.get("status"),
            "blocking_reasons": as_list(readiness_node.get("blocking_reasons")),
        },
        "planned_next_checks": [
            "developer_must_approve_or_deny_activation_authorization",
            "backend_default_runtime_contract_must_be_updated_in_dedicated_activation_task",
            "frontend_runtime_contract_must_be_updated_in_dedicated_activation_task",
            "post_activation_api_browser_and_demo_evidence_must_be_rerun",
        ],
        "safety": {
            "plan_only": True,
            "activation_allowed": False,
            "activation_performed": False,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_performed": False,
            "world_state_mutation_performed": False,
            "provider_call_count_by_plan": 0,
        },
    }


def build_report() -> dict[str, Any]:
    gate_report = load_json(ACTIVATION_GATE_REPORT)
    authorization_report = load_json(ACTIVATION_AUTHORIZATION_REPORT)
    opt_in_report = load_json(OPT_IN_CONTRACT_REPORT)
    readiness_report = load_json(READINESS_REPORT)
    api_smoke_report = load_json(MAP_V02_API_SMOKE_REPORT)

    gate_by_node = index_by_node(gate_report.get("decisions"))
    authorization_by_node = index_by_node(authorization_report.get("nodes"))
    default_api_by_node = index_by_node(opt_in_report.get("default_api"))
    approved_service_by_node = index_by_node(opt_in_report.get("approved_service_contract"))
    readiness_by_node = index_by_node(readiness_report.get("nodes"))

    node_ids = sorted(
        set(gate_by_node)
        | set(authorization_by_node)
        | set(default_api_by_node)
        | set(approved_service_by_node)
        | set(readiness_by_node),
        key=lambda node: (NODE_SORT_ORDER.get(node, 99), node),
    )
    nodes = [
        build_node(
            node_id,
            gate_by_node.get(node_id, {}),
            authorization_by_node.get(node_id, {}),
            default_api_by_node.get(node_id, {}),
            approved_service_by_node.get(node_id, {}),
            readiness_by_node.get(node_id, {}),
        )
        for node_id in node_ids
    ]
    plan = contract_update_plan()
    blocker_counts = Counter(
        blocker
        for node in nodes
        for blocker in as_list(node.get("remaining_blockers_from_gate"))
    )
    semantic_counts = Counter()
    for node in nodes:
        semantic_counts.update(as_obj(node.get("approved_fixture_contract")).get("strong_semantic_counts", {}))
    summary = {
        "node_count": len(nodes),
        "contract_plan_status": plan["status"],
        "activation_apply_now_count": sum(1 for node in nodes if node.get("activation_apply_now")),
        "activation_allowed_count": 0,
        "activation_blocked_count_from_gate": as_obj(gate_report.get("summary")).get(
            "activation_blocked_count"
        ),
        "default_runtime_v01_preserved_count": as_obj(opt_in_report.get("summary")).get(
            "default_runtime_v01_preserved_count"
        ),
        "approved_candidate_available_count": as_obj(opt_in_report.get("summary")).get(
            "approved_candidate_available_count"
        ),
        "api_pending_authorization_count": as_obj(opt_in_report.get("summary")).get(
            "api_pending_authorization_count"
        ),
        "authorization_report_status": authorization_report.get("status"),
        "authorization_approved_count": as_obj(authorization_report.get("summary")).get(
            "approved_count"
        ),
        "gate_status": gate_report.get("status"),
        "readiness_status": readiness_report.get("status"),
        "api_smoke_status": api_smoke_report.get("status"),
        "blocker_counts_from_gate": dict(sorted(blocker_counts.items())),
        "approved_fixture_strong_semantic_totals": dict(sorted(semantic_counts.items())),
        "backend_required_change_count": len(plan["backend_required_changes"]),
        "frontend_required_change_count": len(plan["frontend_required_changes"]),
        "post_activation_required_command_count": len(
            plan["post_activation_required_commands"]
        ),
        "provider_call_count_by_plan": 0,
        "runtime_mutation_count_by_plan": 0,
        "world_mutation_count_by_plan": 0,
    }
    return {
        "schema_version": "map_runtime_v02_activation_contract_plan.v0.1",
        "report_id": "mvp_map_runtime_v02_activation_contract_plan",
        "generated_at": "2026-07-05T00:00:00Z",
        "status": "plan_ready_activation_not_applied",
        "inputs": {
            "map_runtime_activation_gate_report": rel(ACTIVATION_GATE_REPORT),
            "map_runtime_activation_authorization_report": rel(
                ACTIVATION_AUTHORIZATION_REPORT
            ),
            "map_runtime_v02_opt_in_contract_smoke_report": rel(OPT_IN_CONTRACT_REPORT),
            "map_runtime_promotion_readiness_report": rel(READINESS_REPORT),
            "map_v02_preview_api_smoke_report": rel(MAP_V02_API_SMOKE_REPORT),
        },
        "scope": {
            "plan_only": True,
            "read_model_only": True,
            "runtime_activation_allowed": False,
            "activation_performed": False,
            "default_runtime_mutation_allowed": False,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_allowed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_allowed": False,
            "frontend_contract_mutation_performed": False,
            "provider_calls_allowed": False,
            "world_state_mutation_allowed": False,
        },
        "policy": [
            "This plan records the contract delta needed before MapRuntimePackage v0.2 can become a default player runtime.",
            "This plan must not activate v0.2, mutate default MapRuntimePackage files, update backend routes, or update frontend runtime behavior.",
            "MapRuntimePackage remains the map runtime truth source; images, SVG previews, StylePack media, and AI candidates cannot backfill path, slot, resource, hazard, anchor, blocked-area, or collision truth.",
        ],
        "summary": summary,
        "nodes": nodes,
        "contract_update_plan": plan,
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count_by_plan": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "world_mutation_count_by_plan": 0,
            "runtime_mutation_count_by_plan": 0,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_performed": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the MapRuntimePackage v0.2 activation contract plan."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to write the report JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    output = Path(args.output)
    write_json(output, report)
    print(f"wrote map runtime v0.2 activation contract plan: {output}")
    print(
        "status="
        f"{report['status']} nodes={report['summary']['node_count']} "
        f"activation_allowed={report['summary']['activation_allowed_count']} "
        f"backend_steps={report['summary']['backend_required_change_count']} "
        f"frontend_steps={report['summary']['frontend_required_change_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
