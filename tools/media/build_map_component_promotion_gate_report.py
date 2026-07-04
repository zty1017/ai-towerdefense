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
    return path.resolve().relative_to(ROOT).as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def decision_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        candidate.get("candidate_kind") == "generated_candidate"
        and candidate.get("review_status") == "passed"
        and candidate.get("promotion_recommendation") == "eligible_for_promotion"
        and candidate.get("promotion_allowed_now") is True
    )
    if allowed:
        decision = "allowed"
        reason = "Generated candidate passed review and is eligible for a future manifest replacement build."
    elif candidate.get("candidate_kind") == "baseline_fixture_candidate":
        decision = "blocked_no_generated_candidate"
        reason = "Only deterministic SVG baseline fixture is present; no generated candidate may replace baseline."
    else:
        decision = "blocked_review_failed"
        reason = "Generated candidate is not fully reviewed and cannot be promoted."
    return {
        "component_id": candidate.get("component_id"),
        "candidate_id": candidate.get("candidate_id"),
        "candidate_kind": candidate.get("candidate_kind"),
        "decision": decision,
        "promotion_allowed": allowed,
        "baseline_preserved": not allowed,
        "reason": reason,
        "required_before_future_promotion": FUTURE_PROMOTION_GATES,
    }


def build_report(
    candidate_review_path: Path,
    manifest_path: Path,
    *,
    output_path: Path,
    created_at: str | None,
) -> dict[str, Any]:
    candidate_review = as_obj(load_json(candidate_review_path))
    manifest = as_obj(load_json(manifest_path))
    decisions = [
        decision_for_candidate(candidate)
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
        "source_manifest_path": rel(manifest_path),
        "status": "blocked" if blocked_count else "passed",
        "usage_policy": USAGE_POLICY,
        "summary": {
            "candidate_count": len(decisions),
            "generated_candidate_count": generated_count,
            "promotion_allowed_count": allowed_count,
            "promotion_blocked_count": blocked_count,
            "baseline_preserved_count": baseline_preserved_count,
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
    parser.add_argument("--candidate-review", default=str(DEFAULT_CANDIDATE_REVIEW))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    candidate_review_path = resolve_path(args.candidate_review)
    manifest_path = resolve_path(args.manifest)
    output_path = resolve_path(args.output)
    report = build_report(
        candidate_review_path,
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
