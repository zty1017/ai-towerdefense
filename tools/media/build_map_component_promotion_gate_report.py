#!/usr/bin/env python3
"""Build the MapComponent generated-candidate promotion gate report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_component_promotion_gate_report.v0.1"
DEFAULT_CANDIDATE_REVIEW = ROOT / "examples/review_packs/map_component_candidate_review_report.v0.1.json"
DEFAULT_VISUAL_QUALITY_REPORT = ROOT / "examples/review_packs/map_component_visual_quality_report.v0.1.json"
DEFAULT_MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_component_promotion_gate_report.v0.1.json"

USAGE_POLICY = [
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "baseline_preserved_until_generated_candidate_passes",
    "no_frontend_default_consumption",
    "no_manifest_or_style_pack_or_render_plan_mutation",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]
FUTURE_PROMOTION_GATES = [
    "generated candidate artifact imported as local reviewed media",
    "candidate review passed",
    "visual QA passed",
    "cutout and normalization passed",
    "MapStyleComponentBindingReport refreshed with accepted refs",
    "developer approves explicit manifest replacement build",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def visual_items_by_candidate_id(visual_quality_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("candidate_id") or ""): item
        for item in as_list(visual_quality_report.get("items"))
        if isinstance(item, dict)
    }


def visual_blocker_for_item(
    *,
    visual_quality_report: dict[str, Any],
    visual_item: dict[str, Any] | None,
) -> str | None:
    if visual_item is None:
        return "visual quality report has no matching generated candidate item"
    item_status = str(visual_item.get("review_status") or "")
    if visual_quality_report.get("status") == "awaiting_generated_candidates":
        return "visual quality report is awaiting generated candidates"
    if item_status in {"blocked_pending_quality_gates", "needs_review_unsupported_decode"}:
        return f"visual quality item is {item_status}"
    if item_status != "passed":
        return f"visual quality item is incomplete: {item_status}"
    return None


def decision_for_candidate(
    candidate: dict[str, Any],
    *,
    visual_quality_report: dict[str, Any],
    visual_items: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidate_allowed = (
        candidate.get("candidate_kind") == "generated_candidate"
        and candidate.get("review_status") == "passed"
        and candidate.get("promotion_recommendation") == "eligible_for_promotion"
        and candidate.get("promotion_allowed_now") is True
    )
    visual_required = candidate.get("candidate_kind") == "generated_candidate"
    visual_item = visual_items.get(str(candidate.get("candidate_id") or "")) if visual_required else None
    visual_blocker = (
        visual_blocker_for_item(
            visual_quality_report=visual_quality_report,
            visual_item=visual_item,
        )
        if visual_required
        else None
    )
    allowed = candidate_allowed and visual_blocker is None
    if allowed:
        decision = "allowed"
        reason = (
            "Generated candidate passed candidate review and visual quality gate; "
            "manifest replacement still requires a separate developer-approved build."
        )
    elif candidate.get("candidate_kind") == "baseline_fixture_candidate":
        decision = "blocked_no_generated_candidate"
        reason = "Only deterministic SVG baseline fixture is present; no generated candidate may replace baseline."
    elif candidate_allowed:
        decision = "blocked_visual_quality_incomplete"
        reason = f"Generated candidate cannot be promoted because {visual_blocker}."
    else:
        decision = "blocked_review_failed"
        if visual_blocker:
            reason = (
                "Generated candidate is blocked by candidate review and cannot be promoted; "
                f"visual quality gate is also not complete because {visual_blocker}."
            )
        else:
            reason = "Generated candidate is not fully reviewed and cannot be promoted."
    return {
        "component_id": candidate.get("component_id"),
        "candidate_id": candidate.get("candidate_id"),
        "candidate_kind": candidate.get("candidate_kind"),
        "decision": decision,
        "promotion_allowed": allowed,
        "baseline_preserved": not allowed,
        "reason": reason,
        "visual_quality_status": visual_quality_report.get("status"),
        "visual_quality_item_status": visual_item.get("review_status") if visual_item else None,
        "visual_quality_checked": visual_item is not None,
        "visual_quality_required": visual_required,
        "visual_quality_blocker": visual_blocker,
        "required_before_future_promotion": FUTURE_PROMOTION_GATES,
    }


def build_report(
    candidate_review_path: Path,
    visual_quality_report_path: Path,
    manifest_path: Path,
    *,
    output_path: Path,
    created_at: str | None,
) -> dict[str, Any]:
    candidate_review = as_obj(load_json(candidate_review_path))
    visual_quality_report = as_obj(load_json(visual_quality_report_path))
    manifest = as_obj(load_json(manifest_path))
    visual_items = visual_items_by_candidate_id(visual_quality_report)
    decisions = [
        decision_for_candidate(
            candidate,
            visual_quality_report=visual_quality_report,
            visual_items=visual_items,
        )
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict)
    ]
    decision_counts = Counter(str(decision.get("decision")) for decision in decisions)
    generated_count = len(
        [decision for decision in decisions if decision.get("candidate_kind") == "generated_candidate"]
    )
    allowed_count = len([decision for decision in decisions if decision.get("promotion_allowed") is True])
    blocked_count = len(decisions) - allowed_count
    baseline_preserved_count = len([decision for decision in decisions if decision.get("baseline_preserved") is True])
    blocked_reasons = sorted(
        {
            str(decision.get("reason"))
            for decision in decisions
            if decision.get("promotion_allowed") is not True
        }
    )
    if not blocked_reasons:
        blocked_reasons = ["No blocking reasons."]
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "map_component_promotion_gate_report_v0_1",
        "created_at": created_at
        or str(candidate_review.get("created_at") or manifest.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_candidate_review_report_path": rel(candidate_review_path),
        "source_visual_quality_report_path": rel(visual_quality_report_path),
        "source_manifest_path": rel(manifest_path),
        "status": "blocked" if blocked_count else "passed",
        "usage_policy": USAGE_POLICY,
        "summary": {
            "candidate_count": len(decisions),
            "generated_candidate_count": generated_count,
            "promotion_allowed_count": allowed_count,
            "promotion_blocked_count": blocked_count,
            "baseline_preserved_count": baseline_preserved_count,
            "visual_quality_report_status": visual_quality_report.get("status"),
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "decisions": decisions,
        "blocked_reasons": blocked_reasons,
        "runtime_effect": {
            "manifest_replacement_written": False,
            "style_pack_modified": False,
            "render_plan_modified": False,
            "frontend_default_modified": False,
            "runtime_map_truth_modified": False,
        },
        "validation": {
            "validator": "tools/media/validate_map_component_promotion_gate_report.py",
            "commands": [
                f"python3 tools/media/validate_map_component_promotion_gate_report.py {rel(output_path)}"
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapComponentPromotionGateReport v0.1.")
    parser.add_argument(
        "--candidate-review",
        default=None,
        help=(
            "Candidate review report path. Defaults to the source_candidate_review_report_path "
            "declared by --visual-quality-report, or the canonical example when absent."
        ),
    )
    parser.add_argument("--visual-quality-report", default=str(DEFAULT_VISUAL_QUALITY_REPORT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    visual_quality_report_path = resolve_path(args.visual_quality_report)
    if args.candidate_review:
        candidate_review_path = resolve_path(args.candidate_review)
    else:
        visual_quality_report = as_obj(load_json(visual_quality_report_path))
        source_candidate_review = visual_quality_report.get("source_candidate_review_report_path")
        if isinstance(source_candidate_review, str) and source_candidate_review.strip():
            candidate_review_path = resolve_path(source_candidate_review)
        else:
            candidate_review_path = DEFAULT_CANDIDATE_REVIEW
    manifest_path = resolve_path(args.manifest)
    output_path = resolve_path(args.output)
    report = build_report(
        candidate_review_path,
        visual_quality_report_path,
        manifest_path,
        output_path=output_path,
        created_at=args.created_at,
    )
    write_json(output_path, report)
    print(f"OK: wrote {output_path}")
    print(f"- status: {report['status']}")
    print(f"- promotion_allowed_count: {report['summary']['promotion_allowed_count']}")
    print(f"- baseline_preserved_count: {report['summary']['baseline_preserved_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
