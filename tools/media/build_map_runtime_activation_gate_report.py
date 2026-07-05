#!/usr/bin/env python3
"""Build the explicit MapRuntime activation gate report.

This report is deliberately conservative: it may identify v0.2 map runtime
packages as activation candidates, but it never mutates the default player
runtime and never treats review-only evidence as activated content.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_runtime_activation_gate_report.v0.1.json"
READINESS_REPORT = ROOT / "examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json"
VISUAL_PROMOTION_GATE_REPORT = ROOT / "examples/review_packs/map_visual_promotion_gate_report.v0.1.json"
ACTIVATION_AUTHORIZATION_REPORT = ROOT / "examples/review_packs/map_runtime_activation_authorization_report.v0.1.json"
MAP_V02_API_SMOKE_REPORT = ROOT / "examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json"
MAP_RUNTIME_DIR = ROOT / "examples/map_runtime_packages"
MAP_RUNTIME_V02_DIR = ROOT / "examples/map_runtime_packages_v02"
FRONTEND_APP = ROOT / "frontend/app.js"
FRONTEND_VISUAL_CONTRACT = ROOT / "tools/frontend/validate_battle_visual_contract.py"


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


def index_by_node(paths: list[Path]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for path in paths:
        data = load_json(path)
        node_id = data.get("node_id")
        if isinstance(node_id, str) and node_id:
            data["_source_path"] = str(path.relative_to(ROOT))
            indexed[node_id] = data
    return indexed


def check(check_id: str, status: str, summary: str) -> dict[str, str]:
    return {"check_id": check_id, "status": status, "summary": summary}


def frontend_v02_contract_prepared() -> dict[str, Any]:
    app = FRONTEND_APP.read_text(encoding="utf-8") if FRONTEND_APP.exists() else ""
    validator = (
        FRONTEND_VISUAL_CONTRACT.read_text(encoding="utf-8")
        if FRONTEND_VISUAL_CONTRACT.exists()
        else ""
    )
    checks = {
        "resource_nodes_from_runtime": "mapRuntimePackage().resource_nodes" in app,
        "hazard_zones_from_runtime": "mapRuntimePackage().hazard_zones" in app,
        "defense_anchors_from_runtime": "mapRuntimePackage().defense_anchors" in app,
        "blocked_areas_from_runtime": "mapRuntimePackage().blocked_areas" in app,
        "strong_semantic_draw_hook": "drawMapRuntimeStrongSemantics(ctx)" in app,
        "hazards_bind_route_t": "zone.anchor_route_id" in app and "zone.path_t_range" in app,
        "preview_endpoint_forbidden": '"map-v02-preview"' not in app
        and '"map-v02-preview"' in validator,
        "opt_in_endpoint_forbidden": '"map-v02-opt-in-dry-run"' not in app
        and '"map-v02-opt-in-dry-run"' in validator,
    }
    return {
        "status": "pre_activation_ready" if all(checks.values()) else "missing",
        "checks": checks,
    }


def readiness_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node.get("node_id"): node
        for node in as_list(report.get("nodes"))
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }


def api_node_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node.get("node_id"): node
        for node in as_list(report.get("nodes"))
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }


def visual_gate_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    published_by_node: dict[str, list[dict[str, Any]]] = {}
    blocked_by_node: dict[str, list[dict[str, Any]]] = {}
    for layer in as_list(report.get("published_player_layers")):
        if not isinstance(layer, dict):
            continue
        node_id = layer.get("node_id")
        if isinstance(node_id, str) and node_id and node_id != "manifest":
            published_by_node.setdefault(node_id, []).append(layer)
    for candidate in as_list(report.get("blocked_candidates")):
        if not isinstance(candidate, dict):
            continue
        for node_id in as_list(candidate.get("node_ids")):
            if isinstance(node_id, str) and node_id:
                blocked_by_node.setdefault(node_id, []).append(candidate)
    return {
        node_id: {
            "published_layers": published_by_node.get(node_id, []),
            "blocked_candidates": blocked_by_node.get(node_id, []),
        }
        for node_id in sorted(set(published_by_node) | set(blocked_by_node))
    }


def authorization_index(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not report:
        return {}
    return {
        node.get("node_id"): node
        for node in as_list(report.get("nodes"))
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }


def build_node_decision(
    node_id: str,
    readiness_node: dict[str, Any] | None,
    api_node: dict[str, Any] | None,
    visual_node: dict[str, Any],
    runtime_v01: dict[str, Any] | None,
    runtime_v02: dict[str, Any] | None,
    authorization_node: dict[str, Any] | None,
    frontend_contract: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    blockers: list[str] = []

    if runtime_v01 and runtime_v01.get("schema_version") == "map_runtime_package.v0.1":
        checks.append(
            check(
                "default_runtime_v01_preserved",
                "passed",
                "Default player runtime package is still v0.1.",
            )
        )
    else:
        checks.append(
            check(
                "default_runtime_v01_preserved",
                "failed",
                "Default player runtime package is missing or not v0.1.",
            )
        )
        blockers.append("default_runtime_v01_not_preserved")

    readiness_status = (readiness_node or {}).get("status")
    if readiness_status == "promotion_candidate_activation_required":
        checks.append(
            check(
                "promotion_readiness_candidate",
                "passed",
                "Readiness report marks this node as a promotion candidate pending activation.",
            )
        )
    else:
        checks.append(
            check(
                "promotion_readiness_candidate",
                "failed",
                "Readiness report does not mark this node as an activation candidate.",
            )
        )
        blockers.append("readiness_not_candidate")

    if runtime_v02 and runtime_v02.get("schema_version") == "map_runtime_package.v0.2":
        checks.append(
            check(
                "target_v02_preview_present",
                "passed",
                "Target MapRuntimePackage v0.2 preview exists.",
            )
        )
    else:
        checks.append(
            check(
                "target_v02_preview_present",
                "failed",
                "Target MapRuntimePackage v0.2 preview is missing.",
            )
        )
        blockers.append("target_v02_preview_missing")

    api_safety = as_obj((api_node or {}).get("safety"))
    if (
        api_node
        and api_node.get("default_runtime_schema_version") == "map_runtime_package.v0.1"
        and int(api_node.get("default_runtime_v02_field_leak_count") or 0) == 0
        and api_safety.get("player_default_runtime_mutation") is False
    ):
        checks.append(
            check(
                "preview_api_keeps_default_runtime_safe",
                "passed",
                "Map v0.2 preview API proves default v0.1 runtime is preserved.",
            )
        )
    else:
        checks.append(
            check(
                "preview_api_keeps_default_runtime_safe",
                "failed",
                "Map v0.2 preview API evidence is missing or leaked v0.2 fields into default runtime.",
            )
        )
        blockers.append("preview_api_default_runtime_safety_missing")

    readiness_blockers = set(as_list((readiness_node or {}).get("blocking_reasons")))
    visual_blockers = [
        "published_visual_layer_needs_overlay_correction",
        "review_only_or_rejected_visual_candidates_present",
    ]
    present_visual_blockers = [
        reason for reason in visual_blockers if reason in readiness_blockers
    ]
    if present_visual_blockers:
        checks.append(
            check(
                "visual_blockers_resolved",
                "blocked",
                "Readiness still reports visual blockers that must be resolved before activation.",
            )
        )
        blockers.extend(present_visual_blockers)
    else:
        checks.append(
            check(
                "visual_blockers_resolved",
                "passed",
                "No readiness visual blockers are present.",
            )
        )

    blocked_candidates = [
        candidate
        for candidate in as_list(visual_node.get("blocked_candidates"))
        if isinstance(candidate, dict)
    ]
    if blocked_candidates:
        checks.append(
            check(
                "rejected_candidates_remain_isolated",
                "warning",
                "Rejected/review-only candidates remain isolated; activation must not reference them.",
            )
        )
    else:
        checks.append(
            check(
                "rejected_candidates_remain_isolated",
                "passed",
                "No rejected/review-only visual candidates are attached to this node.",
            )
        )

    authorization_status = (authorization_node or {}).get("authorization_status")
    authorization_target = as_obj((authorization_node or {}).get("target_candidate"))
    authorization_matches_target = (
        authorization_target.get("to_package_id") == (runtime_v02 or {}).get("package_id")
        and authorization_target.get("to_schema_version") == (runtime_v02 or {}).get("schema_version")
    )
    if (
        authorization_node
        and authorization_status == "approved_for_gate_review"
        and authorization_matches_target
        and authorization_node.get("activation_authorized_for_gate") is True
    ):
        checks.append(
            check(
                "explicit_developer_activation_approval",
                "passed",
                "Explicit developer authorization exists for this v0.2 target; remaining activation gates still apply.",
            )
        )
    elif authorization_node and authorization_status == "denied":
        checks.append(
            check(
                "explicit_developer_activation_approval",
                "blocked",
                "Developer authorization record exists and denies this v0.2 activation target.",
            )
        )
        blockers.append("explicit_developer_activation_denied")
    elif authorization_node:
        checks.append(
            check(
                "explicit_developer_activation_approval",
                "blocked",
                "Developer authorization record exists but has not approved this v0.2 activation target.",
            )
        )
        blockers.append("explicit_developer_activation_not_approved")
    else:
        checks.append(
            check(
                "explicit_developer_activation_approval",
                "blocked",
                "No explicit developer activation authorization record is present for this node.",
            )
        )
        blockers.append("explicit_developer_activation_approval_missing")

    frontend_contract_status = frontend_contract.get("status")
    if frontend_contract_status == "pre_activation_ready":
        checks.append(
            check(
                "frontend_v02_semantic_consumption_contract",
                "passed",
                "Frontend can consume v0.2 strong semantics from an activated MapRuntimePackage while keeping review-only endpoints out of the default player flow.",
            )
        )
    else:
        checks.append(
            check(
                "frontend_v02_semantic_consumption_contract",
                "blocked",
                "Frontend has not proven v0.2 strong semantic consumption from activated runtime packages.",
            )
        )
        blockers.append("frontend_v02_semantic_consumption_missing")

    checks.append(
        check(
            "api_frontend_contract_update",
            "blocked",
            "Default backend API still serves v0.1; frontend v0.2 semantic rendering is prewired, but making v0.2 default still requires an explicit backend selector and activated-default evidence.",
        )
    )
    blockers.append("api_frontend_contract_update_required")

    checks.append(
        check(
            "post_activation_evidence_required",
            "blocked",
            "Activation would require fresh API smoke, browser flow smoke, visual contract, and demo evidence suite.",
        )
    )
    blockers.append("post_activation_evidence_required")

    status_counts = Counter(item["status"] for item in checks)
    decision = "blocked"
    decision_reason = "blocked_pending_explicit_activation_authorization"
    if status_counts.get("failed"):
        decision_reason = "blocked_failed_activation_preconditions"
    elif "published_visual_layer_needs_overlay_correction" in present_visual_blockers:
        decision_reason = "blocked_visual_reconciliation_required"
    elif "review_only_or_rejected_visual_candidates_present" in present_visual_blockers:
        decision_reason = "blocked_review_only_candidate_isolation_required"

    required_next_actions: list[str] = []
    if "published_visual_layer_needs_overlay_correction" in present_visual_blockers:
        required_next_actions.append(
            "resolve_visual_overlay_correction_or_accept_programmatic_runtime_layer"
        )
    if "review_only_or_rejected_visual_candidates_present" in present_visual_blockers:
        required_next_actions.append(
            "keep_review_only_or_rejected_visual_candidates_isolated_or_clear_with_promotion_gate"
        )
    required_next_actions.extend(
        [
            "approve_or_deny_explicit_developer_activation_authorization",
            "update_backend_api_contract_if_v02_becomes_default",
            "revalidate_frontend_activated_runtime_contract_after_backend_selector",
            "rerun_api_visual_and_demo_evidence_after_activation_candidate_changes",
        ]
    )

    return {
        "node_id": node_id,
        "activation_decision": decision,
        "decision_reason": decision_reason,
        "target_candidate": {
            "from_package_id": (runtime_v01 or {}).get("package_id"),
            "from_schema_version": (runtime_v01 or {}).get("schema_version"),
            "to_package_id": (runtime_v02 or {}).get("package_id"),
            "to_schema_version": (runtime_v02 or {}).get("schema_version"),
            "readiness_status": readiness_status,
        },
        "checks": checks,
        "blockers": sorted(set(blockers)),
        "safety": {
            "activation_allowed": False,
            "default_runtime_mutation_performed": False,
            "world_state_mutation_performed": False,
            "provider_call_count_by_gate": 0,
            "authorization_record_present": bool(authorization_node),
            "authorization_status": authorization_status,
            "frontend_v02_contract_status": frontend_contract_status,
        },
        "required_next_actions": required_next_actions,
    }


def build_report() -> dict[str, Any]:
    readiness_report = load_json(READINESS_REPORT)
    visual_report = load_json(VISUAL_PROMOTION_GATE_REPORT)
    api_report = load_json(MAP_V02_API_SMOKE_REPORT)
    authorization_report = (
        load_json(ACTIVATION_AUTHORIZATION_REPORT)
        if ACTIVATION_AUTHORIZATION_REPORT.exists()
        else None
    )
    runtime_v01 = index_by_node(sorted(MAP_RUNTIME_DIR.glob("*.map_runtime_package.json")))
    runtime_v02 = index_by_node(
        sorted(MAP_RUNTIME_V02_DIR.glob("*.map_runtime_package_v02.json"))
    )
    readiness_by_node = readiness_index(readiness_report)
    api_by_node = api_node_index(api_report)
    visual_by_node = visual_gate_index(visual_report)
    authorization_by_node = authorization_index(authorization_report)
    frontend_contract = frontend_v02_contract_prepared()

    node_ids = sorted(
        set(runtime_v01) | set(runtime_v02) | set(readiness_by_node) | set(api_by_node),
        key=lambda node: (NODE_SORT_ORDER.get(node, 99), node),
    )
    decisions = [
        build_node_decision(
            node_id,
            readiness_by_node.get(node_id),
            api_by_node.get(node_id),
            visual_by_node.get(node_id, {}),
            runtime_v01.get(node_id),
            runtime_v02.get(node_id),
            authorization_by_node.get(node_id),
            frontend_contract,
        )
        for node_id in node_ids
    ]

    decision_counts = Counter(item.get("activation_decision") for item in decisions)
    reason_counts = Counter(item.get("decision_reason") for item in decisions)
    blocker_counts = Counter(
        blocker for item in decisions for blocker in as_list(item.get("blockers"))
    )
    check_status_counts = Counter(
        check_item.get("status")
        for item in decisions
        for check_item in as_list(item.get("checks"))
        if isinstance(check_item, dict)
    )
    activation_allowed_count = sum(
        1 for item in decisions if item.get("activation_decision") == "allowed"
    )

    return {
        "schema_version": "map_runtime_activation_gate_report.v0.1",
        "report_id": "mvp_map_runtime_activation_gate",
        "generated_at": "2026-07-04T00:00:00Z",
        "status": "blocked",
        "inputs": {
            "readiness_report": str(READINESS_REPORT.relative_to(ROOT)),
            "visual_promotion_gate_report": str(
                VISUAL_PROMOTION_GATE_REPORT.relative_to(ROOT)
            ),
            "activation_authorization_report": str(
                ACTIVATION_AUTHORIZATION_REPORT.relative_to(ROOT)
            )
            if authorization_report
            else None,
            "map_v02_preview_api_smoke_report": str(
                MAP_V02_API_SMOKE_REPORT.relative_to(ROOT)
            ),
            "map_runtime_package_dir": str(MAP_RUNTIME_DIR.relative_to(ROOT)),
            "map_runtime_package_v02_dir": str(MAP_RUNTIME_V02_DIR.relative_to(ROOT)),
        },
        "scope": {
            "gate_only": True,
            "read_model_only": True,
            "runtime_activation_allowed": False,
            "default_runtime_mutation_allowed": False,
            "default_runtime_mutation_performed": False,
            "backend_api_contract_mutation_performed": False,
            "frontend_contract_mutation_performed": False,
            "provider_calls_allowed": False,
            "world_state_mutation_allowed": False,
        },
        "policy": [
            "Readiness is not activation.",
            "A v0.2 preview package can become the default player runtime only after explicit developer authorization and fresh API/frontend/evidence validation.",
            "This report may block activation but must not mutate MapRuntimePackage, backend routes, frontend runtime behavior, or world state.",
        ],
        "summary": {
            "node_count": len(decisions),
            "activation_allowed_count": activation_allowed_count,
            "activation_blocked_count": decision_counts.get("blocked", 0),
            "decision_counts": dict(sorted(decision_counts.items())),
            "decision_reason_counts": dict(sorted(reason_counts.items())),
            "check_status_counts": dict(sorted(check_status_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "readiness_status": readiness_report.get("status"),
            "readiness_promotion_candidate_count": as_obj(
                readiness_report.get("summary")
            ).get("promotion_candidate_count"),
            "visual_promotion_violation_count": as_obj(visual_report.get("summary")).get(
                "violation_count"
            ),
            "authorization_report_status": (authorization_report or {}).get("status"),
            "authorization_status_counts": as_obj(
                as_obj((authorization_report or {}).get("summary")).get(
                    "authorization_status_counts"
                )
            ),
            "authorization_approved_count": as_obj(
                (authorization_report or {}).get("summary")
            ).get("approved_count"),
            "api_default_runtime_v01_preserved_count": api_report.get(
                "default_runtime_v01_preserved_count"
            ),
            "frontend_v02_contract_status": frontend_contract.get("status"),
            "provider_call_count_by_report": 0,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
        },
        "decisions": decisions,
        "next_activation_task_contract": {
            "required_authorization_kind": "explicit_developer_activation_authorization",
            "must_update_backend_contract": True,
            "frontend_v02_semantic_consumption_prepared": frontend_contract.get("status")
            == "pre_activation_ready",
            "must_revalidate_frontend_contract_after_activation": True,
            "must_rerun_commands": [
                "python3 tools/dev/check_map_v02_preview_api.py",
                "python3 tools/dev/check_mvp_primary_api_flow.py",
                "python3 tools/frontend/validate_battle_visual_contract.py",
                "python3 tools/demo/run_demo_evidence_suite.py --output-root /tmp/demo_evidence_suite_after_map_runtime_activation",
            ],
            "must_keep_default_runtime_v01_until_activation_allowed": True,
        },
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
    parser = argparse.ArgumentParser(description="Build the MapRuntime activation gate report.")
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote map runtime activation gate report: {output}")
    print(
        "status="
        f"{report['status']} nodes={report['summary']['node_count']} "
        f"allowed={report['summary']['activation_allowed_count']} "
        f"blocked={report['summary']['activation_blocked_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
