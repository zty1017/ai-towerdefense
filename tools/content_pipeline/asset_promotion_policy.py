#!/usr/bin/env python3
"""Decide whether a compiled asset can be delivered to the player.

This policy separates gameplay deliverability from media quality:
- gameplay_core must pass validation/simulation guardrails
- media can promote the asset to runtime_ready
- media failure should fall back to deterministic visuals when gameplay is good
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROMOTION_VERSION = "asset_promotion_policy.v0.1"
SEVERE_SIMULATION_FLAGS = {
    "no_direct_impact",
    "intel_asset_without_intel_effect",
}
REVIEW_SIMULATION_FLAGS = {
    "control_may_be_too_strong",
    "control_has_weak_cost",
    "possibly_underpriced",
    "high_cost_efficiency",
    "high_power_demand",
}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def asset_type(candidate: dict[str, Any]) -> str:
    gameplay = as_obj(candidate.get("gameplay"))
    return str(gameplay.get("asset_type", "unknown"))


def candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("id", "unknown_candidate"))


def validation_passed(validation: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if validation is None:
        return False, ["missing_validation_result"]
    errors = as_list(validation.get("errors"))
    if validation.get("status") == "passed" and not errors:
        return True, []
    return False, ["candidate_validation_failed", *[str(error) for error in errors[:5]]]


def gameplay_core_state(
    validation: dict[str, Any] | None,
    simulation: dict[str, Any] | None,
    candidate_score: dict[str, Any] | None,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    ok, validation_reasons = validation_passed(validation)
    if not ok:
        blockers.extend(validation_reasons)

    if simulation is None:
        warnings.append("missing_simulation_report")
    else:
        flags = [str(flag) for flag in as_list(simulation.get("balance_flags"))]
        blockers.extend(f"severe_simulation_flag:{flag}" for flag in flags if flag in SEVERE_SIMULATION_FLAGS)
        warnings.extend(f"review_simulation_flag:{flag}" for flag in flags if flag in REVIEW_SIMULATION_FLAGS)
        utility = simulation.get("utility_score")
        dps = simulation.get("estimated_dps")
        if isinstance(utility, (int, float)) and isinstance(dps, (int, float)):
            if float(utility) < 0.12 and float(dps) <= 0:
                blockers.append("simulation_indicates_no_playable_impact")

    if candidate_score is None:
        warnings.append("missing_candidate_score")
    else:
        recommendation = str(candidate_score.get("recommendation", ""))
        dimensions = as_obj(candidate_score.get("dimension_scores"))
        validation_score = float(dimensions.get("validation", 0.0) or 0.0)
        gameplay_score = float(dimensions.get("gameplay_fit", 0.0) or 0.0)
        simulation_score = float(dimensions.get("simulation", 0.0) or 0.0)
        if recommendation == "reject":
            blockers.append("candidate_score_reject")
        if gameplay_score < 60:
            blockers.append("candidate_score_gameplay_fit_too_low")
        if validation_score < 50:
            blockers.append("candidate_score_validation_too_low")
        if simulation_score < 35:
            warnings.append("candidate_score_simulation_low")
        if recommendation in {"revise", "needs_review"} and not blockers:
            warnings.append(f"candidate_score_{recommendation}")

    if blockers:
        return "failed", blockers, warnings
    return "passed", blockers, warnings


def media_state(
    runtime_readiness: dict[str, Any] | None,
    vision_review: dict[str, Any] | None,
    consistency_report: dict[str, Any] | None,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if runtime_readiness is None:
        warnings.append("missing_runtime_readiness_report")
        base = "missing"
    else:
        status = str(runtime_readiness.get("status", "failed"))
        if status == "passed":
            base = "runtime_ready"
        elif status == "needs_review":
            base = "needs_review"
            warnings.append("runtime_readiness_needs_review")
        else:
            base = "failed"
            blockers.append("runtime_readiness_failed")

    if consistency_report is not None:
        status = str(consistency_report.get("status", ""))
        if status == "failed":
            blockers.append("media_consistency_failed")
        elif status == "needs_review":
            warnings.append("media_consistency_needs_review")

    if vision_review is not None:
        status = str(vision_review.get("status", ""))
        score = vision_review.get("vision_score")
        score_value = float(score) if isinstance(score, (int, float)) else None
        if status == "failed" or (score_value is not None and score_value < 70):
            blockers.append("vision_review_failed")
        elif status == "needs_review" or (score_value is not None and score_value < 80):
            warnings.append("vision_review_needs_review")

    if blockers:
        return "failed", blockers, warnings
    if base == "runtime_ready" and not warnings:
        return "runtime_ready", blockers, warnings
    if base == "runtime_ready":
        return "needs_review", blockers, warnings
    return base, blockers, warnings


def evaluate_promotion(
    candidate: dict[str, Any],
    *,
    validation: dict[str, Any] | None = None,
    simulation: dict[str, Any] | None = None,
    candidate_score: dict[str, Any] | None = None,
    runtime_readiness: dict[str, Any] | None = None,
    vision_review: dict[str, Any] | None = None,
    consistency_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gameplay_state, gameplay_blockers, gameplay_warnings = gameplay_core_state(
        validation,
        simulation,
        candidate_score,
    )
    media_status, media_blockers, media_warnings = media_state(
        runtime_readiness,
        vision_review,
        consistency_report,
    )

    uses_fallback_media = False
    playable = False
    if gameplay_state == "failed":
        promotion_state = "failed"
    elif gameplay_state == "needs_review":
        promotion_state = "preview_only"
    elif media_status == "runtime_ready":
        promotion_state = "runtime_ready"
        playable = True
    else:
        promotion_state = "fallback_ready"
        playable = True
        uses_fallback_media = True

    required_next_actions: list[str] = []
    if promotion_state == "failed":
        required_next_actions.append("repair_gameplay_core_before_player_delivery")
    elif promotion_state == "preview_only":
        required_next_actions.append("human_or_agent_review_before_battle_delivery")
    elif promotion_state == "fallback_ready":
        required_next_actions.append("attach_deterministic_fallback_skin")
        if media_status in {"missing", "failed", "needs_review"}:
            required_next_actions.append("continue_media_generation_or_repair_in_background")
    elif promotion_state == "runtime_ready":
        required_next_actions.append("promote_to_player_runtime_package")

    return {
        "promotion_version": PROMOTION_VERSION,
        "candidate_id": candidate_id(candidate),
        "asset_type": asset_type(candidate),
        "promotion_state": promotion_state,
        "playable": playable,
        "uses_fallback_media": uses_fallback_media,
        "gameplay_core_state": gameplay_state,
        "media_state": media_status,
        "blockers": gameplay_blockers + media_blockers,
        "warnings": gameplay_warnings + media_warnings,
        "required_next_actions": required_next_actions,
        "fallback_media_strategy": {
            "enabled": promotion_state == "fallback_ready",
            "skin": "deterministic_shape_sprite",
            "icon": "generated_or_template_icon",
            "effects": "visual_recipe_only",
        },
        "source_summary": {
            "validation_status": validation.get("status") if isinstance(validation, dict) else None,
            "simulation_flags": as_list(simulation.get("balance_flags")) if isinstance(simulation, dict) else [],
            "candidate_score_recommendation": candidate_score.get("recommendation") if isinstance(candidate_score, dict) else None,
            "runtime_readiness_status": runtime_readiness.get("status") if isinstance(runtime_readiness, dict) else None,
            "vision_review_status": vision_review.get("status") if isinstance(vision_review, dict) else None,
            "media_consistency_status": consistency_report.get("status") if isinstance(consistency_report, dict) else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--validation")
    parser.add_argument("--simulation")
    parser.add_argument("--candidate-score")
    parser.add_argument("--runtime-readiness")
    parser.add_argument("--vision-review")
    parser.add_argument("--consistency-report")
    parser.add_argument("--output")
    args = parser.parse_args()

    candidate = load_json(Path(args.candidate))
    report = evaluate_promotion(
        candidate if isinstance(candidate, dict) else {},
        validation=load_json(Path(args.validation)) if args.validation else None,
        simulation=load_json(Path(args.simulation)) if args.simulation else None,
        candidate_score=load_json(Path(args.candidate_score)) if args.candidate_score else None,
        runtime_readiness=load_json(Path(args.runtime_readiness)) if args.runtime_readiness else None,
        vision_review=load_json(Path(args.vision_review)) if args.vision_review else None,
        consistency_report=load_json(Path(args.consistency_report)) if args.consistency_report else None,
    )
    if args.output:
        write_json(Path(args.output), report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["promotion_state"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
