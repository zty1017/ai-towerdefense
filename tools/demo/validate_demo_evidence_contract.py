#!/usr/bin/env python3
"""Validate narrow demo evidence contracts that used to live in task-pack heredocs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


ContractValidator = Callable[[argparse.Namespace], dict[str, Any]]


def load_json(path: Path, *, label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist: {path}") from exc


def load_text(path: Path, *, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist: {path}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label}: expected {expected!r}, got {actual!r}")


def gates_by_id(report: dict[str, Any], *, label: str) -> dict[str, dict[str, Any]]:
    gates = report.get("gates")
    require(isinstance(gates, list), f"{label}.gates must be a list")
    result: dict[str, dict[str, Any]] = {}
    for gate in gates:
        require(isinstance(gate, dict), f"{label}.gates items must be objects")
        gate_id = gate.get("gate_id")
        require(isinstance(gate_id, str) and gate_id, f"{label}.gates item missing gate_id")
        result[gate_id] = gate
    return result


def require_readiness_report(report: dict[str, Any], *, label: str) -> None:
    require_equal(
        report.get("overall_status"),
        "ready_for_mvp_demo_with_known_limitations",
        f"{label}.overall_status",
    )
    summary = report.get("summary")
    require(isinstance(summary, dict), f"{label}.summary must be an object")
    require_equal(summary.get("blocking_gate_count"), 0, f"{label}.summary.blocking_gate_count")


def validate_demo_readiness_video_boundary(args: argparse.Namespace) -> dict[str, Any]:
    report = load_json(args.readiness_report, label="readiness report")
    evidence = load_json(args.evidence, label="evidence")
    require(isinstance(report, dict), "readiness report root must be an object")
    require(isinstance(evidence, dict), "evidence root must be an object")
    require_readiness_report(report, label="readiness_report")

    gate = gates_by_id(report, label="readiness_report").get("provider_video_boundary")
    require(isinstance(gate, dict), "readiness_report missing provider_video_boundary gate")
    require_equal(gate.get("status"), "passed_with_warnings", "provider_video_boundary.status")
    require_equal(gate.get("required_for_mvp_demo"), False, "provider_video_boundary.required_for_mvp_demo")
    metrics = gate.get("metrics")
    require(isinstance(metrics, dict), "provider_video_boundary.metrics must be an object")
    require_equal(
        metrics.get("provider_call_performed"),
        False,
        "provider_video_boundary.metrics.provider_call_performed",
    )

    readiness = evidence.get("mvp_demo_readiness")
    require(isinstance(readiness, dict), "evidence.mvp_demo_readiness must be an object")
    evidence_gate = gates_by_id(readiness, label="evidence.mvp_demo_readiness").get(
        "provider_video_boundary"
    )
    require(isinstance(evidence_gate, dict), "evidence missing provider_video_boundary gate")
    require_equal(
        evidence_gate.get("status"),
        "passed_with_warnings",
        "evidence.provider_video_boundary.status",
    )
    summary = readiness.get("summary")
    require(isinstance(summary, dict), "evidence.mvp_demo_readiness.summary must be an object")
    require_equal(
        summary.get("provider_call_count_by_report"),
        0,
        "evidence.mvp_demo_readiness.summary.provider_call_count_by_report",
    )
    return {"contract": args.contract, "status": "passed", "gate": "provider_video_boundary"}


def validate_map_runtime_v02(args: argparse.Namespace) -> dict[str, Any]:
    evidence = load_json(args.evidence, label="evidence")
    require(isinstance(evidence, dict), "evidence root must be an object")
    v02 = evidence.get("map_runtime_packages_v02")
    require(isinstance(v02, dict), "evidence.map_runtime_packages_v02 must be an object")
    expected = {
        "package_count": 3,
        "total_resource_node_count": 3,
        "total_hazard_zone_count": 3,
        "total_defense_anchor_count": 3,
        "total_blocked_area_count": 3,
    }
    for key, value in expected.items():
        require_equal(v02.get(key), value, f"map_runtime_packages_v02.{key}")
    return {"contract": args.contract, "status": "passed", **expected}


def validate_map_v02_api(args: argparse.Namespace) -> dict[str, Any]:
    evidence = load_json(args.evidence, label="evidence")
    require(isinstance(evidence, dict), "evidence root must be an object")
    backend = evidence.get("backend_api_evidence")
    require(isinstance(backend, dict), "evidence.backend_api_evidence must be an object")
    api = backend.get("map_v02_preview")
    require(isinstance(api, dict), "backend_api_evidence.map_v02_preview must be an object")
    require_equal(api.get("status"), "passed", "map_v02_preview.status")
    require_equal(api.get("node_count"), 3, "map_v02_preview.node_count")
    require_equal(
        api.get("default_runtime_v01_preserved_count"),
        3,
        "map_v02_preview.default_runtime_v01_preserved_count",
    )
    safety = api.get("safety")
    require(isinstance(safety, dict), "map_v02_preview.safety must be an object")
    require_equal(safety.get("provider_call_count"), 0, "map_v02_preview.safety.provider_call_count")
    require_equal(api.get("runtime_activation_allowed"), False, "map_v02_preview.runtime_activation_allowed")
    return {"contract": args.contract, "status": "passed", "node_count": 3}


def validate_mvp_demo_readiness(args: argparse.Namespace) -> dict[str, Any]:
    report = load_json(args.readiness_report, label="readiness report")
    evidence = load_json(args.evidence, label="evidence")
    require(isinstance(report, dict), "readiness report root must be an object")
    require(isinstance(evidence, dict), "evidence root must be an object")
    require_readiness_report(report, label="readiness_report")
    summary = report.get("summary")
    require(isinstance(summary, dict), "readiness_report.summary must be an object")
    require_equal(
        summary.get("required_gate_passed_or_expected_count"),
        summary.get("required_gate_count"),
        "readiness_report.summary.required_gate_passed_or_expected_count",
    )

    readiness = evidence.get("mvp_demo_readiness")
    require(isinstance(readiness, dict), "evidence.mvp_demo_readiness must be an object")
    require_readiness_report(readiness, label="evidence.mvp_demo_readiness")
    evidence_summary = readiness.get("summary")
    require(isinstance(evidence_summary, dict), "evidence.mvp_demo_readiness.summary must be an object")
    require_equal(
        evidence_summary.get("provider_call_count_by_report"),
        0,
        "evidence.mvp_demo_readiness.summary.provider_call_count_by_report",
    )
    return {"contract": args.contract, "status": "passed"}


def validate_mvp_primary_api_flow(args: argparse.Namespace) -> dict[str, Any]:
    evidence = load_json(args.evidence, label="evidence")
    require(isinstance(evidence, dict), "evidence root must be an object")
    backend = evidence.get("backend_api_evidence")
    require(isinstance(backend, dict), "evidence.backend_api_evidence must be an object")
    flow = backend.get("mvp_primary_flow")
    require(isinstance(flow, dict), "backend_api_evidence.mvp_primary_flow must be an object")
    require_equal(flow.get("status"), "passed", "mvp_primary_flow.status")
    require_equal(flow.get("passed_step_count"), flow.get("step_count"), "mvp_primary_flow.passed_step_count")
    require_equal(flow.get("step_count"), 21, "mvp_primary_flow.step_count")
    research = flow.get("research")
    require(isinstance(research, dict), "mvp_primary_flow.research must be an object")
    require_equal(research.get("job_status"), "completed", "mvp_primary_flow.research.job_status")
    safety = flow.get("safety")
    require(isinstance(safety, dict), "mvp_primary_flow.safety must be an object")
    require_equal(safety.get("provider_call_count"), 0, "mvp_primary_flow.safety.provider_call_count")
    require_equal(
        safety.get("runtime_activation_mutation_count"),
        0,
        "mvp_primary_flow.safety.runtime_activation_mutation_count",
    )
    return {"contract": args.contract, "status": "passed", "step_count": 21}


def validate_render_plan_v02_semantics(args: argparse.Namespace) -> dict[str, Any]:
    evidence = load_json(args.evidence, label="evidence")
    require(isinstance(evidence, dict), "evidence root must be an object")
    assets = evidence.get("assets_and_media")
    require(isinstance(assets, dict), "evidence.assets_and_media must be an object")
    references = assets.get("map_visual_reference")
    require(isinstance(references, dict), "assets_and_media.map_visual_reference must be an object")
    summary = references.get("procedural_map_previews_v02")
    require(isinstance(summary, dict), "map_visual_reference.procedural_map_previews_v02 must be an object")
    require_equal(summary.get("report_count"), 3, "procedural_map_previews_v02.report_count")
    require_equal(summary.get("ready_count"), 3, "procedural_map_previews_v02.ready_count")
    samples = summary.get("preview_samples")
    require(isinstance(samples, list) and samples, "procedural_map_previews_v02.preview_samples must be a list")
    for index, sample in enumerate(samples):
        require(isinstance(sample, dict), f"preview_samples[{index}] must be an object")
        render = sample.get("render_summary")
        require(isinstance(render, dict), f"preview_samples[{index}].render_summary must be an object")
        for key in ("resource_node_count", "hazard_zone_count", "defense_anchor_count", "blocked_area_count"):
            require_equal(render.get(key), 1, f"preview_samples[{index}].render_summary.{key}")
    return {"contract": args.contract, "status": "passed", "sample_count": len(samples)}


def validate_render_preview_export(args: argparse.Namespace) -> dict[str, Any]:
    evidence = load_json(args.evidence, label="evidence")
    summary_text = load_text(args.summary, label="summary")
    require(isinstance(evidence, dict), "evidence root must be an object")
    assets = evidence.get("assets_and_media")
    require(isinstance(assets, dict), "evidence.assets_and_media must be an object")
    references = assets.get("map_visual_reference")
    require(isinstance(references, dict), "assets_and_media.map_visual_reference must be an object")
    previews = references.get("procedural_map_previews")
    require(isinstance(previews, dict), "map_visual_reference.procedural_map_previews must be an object")
    require_equal(previews.get("report_count"), 3, "procedural_map_previews.report_count")
    require_equal(previews.get("ready_count"), 3, "procedural_map_previews.ready_count")
    require_equal(
        previews.get("runtime_activation_policy"),
        "review_only_not_player_runtime",
        "procedural_map_previews.runtime_activation_policy",
    )
    require("地图 RenderPlan 离线预览" in summary_text, "summary missing RenderPlan preview section")
    return {"contract": args.contract, "status": "passed"}


CONTRACTS: dict[str, ContractValidator] = {
    "demo_readiness_video_boundary": validate_demo_readiness_video_boundary,
    "map_runtime_v02": validate_map_runtime_v02,
    "map_v02_api": validate_map_v02_api,
    "mvp_demo_readiness": validate_mvp_demo_readiness,
    "mvp_primary_api_flow": validate_mvp_primary_api_flow,
    "render_plan_v02_semantics": validate_render_plan_v02_semantics,
    "render_preview_export": validate_render_preview_export,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", choices=sorted(CONTRACTS), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--summary", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.contract in {"demo_readiness_video_boundary", "mvp_demo_readiness"} and not args.readiness_report:
        print("--readiness-report is required for this contract", file=sys.stderr)
        return 2
    if args.contract == "render_preview_export" and not args.summary:
        print("--summary is required for render_preview_export", file=sys.stderr)
        return 2
    try:
        summary = CONTRACTS[args.contract](args)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise validation failures.
        print(f"demo evidence contract validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "demo evidence contract validation passed: "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
