#!/usr/bin/env python3
"""Build a read-only MapRuntime activation authorization report.

This report records whether a developer has explicitly authorized a v0.2
MapRuntimePackage to become a default player runtime candidate. It is only an
authorization record: it never mutates runtime packages, backend APIs, frontend
behavior, world state, or provider state.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_runtime_activation_authorization_report.v0.1.json"
READINESS_REPORT = ROOT / "examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json"
ACTIVATION_GATE_REPORT = ROOT / "examples/review_packs/map_runtime_activation_gate_report.v0.1.json"

REPORT_VERSION = "map_runtime_activation_authorization_report.v0.1"
ALLOWED_DECISIONS = {"pending", "denied", "approved"}
NODE_SORT_ORDER = {
    "gray_lantern_station": 0,
    "lamp_wick_store": 1,
    "old_signal_tower": 2,
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def index_by_node(items: list[Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("node_id"), str):
            indexed[item["node_id"]] = item
    return indexed


def normalize_plan(plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not plan:
        return {}
    approvals: dict[str, dict[str, Any]] = {}
    for item in as_list(plan.get("approvals")):
        if not isinstance(item, dict) or not isinstance(item.get("node_id"), str):
            continue
        decision = item.get("authorization_decision", "pending")
        if decision not in ALLOWED_DECISIONS:
            decision = "pending"
        approvals[item["node_id"]] = {**item, "authorization_decision": decision}
    return approvals


def build_node_authorization(
    *,
    node_id: str,
    readiness_node: dict[str, Any] | None,
    gate_decision: dict[str, Any] | None,
    approval: dict[str, Any] | None,
) -> dict[str, Any]:
    target_candidate = as_obj((gate_decision or {}).get("target_candidate"))
    target_package_id = target_candidate.get("to_package_id")
    target_schema_version = target_candidate.get("to_schema_version")
    plan_decision = (approval or {}).get("authorization_decision", "pending")
    approval_matches_target = (
        approval is not None
        and (approval.get("target_package_id") in (None, target_package_id))
        and (approval.get("target_schema_version") in (None, target_schema_version))
    )

    if approval is not None and not approval_matches_target:
        authorization_status = "pending"
        blocker_reasons = ["developer_authorization_target_mismatch"]
        effective_decision = "pending"
    elif plan_decision == "approved" and approval_matches_target:
        authorization_status = "approved_for_gate_review"
        blocker_reasons: list[str] = []
        effective_decision = "approved"
    elif plan_decision == "denied":
        authorization_status = "denied"
        blocker_reasons = ["developer_authorization_denied"]
        effective_decision = "denied"
    else:
        authorization_status = "pending"
        blocker_reasons = ["developer_authorization_not_approved"]
        effective_decision = "pending"

    return {
        "node_id": node_id,
        "authorization_record_present": True,
        "authorization_decision": effective_decision,
        "authorization_status": authorization_status,
        "activation_authorized_for_gate": authorization_status == "approved_for_gate_review",
        "target_candidate": {
            "from_package_id": target_candidate.get("from_package_id"),
            "from_schema_version": target_candidate.get("from_schema_version"),
            "to_package_id": target_package_id,
            "to_schema_version": target_schema_version,
            "readiness_status": (readiness_node or {}).get("status"),
        },
        "approval_record": {
            "approved_by": (approval or {}).get("approved_by"),
            "approved_at": (approval or {}).get("approved_at"),
            "notes": (approval or {}).get("notes"),
            "target_match": approval_matches_target if approval is not None else None,
        },
        "blocking_reasons": blocker_reasons,
        "required_next_actions": [
            "developer_must_explicitly_approve_target_v02_runtime"
            if authorization_status == "pending"
            else "keep_authorization_record_attached_to_activation_gate",
            "activation_gate_must_still_check_visual_candidate_isolation",
            "activation_gate_must_still_require_backend_frontend_contract_update",
            "activation_gate_must_still_require_post_activation_evidence",
        ],
        "safety": {
            "authorization_is_not_activation": True,
            "runtime_activation_allowed": False,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_performed": False,
            "provider_call_count_by_report": 0,
            "world_state_mutation_performed": False,
        },
    }


def build_report(approval_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    readiness_report = load_json(READINESS_REPORT)
    gate_report = load_json(ACTIVATION_GATE_REPORT)
    readiness_by_node = index_by_node(as_list(readiness_report.get("nodes")))
    gate_by_node = index_by_node(as_list(gate_report.get("decisions")))
    approvals_by_node = normalize_plan(approval_plan)
    node_ids = sorted(
        set(readiness_by_node) | set(gate_by_node),
        key=lambda node: (NODE_SORT_ORDER.get(node, 99), node),
    )
    nodes = [
        build_node_authorization(
            node_id=node_id,
            readiness_node=readiness_by_node.get(node_id),
            gate_decision=gate_by_node.get(node_id),
            approval=approvals_by_node.get(node_id),
        )
        for node_id in node_ids
    ]
    status_counts = Counter(node.get("authorization_status") for node in nodes)
    approved_count = status_counts.get("approved_for_gate_review", 0)
    report_status = "authorized_for_gate_review" if approved_count == len(nodes) and nodes else "pending_developer_approval"
    if status_counts.get("denied"):
        report_status = "authorization_denied"
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_runtime_activation_authorization",
        "generated_at": "2026-07-05T00:00:00Z",
        "status": report_status,
        "inputs": {
            "readiness_report": str(READINESS_REPORT.relative_to(ROOT)),
            "activation_gate_report": str(ACTIVATION_GATE_REPORT.relative_to(ROOT)),
            "approval_plan_supplied": approval_plan is not None,
        },
        "scope": {
            "authorization_record_only": True,
            "read_model_only": True,
            "runtime_activation_allowed": False,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_performed": False,
            "provider_calls_allowed": False,
            "world_state_mutation_allowed": False,
        },
        "policy": [
            "Developer authorization is required before a v0.2 map runtime can be considered for default activation.",
            "Authorization is not activation and does not modify MapRuntimePackage, backend API, frontend runtime, or world state.",
            "Even an approved authorization must still pass activation gate checks, API/frontend contract updates, and post-activation evidence.",
        ],
        "summary": {
            "node_count": len(nodes),
            "approved_count": approved_count,
            "pending_count": status_counts.get("pending", 0),
            "denied_count": status_counts.get("denied", 0),
            "authorization_status_counts": dict(sorted(status_counts.items())),
            "activation_authorized_for_gate_count": sum(
                1 for node in nodes if node.get("activation_authorized_for_gate") is True
            ),
            "runtime_mutation_count_by_report": 0,
            "world_mutation_count_by_report": 0,
            "provider_call_count_by_report": 0,
        },
        "nodes": nodes,
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count_by_report": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_performed": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a MapRuntime activation authorization report.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to write report JSON.")
    parser.add_argument(
        "--approval-plan",
        type=Path,
        default=None,
        help="Optional local JSON approval plan. The default report records pending approvals only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    approval_plan = load_json(args.approval_plan) if args.approval_plan else None
    report = build_report(approval_plan)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote map runtime activation authorization report: {output}")
    print(f"- status: {report['status']}")
    print(f"- approved: {report['summary']['approved_count']}")
    print(f"- pending: {report['summary']['pending_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
