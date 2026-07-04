#!/usr/bin/env python3
"""Score a CompiledAssetCandidate using deterministic guardrails.

This scorer is intentionally transparent. It combines validation state,
asset-type structure, simulation output, world-fit hints, and optional media
metadata into a compact candidate_score.v0.1 report. It is a selection
guardrail, not a substitute for human/playtest review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCORE_VERSION = "candidate_score_v0.1"

TECHNICAL_TERMS = {
    "provider",
    "schema",
    "prompt",
    "json",
    "llm",
    "api",
    "trace",
}

TYPE_REQUIRED_STATS = {
    "tower_blueprint": {"build_cost", "range", "cooldown"},
    "support_item": {"deploy_cost", "cooldown", "use_count"},
    "temporary_mod": {"activation_cost", "duration_seconds", "cooldown"},
    "intel_asset": {"action_cost", "valid_turns", "confidence"},
}

TYPE_REQUIRED_SPECIFIC = {
    "tower_blueprint": {"tower_slot"},
    "support_item": {"item_slot", "delivery_method", "target_rule"},
    "temporary_mod": {"target_asset_type", "stacking", "rollback_behavior"},
    "intel_asset": {"reveal_mode", "applies_to", "consumer_hint"},
}

TYPE_EXPECTED_MEDIA = {
    "tower_blueprint": {"icon", "tower_sprite", "battle_preview"},
    "support_item": {"icon", "ui_card", "effect_preview"},
    "temporary_mod": {"icon", "ui_card", "effect_preview"},
    "intel_asset": {"icon", "ui_card"},
}

FLAG_PENALTIES = {
    "no_direct_impact": 0.20,
    "pure_control_requires_damage_partner": 0.08,
    "control_may_be_too_strong": 0.12,
    "control_has_weak_cost": 0.10,
    "high_power_demand": 0.12,
    "possibly_underpriced": 0.10,
    "low_cost_efficiency": 0.12,
    "high_cost_efficiency": 0.06,
    "intel_asset_without_intel_effect": 0.25,
    "weak_intel_value": 0.12,
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def effect_types(candidate: dict[str, Any]) -> set[str]:
    gameplay = as_obj(candidate.get("gameplay"))
    effects = gameplay.get("effect_blocks")
    if not isinstance(effects, list):
        return set()
    return {
        str(effect.get("type"))
        for effect in effects
        if isinstance(effect, dict) and effect.get("type")
    }


def asset_type(candidate: dict[str, Any]) -> str:
    gameplay = as_obj(candidate.get("gameplay"))
    return str(gameplay.get("asset_type", "unknown"))


def score_validation(validation: dict[str, Any] | None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if validation is None:
        reasons.append("no_validation_artifact")
        return 0.75, reasons
    errors = validation.get("errors", [])
    if validation.get("status") == "passed" and not errors:
        return 1.0, reasons
    if isinstance(errors, list):
        reasons.extend(str(error) for error in errors[:5])
        return clamp01(0.5 - len(errors) * 0.08), reasons
    reasons.append("validation_not_passed")
    return 0.4, reasons


def score_gameplay_fit(candidate: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    kind = asset_type(candidate)
    gameplay = as_obj(candidate.get("gameplay"))
    stats = as_obj(gameplay.get("base_stats"))
    specific = as_obj(gameplay.get("type_specific"))
    effects = effect_types(candidate)

    required_stats = TYPE_REQUIRED_STATS.get(kind, set())
    required_specific = TYPE_REQUIRED_SPECIFIC.get(kind, set())
    missing_stats = sorted(required_stats - set(stats))
    missing_specific = sorted(required_specific - set(specific))

    score = 1.0
    if missing_stats:
        score -= min(0.35, 0.12 * len(missing_stats))
        reasons.append(f"missing_base_stats:{','.join(missing_stats)}")
    if missing_specific:
        score -= min(0.30, 0.10 * len(missing_specific))
        reasons.append(f"missing_type_specific:{','.join(missing_specific)}")
    if not effects:
        score -= 0.35
        reasons.append("missing_effect_blocks")

    if kind == "intel_asset" and not (effects & {"scout_reveal", "weakness_tag", "path_prediction", "threat_forecast", "countermeasure_hint"}):
        score -= 0.25
        reasons.append("intel_asset_without_intel_effect")
    if kind == "temporary_mod" and not (effects & {"damage", "pierce_or_chain", "charge_burst", "aura_buff"}):
        score -= 0.2
        reasons.append("temporary_mod_without_modifier_effect")
    if kind == "support_item" and not (effects & {"trap_tile_effect", "shield", "repair", "summon_unit", "slow", "scout_reveal"}):
        score -= 0.2
        reasons.append("support_item_without_support_effect")
    return clamp01(score), reasons


def score_simulation(simulation: dict[str, Any] | None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if simulation is None:
        reasons.append("no_simulation_artifact")
        return 0.5, reasons

    utility = float(simulation.get("utility_score") or 0.0)
    cost_eff = float(simulation.get("cost_efficiency") or 0.0)
    dps = float(simulation.get("estimated_dps") or 0.0)
    flags = simulation.get("balance_flags", [])
    flags = flags if isinstance(flags, list) else []

    utility_score = clamp01(utility / 0.6)
    cost_score = clamp01(cost_eff / 0.9)
    output_score = clamp01(dps / 80.0)
    base = max(utility_score, output_score * 0.8) * 0.55 + cost_score * 0.45

    penalty = 0.0
    for flag in flags:
        text = str(flag)
        penalty += FLAG_PENALTIES.get(text, 0.04)
        reasons.append(f"simulation_flag:{text}")
    return clamp01(base - min(penalty, 0.45)), reasons


def score_world_fit(candidate: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    presentation = as_obj(candidate.get("presentation"))
    provenance = as_obj(candidate.get("provenance"))
    text = " ".join(
        str(presentation.get(key, ""))
        for key in ("name", "short_description", "long_description")
    ).lower()

    score = 1.0
    if not provenance.get("worldbook_id"):
        score -= 0.3
        reasons.append("missing_worldbook_id")
    if not provenance.get("npc_ids"):
        score -= 0.08
        reasons.append("missing_npc_context")
    if not provenance.get("material_ids"):
        score -= 0.08
        reasons.append("missing_material_context")
    leaked_terms = sorted(term for term in TECHNICAL_TERMS if term in text)
    if leaked_terms:
        score -= min(0.3, 0.08 * len(leaked_terms))
        reasons.append(f"player_text_technical_terms:{','.join(leaked_terms)}")
    return clamp01(score), reasons


def score_media_readiness(
    candidate: dict[str, Any],
    media_metadata: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    expected = TYPE_EXPECTED_MEDIA.get(asset_type(candidate), {"icon"})
    if media_metadata is None:
        reasons.append("media_not_generated")
        return 0.35, reasons

    items = media_metadata.get("items") or media_metadata.get("published_media") or []
    if not isinstance(items, list):
        reasons.append("media_items_invalid")
        return 0.2, reasons
    roles = {
        str(item.get("media_role"))
        for item in items
        if isinstance(item, dict) and item.get("media_role")
    }
    coverage = len(expected & roles) / max(len(expected), 1)
    if coverage < 1:
        reasons.append(f"missing_media_roles:{','.join(sorted(expected - roles))}")

    score = 0.35 + coverage * 0.65
    if media_metadata.get("media_layer") == "published_media":
        score += 0.05
    return clamp01(score), reasons


def score_risk_control(candidate: dict[str, Any], simulation: dict[str, Any] | None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    provenance = as_obj(candidate.get("provenance"))
    mode = provenance.get("mode")
    effects = as_obj(candidate.get("gameplay")).get("effect_blocks", [])
    risk_delta = 0.0
    if isinstance(effects, list):
        for effect in effects:
            if isinstance(effect, dict) and effect.get("type") == "risk_modifier":
                value = effect.get("risk_delta")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    risk_delta += float(value)

    score = 0.85
    if mode == "runtime_safe" and risk_delta > 15:
        score -= 0.25
        reasons.append("runtime_safe_high_positive_risk")
    elif mode == "runtime_experimental" and risk_delta > 0:
        score += 0.08
    if simulation:
        flags = simulation.get("balance_flags", [])
        if isinstance(flags, list) and "high_power_demand" in flags:
            score -= 0.12
            reasons.append("high_power_demand")
    return clamp01(score), reasons


def recommendation(total: float, dimensions: dict[str, float], reasons: list[str]) -> str:
    if dimensions.get("validation", 0.0) < 0.5:
        return "reject"
    if total < 55:
        return "revise"
    if dimensions.get("media_readiness", 0.0) < 0.6:
        return "generate_media"
    if total < 72 or any("simulation_flag:control_may_be_too_strong" in r for r in reasons):
        return "needs_review"
    return "promote_candidate"


def score_candidate(
    candidate: dict[str, Any],
    *,
    validation: dict[str, Any] | None = None,
    simulation: dict[str, Any] | None = None,
    media_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_score, validation_reasons = score_validation(validation)
    gameplay_score, gameplay_reasons = score_gameplay_fit(candidate)
    simulation_score, simulation_reasons = score_simulation(simulation)
    world_score, world_reasons = score_world_fit(candidate)
    media_score, media_reasons = score_media_readiness(candidate, media_metadata)
    risk_score, risk_reasons = score_risk_control(candidate, simulation)

    weights = {
        "validation": 0.20,
        "gameplay_fit": 0.20,
        "simulation": 0.20,
        "world_fit": 0.15,
        "media_readiness": 0.15,
        "risk_control": 0.10,
    }
    dimensions = {
        "validation": validation_score,
        "gameplay_fit": gameplay_score,
        "simulation": simulation_score,
        "world_fit": world_score,
        "media_readiness": media_score,
        "risk_control": risk_score,
    }
    total = sum(dimensions[key] * weights[key] for key in weights) * 100.0
    reasons = (
        validation_reasons
        + gameplay_reasons
        + simulation_reasons
        + world_reasons
        + media_reasons
        + risk_reasons
    )
    return {
        "score_version": SCORE_VERSION,
        "candidate_id": candidate.get("id"),
        "asset_type": asset_type(candidate),
        "total_score": round(total, 1),
        "dimension_scores": {key: round(value * 100.0, 1) for key, value in dimensions.items()},
        "weights": weights,
        "recommendation": recommendation(total, dimensions, reasons),
        "reasons": reasons,
        "expected_media_roles": sorted(TYPE_EXPECTED_MEDIA.get(asset_type(candidate), {"icon"})),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", help="Path to CompiledAssetCandidate JSON.")
    parser.add_argument("--validation", help="Optional validation_result JSON.")
    parser.add_argument("--simulation", help="Optional simulation_report JSON.")
    parser.add_argument("--media-metadata", help="Optional raw/published media metadata JSON.")
    parser.add_argument("--output", help="Write candidate_score JSON to this path. Defaults to stdout.")
    args = parser.parse_args()

    candidate = load_json(Path(args.candidate))
    if not isinstance(candidate, dict):
        print("CompiledAssetCandidate root must be an object")
        return 1
    validation = load_json(Path(args.validation)) if args.validation else None
    simulation = load_json(Path(args.simulation)) if args.simulation else None
    media_metadata = load_json(Path(args.media_metadata)) if args.media_metadata else None
    report = score_candidate(
        candidate,
        validation=validation if isinstance(validation, dict) else None,
        simulation=simulation if isinstance(simulation, dict) else None,
        media_metadata=media_metadata if isinstance(media_metadata, dict) else None,
    )
    if args.output:
        write_json(Path(args.output), report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
