#!/usr/bin/env python3
"""Build a deterministic MapRuntime promotion readiness report.

The report is a read model for map compilation evidence. It does not activate
MapRuntimePackage v0.2 preview packages and does not update player runtime
fixtures. It only answers which nodes are structurally close to promotion and
which gates still block activation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    ROOT / "examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json"
)
MAP_RUNTIME_DIR = ROOT / "examples/map_runtime_packages"
MAP_RUNTIME_V02_DIR = ROOT / "examples/map_runtime_packages_v02"
MAP_RENDER_PLAN_V02_DIR = ROOT / "examples/map_render_plans_v02"
SEMANTIC_REPORT_V02_DIR = ROOT / "examples/semantic_visual_consistency_reports_v02"
MAP_COMPILE_DIR = ROOT / "examples/map_compile_packages"
MAP_VISUAL_PROMOTION_GATE = (
    ROOT / "examples/review_packs/map_visual_promotion_gate_report.v0.1.json"
)

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


def gate(gate_id: str, status: str, summary: str) -> dict[str, str]:
    return {"gate_id": gate_id, "status": status, "summary": summary}


def count_strong_semantics(package: dict[str, Any]) -> dict[str, int]:
    return {
        "resource_nodes": len(as_list(package.get("resource_nodes"))),
        "hazard_zones": len(as_list(package.get("hazard_zones"))),
        "defense_anchors": len(as_list(package.get("defense_anchors"))),
        "blocked_areas": len(as_list(package.get("blocked_areas"))),
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


def build_node_report(
    node_id: str,
    runtime_v01: dict[str, Any] | None,
    runtime_v02: dict[str, Any] | None,
    render_plan: dict[str, Any] | None,
    semantic_report: dict[str, Any] | None,
    compile_package: dict[str, Any] | None,
    visual_gate: dict[str, Any],
) -> dict[str, Any]:
    gates: list[dict[str, str]] = []

    if runtime_v01:
        gates.append(
            gate(
                "default_runtime_v01_preserved",
                "passed"
                if runtime_v01.get("schema_version") == "map_runtime_package.v0.1"
                else "failed",
                "Default player runtime remains MapRuntimePackage v0.1.",
            )
        )
    else:
        gates.append(
            gate(
                "default_runtime_v01_preserved",
                "failed",
                "Missing default MapRuntimePackage v0.1.",
            )
        )

    v02_validation = as_obj(runtime_v02.get("validation_report") if runtime_v02 else None)
    strong_counts = count_strong_semantics(runtime_v02 or {})
    if runtime_v02 and v02_validation.get("gate_status") == "passed":
        gates.append(
            gate(
                "v02_preview_semantics_available",
                "passed",
                "MapRuntimePackage v0.2 preview has explicit strong semantic extensions.",
            )
        )
    else:
        gates.append(
            gate(
                "v02_preview_semantics_available",
                "failed",
                "MapRuntimePackage v0.2 preview is missing or did not pass validation.",
            )
        )

    if runtime_v02 and all(value > 0 for value in strong_counts.values()):
        gates.append(
            gate(
                "strong_semantic_counts_nonzero",
                "passed",
                "Resource nodes, hazard zones, defense anchors, and blocked areas are present.",
            )
        )
    else:
        gates.append(
            gate(
                "strong_semantic_counts_nonzero",
                "warning",
                "One or more v0.2 strong semantic categories are absent.",
            )
        )

    render_validation = as_obj(render_plan.get("validation_report") if render_plan else None)
    render_matches_runtime = (
        bool(render_plan)
        and bool(runtime_v02)
        and render_plan.get("map_runtime_package_id") == runtime_v02.get("package_id")
    )
    if (
        render_plan
        and render_validation.get("gate_status") == "passed"
        and render_validation.get("runtime_truth_preserved") is True
        and render_matches_runtime
    ):
        gates.append(
            gate(
                "v02_render_plan_executable",
                "passed",
                "ProceduralMapRenderPlan v0.2 preview is executable and preserves runtime truth.",
            )
        )
    else:
        gates.append(
            gate(
                "v02_render_plan_executable",
                "failed",
                "Missing or invalid v0.2 render plan, or render plan does not target the v0.2 package.",
            )
        )

    semantic_summary = as_obj(semantic_report.get("summary") if semantic_report else None)
    if semantic_report and semantic_report.get("status") == "passed":
        gates.append(
            gate(
                "semantic_visual_consistency_passed",
                "passed",
                "SemanticVisualConsistencyReport passed with no blocking visual-semantic failures.",
            )
        )
    else:
        gates.append(
            gate(
                "semantic_visual_consistency_passed",
                "failed",
                "SemanticVisualConsistencyReport is missing or not passed.",
            )
        )

    compile_validation = as_obj(
        compile_package.get("validation_report") if compile_package else None
    )
    compile_status = compile_validation.get("gate_status")
    if (
        compile_package
        and compile_status in {"passed", "warning"}
        and compile_validation.get("runtime_truth_preserved") is True
        and compile_validation.get("player_visual_safe") is True
    ):
        gates.append(
            gate(
                "map_compile_package_safe",
                "warning" if compile_status == "warning" else "passed",
                "MapCompilePackage preserves runtime truth and marks player visual layer safe, with MVP warnings if present.",
            )
        )
    else:
        gates.append(
            gate(
                "map_compile_package_safe",
                "failed",
                "MapCompilePackage is missing or does not preserve runtime/player visual safety.",
            )
        )

    published_layers = [
        layer
        for layer in as_list(visual_gate.get("published_layers"))
        if isinstance(layer, dict)
    ]
    blocked_candidates = [
        candidate
        for candidate in as_list(visual_gate.get("blocked_candidates"))
        if isinstance(candidate, dict)
    ]
    layer_alignment_statuses = sorted(
        {
            str(layer.get("logic_alignment_status"))
            for layer in published_layers
            if layer.get("logic_alignment_status")
        }
    )
    if published_layers and not blocked_candidates:
        visual_status = "passed"
    elif published_layers:
        visual_status = "warning"
    else:
        visual_status = "failed"
    gates.append(
        gate(
            "published_visual_layer_isolated",
            visual_status,
            "Published player layer exists; rejected/review-only candidates remain isolated by the visual promotion gate."
            if published_layers
            else "No published player layer is registered for this node.",
        )
    )

    gates.append(
        gate(
            "activation_gate_required",
            "blocked",
            "No task has explicitly promoted v0.2 preview into the default player runtime.",
        )
    )

    status_counts = Counter(item["status"] for item in gates)
    if status_counts.get("failed"):
        node_status = "blocked_failed_gate"
    elif status_counts.get("blocked"):
        node_status = "promotion_candidate_activation_required"
    elif status_counts.get("warning"):
        node_status = "promotion_candidate_with_warnings"
    else:
        node_status = "promotion_candidate"

    blocking_reasons: list[str] = []
    for item in gates:
        if item["status"] in {"failed", "blocked"}:
            blocking_reasons.append(item["gate_id"])
    if blocked_candidates:
        blocking_reasons.append("review_only_or_rejected_visual_candidates_present")
    if any(status == "needs_overlay_correction" for status in layer_alignment_statuses):
        blocking_reasons.append("published_visual_layer_needs_overlay_correction")

    return {
        "node_id": node_id,
        "status": node_status,
        "readiness_gates": gates,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "runtime_v01": {
            "present": runtime_v01 is not None,
            "schema_version": (runtime_v01 or {}).get("schema_version"),
            "package_id": (runtime_v01 or {}).get("package_id"),
            "source_path": (runtime_v01 or {}).get("_source_path"),
            "path_route_count": len(as_list((runtime_v01 or {}).get("path_routes"))),
            "build_slot_count": len(as_list((runtime_v01 or {}).get("build_slots"))),
            "spawn_point_count": len(as_list((runtime_v01 or {}).get("spawn_points"))),
            "published_visual_layer_count": sum(
                1
                for layer in as_list((runtime_v01 or {}).get("visual_layers"))
                if isinstance(layer, dict)
                and layer.get("authority") == "published_visual_layer"
            ),
        },
        "runtime_v02_preview": {
            "present": runtime_v02 is not None,
            "schema_version": (runtime_v02 or {}).get("schema_version"),
            "package_id": (runtime_v02 or {}).get("package_id"),
            "source_path": (runtime_v02 or {}).get("_source_path"),
            "validation_gate_status": v02_validation.get("gate_status"),
            "runtime_loadable": v02_validation.get("runtime_loadable"),
            "strong_semantic_counts": strong_counts,
        },
        "render_plan_v02": {
            "present": render_plan is not None,
            "plan_id": (render_plan or {}).get("plan_id"),
            "source_path": (render_plan or {}).get("_source_path"),
            "target_package_id": (render_plan or {}).get("map_runtime_package_id"),
            "validation_gate_status": render_validation.get("gate_status"),
            "runtime_truth_preserved": render_validation.get("runtime_truth_preserved"),
            "player_default_safe": render_validation.get("player_default_safe"),
            "player_default_layer_count": len(
                as_list((render_plan or {}).get("player_default_layer_ids"))
            ),
            "debug_layer_count": len(as_list((render_plan or {}).get("debug_layer_ids"))),
        },
        "semantic_visual_consistency": {
            "present": semantic_report is not None,
            "report_id": (semantic_report or {}).get("report_id"),
            "source_path": (semantic_report or {}).get("_source_path"),
            "status": (semantic_report or {}).get("status"),
            "passed_count": semantic_summary.get("passed_count"),
            "warning_count": semantic_summary.get("warning_count"),
            "failed_count": semantic_summary.get("failed_count"),
        },
        "map_compile_package": {
            "present": compile_package is not None,
            "package_id": (compile_package or {}).get("package_id"),
            "source_path": (compile_package or {}).get("_source_path"),
            "validation_gate_status": compile_status,
            "runtime_truth_preserved": compile_validation.get("runtime_truth_preserved"),
            "player_visual_safe": compile_validation.get("player_visual_safe"),
            "painted_visual_status": as_obj(
                (compile_package or {}).get("painted_visual_layer")
            ).get("status"),
            "quality_gate_count": len(as_list((compile_package or {}).get("quality_gates"))),
        },
        "visual_promotion_gate": {
            "published_player_layer_count": len(published_layers),
            "blocked_candidate_count": len(blocked_candidates),
            "published_layer_alignment_statuses": layer_alignment_statuses,
            "blocked_reason_counts": dict(
                sorted(
                    Counter(
                        reason
                        for candidate in blocked_candidates
                        for reason in as_list(candidate.get("blocking_reasons"))
                    ).items()
                )
            ),
        },
        "activation_policy": {
            "runtime_activation_allowed": False,
            "default_runtime_mutation_allowed": False,
            "required_next_gate": "explicit_map_runtime_activation_gate",
        },
    }


def build_report() -> dict[str, Any]:
    runtime_v01 = index_by_node(sorted(MAP_RUNTIME_DIR.glob("*.map_runtime_package.json")))
    runtime_v02 = index_by_node(
        sorted(MAP_RUNTIME_V02_DIR.glob("*.map_runtime_package_v02.json"))
    )
    render_plans = index_by_node(
        sorted(MAP_RENDER_PLAN_V02_DIR.glob("*.procedural_map_render_plan.json"))
    )
    semantic_reports = index_by_node(
        sorted(SEMANTIC_REPORT_V02_DIR.glob("*.semantic_visual_consistency_report.json"))
    )
    compile_packages = index_by_node(
        sorted(MAP_COMPILE_DIR.glob("*.map_compile_package.json"))
    )
    visual_gate_report = load_json(MAP_VISUAL_PROMOTION_GATE)
    visual_by_node = visual_gate_index(visual_gate_report)

    node_ids = sorted(
        set(runtime_v01)
        | set(runtime_v02)
        | set(render_plans)
        | set(semantic_reports)
        | set(compile_packages),
        key=lambda node: (NODE_SORT_ORDER.get(node, 99), node),
    )
    nodes = [
        build_node_report(
            node_id,
            runtime_v01.get(node_id),
            runtime_v02.get(node_id),
            render_plans.get(node_id),
            semantic_reports.get(node_id),
            compile_packages.get(node_id),
            visual_by_node.get(node_id, {}),
        )
        for node_id in node_ids
    ]

    status_counts = Counter(node.get("status") for node in nodes)
    gate_status_counts = Counter(
        gate_item.get("status")
        for node in nodes
        for gate_item in as_list(node.get("readiness_gates"))
        if isinstance(gate_item, dict)
    )
    blocker_counts = Counter(
        reason
        for node in nodes
        for reason in as_list(node.get("blocking_reasons"))
    )
    promotion_candidate_count = sum(
        1
        for node in nodes
        if str(node.get("status")).startswith("promotion_candidate")
    )

    visual_summary = as_obj(visual_gate_report.get("summary"))
    overall_status = (
        "promotion_candidates_activation_required"
        if nodes and promotion_candidate_count == len(nodes)
        else "blocked_until_inputs_repaired"
    )

    return {
        "schema_version": "map_runtime_promotion_readiness_report.v0.1",
        "report_id": "mvp_map_runtime_promotion_readiness",
        "generated_at": "2026-07-04T00:00:00Z",
        "status": overall_status,
        "inputs": {
            "map_runtime_package_dir": str(MAP_RUNTIME_DIR.relative_to(ROOT)),
            "map_runtime_package_v02_dir": str(MAP_RUNTIME_V02_DIR.relative_to(ROOT)),
            "map_render_plan_v02_dir": str(MAP_RENDER_PLAN_V02_DIR.relative_to(ROOT)),
            "semantic_visual_consistency_report_v02_dir": str(
                SEMANTIC_REPORT_V02_DIR.relative_to(ROOT)
            ),
            "map_compile_package_dir": str(MAP_COMPILE_DIR.relative_to(ROOT)),
            "map_visual_promotion_gate_report": str(
                MAP_VISUAL_PROMOTION_GATE.relative_to(ROOT)
            ),
        },
        "scope": {
            "read_model_only": True,
            "review_only_inputs_allowed": True,
            "runtime_activation_allowed": False,
            "default_runtime_mutation_allowed": False,
            "world_state_mutation_allowed": False,
            "provider_calls_allowed": False,
            "player_runtime_update_performed": False,
        },
        "policy": [
            "MapRuntimePackage v0.1 remains the default player runtime until a separate activation gate promotes another package.",
            "MapRuntimePackage v0.2 preview, RenderPlan, and semantic reports can prove readiness but cannot activate runtime by themselves.",
            "Review-only, rejected, or awaiting-provider visual candidates must stay isolated from published player layers.",
            "Warnings are acceptable for MVP evidence only when runtime truth is preserved and activation remains blocked.",
        ],
        "summary": {
            "node_count": len(nodes),
            "promotion_candidate_count": promotion_candidate_count,
            "activation_allowed_count": 0,
            "default_runtime_v01_count": len(runtime_v01),
            "v02_preview_count": len(runtime_v02),
            "v02_render_plan_count": len(render_plans),
            "semantic_report_count": len(semantic_reports),
            "map_compile_package_count": len(compile_packages),
            "status_counts": dict(sorted(status_counts.items())),
            "gate_status_counts": dict(sorted(gate_status_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "published_player_layer_count": visual_summary.get(
                "published_player_layer_count"
            ),
            "blocked_visual_candidate_count": visual_summary.get(
                "blocked_candidate_count"
            ),
            "visual_promotion_violation_count": visual_summary.get("violation_count"),
            "provider_call_count_by_report": 0,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
        },
        "nodes": nodes,
        "next_required_gates": [
            {
                "gate_id": "explicit_map_runtime_activation_gate",
                "required": True,
                "summary": "A later task must explicitly decide whether v0.2 semantics become default runtime, update API/frontend contracts, and rerun visual/API/browser evidence.",
            },
            {
                "gate_id": "visual_model_or_human_review_for_published_layer",
                "required": True,
                "summary": "Published visual layers still need stronger visual review before they can be treated as final art rather than MVP-safe presentation.",
            },
        ],
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count_by_report": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
            "player_runtime_update_performed": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a map runtime promotion readiness report."
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote map runtime promotion readiness report: {output}")
    print(
        "status="
        f"{report['status']} nodes={report['summary']['node_count']} "
        f"promotion_candidates={report['summary']['promotion_candidate_count']} "
        f"activation_allowed={report['summary']['activation_allowed_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
