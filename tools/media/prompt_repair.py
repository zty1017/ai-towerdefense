#!/usr/bin/env python3
"""Build deterministic prompt repair plans from media review reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import asset_media_prompt
import media_review


PLAN_VERSION = "media_prompt_repair_plan.v0.1"


BASE_NEGATIVE_CONSTRAINTS = [
    "no readable text",
    "no pseudo text",
    "no letters",
    "no numbers",
    "no watermark",
    "no provider logo",
    "no generated UI labels",
]


WORLD_NEGATIVE_CONSTRAINTS = [
    "use abstract shadow mist instead of humanoid figures",
    "fantasy lantern-world scene only",
    "avoid real-world uniforms or equipment",
]


SUBJECT_DRIFT_NEGATIVE_CONSTRAINTS = [
    "do not change the asset into a large building",
    "do not change the asset into an altar",
    "do not change the asset into an unrelated large object",
    "do not replace the mirror shard lure motif",
]


ROLE_COMPOSITION: dict[str, list[str]] = {
    "icon": [
        "single centered object",
        "simple readable silhouette",
        "plain solid background",
    ],
    "tower_sprite": [
        "isolated sprite",
        "bottom-center anchor",
        "no battlefield background",
    ],
    "ui_card": [
        "illustration only",
        "blank decorative frame is allowed",
        "no label plaques or text areas with glyphs",
        "show one small deployable object, not a building",
    ],
    "effect_preview": [
        "small tower-defense diorama",
        "show the same deployable object on the ground",
        "abstract shadow mist and dark wisps around the device",
        "clearly show the gameplay effect with fantasy shadow shapes",
    ],
    "battle_preview": [
        "pseudo-isometric battlefield context",
        "same asset silhouette remains visible",
        "shadow tide enemies only",
    ],
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def role_quality_by_role(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(report, dict):
        return out
    for item in as_list(report.get("items")):
        if isinstance(item, dict) and item.get("media_role"):
            out[str(item["media_role"])] = item
    return out


def role_vision_by_role(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(report, dict):
        return out
    for item in as_list(report.get("item_reviews")):
        if isinstance(item, dict) and item.get("media_role"):
            out[str(item["media_role"])] = item
    return out


def reason_code_from_text(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("text", "glyph", "letter", "number", "文字", "伪文字")):
        return "text_or_glyph_detected"
    if "watermark" in lowered or "水印" in lowered:
        return "watermark_detected"
    if any(token in lowered for token in ("soldier", "military", "tactical", "human", "士兵", "军")):
        return "modern_human_soldier_detected"
    if any(token in lowered for token in ("inconsistency", "same subject", "subject", "主体", "漂移")):
        return "subject_drift"
    if any(token in lowered for token in ("world", "setting", "worldview", "世界观")):
        return "world_fit_failed"
    if any(token in lowered for token in ("role", "composition", "构图")):
        return "role_fit_failed"
    return None


def role_reason_codes(vision_item: dict[str, Any] | None, quality_item: dict[str, Any] | None) -> list[str]:
    codes: list[str] = []
    if isinstance(vision_item, dict):
        if vision_item.get("status") == "failed":
            codes.append("vision_failed")
        elif vision_item.get("status") == "needs_review":
            codes.append("vision_needs_review")
        if vision_item.get("text_detected") is True:
            codes.append("text_or_glyph_detected")
        if vision_item.get("watermark_detected") is True:
            codes.append("watermark_detected")
        if vision_item.get("same_subject") is False:
            codes.append("subject_drift")
        if vision_item.get("world_fit") == "failed":
            codes.append("world_fit_failed")
        if vision_item.get("role_fit") == "failed":
            codes.append("role_fit_failed")
        for key in ("issues", "warnings", "notes"):
            for text in as_list(vision_item.get(key)):
                code = reason_code_from_text(str(text))
                if code:
                    codes.append(code)
    if isinstance(quality_item, dict):
        for flag in as_list(quality_item.get("review_flags")):
            if flag == "ocr_text_check_required":
                codes.append("ocr_review_required")
            elif flag == "watermark_check_required":
                codes.append("watermark_review_required")
            elif flag == "semantic_world_fit_review_required":
                codes.append("semantic_world_fit_review_required")
    return unique(codes)


def positive_identity(candidate: dict[str, Any], visual_identity: dict[str, Any]) -> list[str]:
    presentation = as_obj(candidate.get("presentation"))
    subject = str(visual_identity.get("subject_name") or presentation.get("name") or candidate.get("id", "asset"))
    silhouette = str(visual_identity.get("silhouette") or "clear single-subject game asset silhouette")
    tokens = [str(v) for v in as_list(visual_identity.get("identity_tokens"))[:8]]
    motifs = [str(v) for v in as_list(visual_identity.get("required_motifs"))[:8]]
    out = [
        f"same asset subject: {subject}",
        f"preserve silhouette: {silhouette}",
        "consistent mirror-shard lure trap identity across all roles",
    ]
    if tokens:
        out.append("identity tokens: " + ", ".join(tokens))
    if motifs:
        out.append("required motifs: " + ", ".join(motifs))
    return out


def constraints_for_codes(codes: list[str]) -> list[str]:
    constraints = list(BASE_NEGATIVE_CONSTRAINTS)
    if any(code in codes for code in ("modern_human_soldier_detected", "world_fit_failed", "semantic_world_fit_review_required")):
        constraints.extend(WORLD_NEGATIVE_CONSTRAINTS)
    if "subject_drift" in codes:
        constraints.extend(SUBJECT_DRIFT_NEGATIVE_CONSTRAINTS)
    if "watermark_detected" in codes:
        constraints.append("no watermark-like corner marks")
    if "role_fit_failed" in codes:
        constraints.append("follow the requested media_role exactly")
    return unique(constraints)


def build_prompt_suffix(
    *,
    positive_additions: list[str],
    negative_constraints: list[str],
    composition_constraints: list[str],
) -> str:
    safe_avoid: list[str] = []
    constraint_text = " | ".join(negative_constraints).lower()
    if any(token in constraint_text for token in ("text", "letters", "numbers", "labels", "logo", "watermark")):
        safe_avoid.append("no readable writing, symbols, labels, logos, or watermark-like marks")
    if any(token in constraint_text for token in ("modern", "soldiers", "tactical", "military", "sci-fi")):
        safe_avoid.append("use abstract shadow mist and dark wisps instead of humanoid figures")
        safe_avoid.append("fantasy lantern-world battlefield only")
    if any(token in constraint_text for token in ("building", "altar", "object", "motif")):
        safe_avoid.append("do not transform the subject into an unrelated large object")
        safe_avoid.append("preserve the mirror-shard lure motif")
    positives = unique(positive_additions)[:6]
    composition = unique(composition_constraints)[:4]
    avoid = unique(safe_avoid)[:6]
    return (
        "Repair constraints: "
        + "; ".join(positives + composition)
        + ". Avoid: "
        + "; ".join(avoid)
        + "."
    )


def build_prompt_repair_plan(
    candidate: dict[str, Any],
    visual_identity: dict[str, Any],
    *,
    quality_report: dict[str, Any] | None = None,
    consistency_report: dict[str, Any] | None = None,
    vision_review_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_id = str(candidate.get("id", "unknown_candidate"))
    kind = media_review.asset_type(candidate)
    expected_roles = asset_media_prompt.default_media_roles(candidate)
    quality_by_role = role_quality_by_role(quality_report)
    vision_by_role = role_vision_by_role(vision_review_report)
    source_status = (
        str(vision_review_report.get("status"))
        if isinstance(vision_review_report, dict)
        else str(consistency_report.get("status")) if isinstance(consistency_report, dict)
        else "unknown"
    )
    source_action = (
        str(vision_review_report.get("recommended_action"))
        if isinstance(vision_review_report, dict)
        else ""
    )

    global_negative = list(BASE_NEGATIVE_CONSTRAINTS)
    global_text = []
    if isinstance(vision_review_report, dict):
        global_text.extend(str(v) for v in as_list(vision_review_report.get("global_issues")))
        global_text.extend(str(v) for v in as_list(vision_review_report.get("global_warnings")))
    for text in global_text:
        code = reason_code_from_text(text)
        if code in {"modern_human_soldier_detected", "world_fit_failed"}:
            global_negative.extend(WORLD_NEGATIVE_CONSTRAINTS)
        if code == "subject_drift":
            global_negative.extend(SUBJECT_DRIFT_NEGATIVE_CONSTRAINTS)
    global_negative = unique(global_negative)

    target_roles: list[str] = []
    reuse_roles: list[str] = []
    role_repairs: list[dict[str, Any]] = []
    prompt_suffix_by_role: dict[str, str] = {}
    identity_positive = positive_identity(candidate, visual_identity)

    for role in expected_roles:
        vision_item = vision_by_role.get(role)
        quality_item = quality_by_role.get(role)
        codes = role_reason_codes(vision_item, quality_item)
        regenerate = False
        if isinstance(vision_item, dict):
            regenerate = (
                vision_item.get("status") == "failed"
                or vision_item.get("text_detected") is True
                or vision_item.get("watermark_detected") is True
                or vision_item.get("same_subject") is False
                or vision_item.get("world_fit") == "failed"
                or vision_item.get("role_fit") == "failed"
            )
        elif source_status == "failed":
            regenerate = True

        if regenerate:
            target_roles.append(role)
        else:
            reuse_roles.append(role)

        composition = ROLE_COMPOSITION.get(role, ["single clear game asset composition"])
        negatives = unique(global_negative + constraints_for_codes(codes))
        positives = list(identity_positive)
        if role == "effect_preview":
            positives.append("same small deployable mirror shard lure trap emits refracted decoy light")
            positives.append("shadow tide creatures are faceless dark silhouettes around the trap")
        elif role == "ui_card":
            positives.append("same small deployable mirror shard lure trap as the icon")
            positives.append("card art without any written label or glyph texture")
        elif role == "icon":
            positives.append("simple mirror shard lure trap icon")

        role_repairs.append(
            {
                "media_role": role,
                "regenerate": regenerate,
                "reason_codes": codes,
                "positive_additions": unique(positives),
                "negative_constraints": negatives,
                "composition_constraints": composition,
                "reference_strategy": (
                    "reuse passed icon as visual identity reference for silhouette and motif"
                    if role != "icon" and "icon" in reuse_roles
                    else "use VisualIdentitySpec as the stable reference"
                ),
            }
        )
        if regenerate:
            prompt_suffix_by_role[role] = build_prompt_suffix(
                positive_additions=unique(positives),
                negative_constraints=negatives,
                composition_constraints=composition,
            )

    if source_action == "reject":
        next_action = "reject"
    elif target_roles:
        next_action = "regenerate_failed_roles"
    elif source_status == "needs_review":
        next_action = "manual_review"
    else:
        next_action = "none"

    return {
        "plan_version": PLAN_VERSION,
        "candidate_id": candidate_id,
        "asset_type": kind,
        "source_review_status": source_status,
        "next_action": next_action,
        "target_roles": target_roles,
        "reuse_roles": reuse_roles,
        "global_negative_constraints": global_negative,
        "role_repairs": role_repairs,
        "prompt_suffix_by_role": prompt_suffix_by_role,
        "notes": [
            "This deterministic plan converts review findings into prompt constraints.",
            "It does not guarantee image quality; regenerated media must be reviewed again.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--visual-identity", required=True)
    parser.add_argument("--quality-report")
    parser.add_argument("--consistency-report")
    parser.add_argument("--vision-review-report")
    parser.add_argument("--output")
    args = parser.parse_args()

    candidate = load_json(Path(args.candidate))
    visual_identity = load_json(Path(args.visual_identity))
    quality_report = load_json(Path(args.quality_report)) if args.quality_report else None
    consistency_report = load_json(Path(args.consistency_report)) if args.consistency_report else None
    vision_review_report = load_json(Path(args.vision_review_report)) if args.vision_review_report else None

    plan = build_prompt_repair_plan(
        candidate,
        visual_identity,
        quality_report=quality_report if isinstance(quality_report, dict) else None,
        consistency_report=consistency_report if isinstance(consistency_report, dict) else None,
        vision_review_report=vision_review_report if isinstance(vision_review_report, dict) else None,
    )
    if args.output:
        write_json(Path(args.output), plan)
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
