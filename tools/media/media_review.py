#!/usr/bin/env python3
"""Deterministic media quality and consistency guardrails.

These checks do not try to fully understand pixels. They validate metadata,
role coverage, identity linkage, local file format when available, and mark
which items need visual/OCR review before becoming trusted game assets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import asset_media_prompt


VISUAL_IDENTITY_VERSION = "visual_identity_spec.v0.1"
MEDIA_QUALITY_VERSION = "media_quality_report.v0.1"
MEDIA_CONSISTENCY_VERSION = "media_consistency_report.v0.1"


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


def asset_type(candidate: dict[str, Any]) -> str:
    return asset_media_prompt.asset_type(candidate)


def candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("id", "unknown_candidate"))


def effect_types(candidate: dict[str, Any]) -> list[str]:
    gameplay = as_obj(candidate.get("gameplay"))
    effects = as_list(gameplay.get("effect_blocks"))
    return [
        str(effect.get("type"))
        for effect in effects
        if isinstance(effect, dict) and effect.get("type")
    ]


def media_items(media_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "published_media", "raw_media_items"):
        items = media_metadata.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def build_visual_identity_spec(candidate: dict[str, Any]) -> dict[str, Any]:
    presentation = as_obj(candidate.get("presentation"))
    provenance = as_obj(candidate.get("provenance"))
    gameplay = as_obj(candidate.get("gameplay"))
    visual_tags = [str(tag) for tag in as_list(presentation.get("visual_tags"))]
    materials = [str(item) for item in as_list(provenance.get("material_ids"))]
    effects = effect_types(candidate)
    kind = asset_type(candidate)

    identity_tokens = unique_text(
        [
            str(presentation.get("name", "")),
            kind,
            *visual_tags,
            *materials,
            *effects,
        ]
    )

    if kind == "tower_blueprint":
        silhouette = "pseudo-isometric tower body, bottom-center anchor, readable base"
    elif kind == "support_item":
        silhouette = "small deployable object or ground trap, readable as a consumable item"
    elif kind == "temporary_mod":
        silhouette = "modification device or energy overlay that clearly attaches to a tower"
    elif kind == "intel_asset":
        silhouette = "map, scroll, signal device, or readable scouting artifact without text"
    else:
        silhouette = "clear single-subject game asset silhouette"

    spec = {
        "spec_version": VISUAL_IDENTITY_VERSION,
        "candidate_id": candidate_id(candidate),
        "asset_type": kind,
        "worldbook_id": provenance.get("worldbook_id"),
        "subject_name": presentation.get("name", candidate_id(candidate)),
        "identity_tokens": identity_tokens,
        "silhouette": silhouette,
        "materials": unique_text(materials + visual_tags),
        "palette": [
            "dark lantern-world neutrals",
            "warm amber lantern light",
            "cold blue-white magical highlights",
        ],
        "light_effects": unique_text(
            ["lantern glow"]
            + [effect for effect in effects if effect in {"slow", "power_cost", "pierce_or_chain", "risk_modifier"}]
        ),
        "required_motifs": unique_text(visual_tags + materials + effects),
        "forbidden_elements": [
            "readable text",
            "letters",
            "numbers",
            "watermark",
            "provider logo",
            "modern UI labels",
            "human soldiers as enemies in shadow-tide scenes",
        ],
        "role_directives": {
            "icon": "same subject, simple silhouette, no text, no watermark",
            "tower_sprite": "isolated sprite, no battlefield background, bottom-center anchor",
            "ui_card": "illustration only, blank label areas, no generated writing",
            "effect_preview": "show gameplay effect with shadow creatures or abstract hostile silhouettes",
            "battle_preview": "show the same asset in battlefield context without changing the core silhouette",
        },
    }
    if gameplay.get("constraints"):
        spec["gameplay_constraints_hint"] = gameplay.get("constraints")
    return spec


def detect_image_format(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return "unreadable"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"RIFF") and b"WEBP" in header[:12]:
        return "webp"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"
    return "unknown"


def extension_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"jpg", "jpeg"}:
        return "jpeg"
    if suffix in {"png", "webp", "gif"}:
        return suffix
    return suffix or "none"


def expected_roles_for_candidate(candidate: dict[str, Any]) -> list[str]:
    return asset_media_prompt.default_media_roles(candidate)


def assess_media_quality(
    candidate: dict[str, Any],
    media_metadata: dict[str, Any],
) -> dict[str, Any]:
    expected_roles = set(expected_roles_for_candidate(candidate))
    items = media_items(media_metadata)
    roles_present = {
        str(item.get("media_role"))
        for item in items
        if item.get("media_role")
    }
    missing_roles = sorted(expected_roles - roles_present)
    unknown_roles = sorted(roles_present - asset_media_prompt.MEDIA_ROLES)

    item_reports: list[dict[str, Any]] = []
    critical_count = 0
    warning_count = 0
    review_count = 0

    if missing_roles:
        critical_count += len(missing_roles)
    if unknown_roles:
        warning_count += len(unknown_roles)

    for item in items:
        role = str(item.get("media_role", "unknown"))
        issues: list[str] = []
        warnings: list[str] = []
        review_flags: list[str] = []
        width = item.get("width")
        height = item.get("height")
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            issues.append("missing_dimensions")
        elif width <= 0 or height <= 0:
            issues.append("invalid_dimensions")
        elif role in {"icon", "tower_sprite"} and abs(float(width) - float(height)) > max(width, height) * 0.05:
            warnings.append("expected_near_square_canvas")

        local_path = item.get("local_path")
        detected_format = None
        declared_extension = None
        if isinstance(local_path, str) and local_path:
            path = Path(local_path)
            declared_extension = extension_format(path)
            if not path.exists():
                issues.append("local_file_missing")
            else:
                detected_format = detect_image_format(path)
                if detected_format in {"unknown", "unreadable"}:
                    issues.append(f"image_format_{detected_format}")
                elif declared_extension != detected_format:
                    warnings.append(f"extension_mismatch:{declared_extension}_file_is_{detected_format}")
        else:
            warnings.append("local_file_not_available_for_format_check")

        if item.get("fallback_used"):
            warnings.append("fallback_media_used")
        if role == "ui_card":
            review_flags.append("ocr_text_check_required")
        if role in {"ui_card", "effect_preview", "battle_preview"}:
            review_flags.append("watermark_check_required")
        if role in {"effect_preview", "battle_preview"}:
            review_flags.append("semantic_world_fit_review_required")
        if role == "tower_sprite":
            review_flags.append("background_and_anchor_review_required")

        critical_count += len(issues)
        warning_count += len(warnings)
        review_count += len(review_flags)
        item_reports.append(
            {
                "stable_internal_id": item.get("stable_internal_id"),
                "media_role": role,
                "width": width,
                "height": height,
                "detected_format": detected_format,
                "declared_extension": declared_extension,
                "issues": issues,
                "warnings": warnings,
                "review_flags": review_flags,
            }
        )

    status = "passed"
    if critical_count:
        status = "failed"
    elif warning_count or review_count:
        status = "needs_review"

    return {
        "report_version": MEDIA_QUALITY_VERSION,
        "candidate_id": candidate_id(candidate),
        "asset_type": asset_type(candidate),
        "media_layer": media_metadata.get("media_layer"),
        "status": status,
        "expected_roles": sorted(expected_roles),
        "roles_present": sorted(roles_present),
        "missing_roles": missing_roles,
        "unknown_roles": unknown_roles,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "review_count": review_count,
        "items": item_reports,
        "notes": [
            "This deterministic report checks metadata and file headers only.",
            "OCR/text, watermark, and semantic visual consistency require a visual reviewer or vision model.",
        ],
    }


def assess_media_consistency(
    candidate: dict[str, Any],
    media_metadata: dict[str, Any],
    visual_identity: dict[str, Any],
    quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_roles = set(expected_roles_for_candidate(candidate))
    items = media_items(media_metadata)
    candidate_prefix = candidate_id(candidate)
    roles_present = {
        str(item.get("media_role"))
        for item in items
        if item.get("media_role")
    }
    issues: list[str] = []
    warnings: list[str] = []
    review_flags: list[str] = []

    missing_roles = sorted(expected_roles - roles_present)
    if missing_roles:
        issues.append(f"missing_roles:{','.join(missing_roles)}")

    providers = {
        str(item.get("provider_profile"))
        for item in items
        if item.get("provider_profile")
    }
    models = {
        str(item.get("model"))
        for item in items
        if item.get("model")
    }
    if len(providers) > 1:
        warnings.append("mixed_provider_style_risk")
    if len(models) > 1:
        warnings.append("mixed_model_style_risk")

    dimensions = {
        (item.get("width"), item.get("height"))
        for item in items
        if item.get("width") and item.get("height")
    }
    if len(dimensions) > 1:
        warnings.append("mixed_canvas_dimensions")

    identity_tokens = [
        str(token).lower()
        for token in as_list(visual_identity.get("identity_tokens"))
        if str(token).strip()
    ]
    identity_linked_items = 0
    for item in items:
        stable_id = str(item.get("stable_internal_id", ""))
        role = str(item.get("media_role", "unknown"))
        if stable_id and not stable_id.startswith(candidate_prefix):
            warnings.append(f"stable_id_not_prefixed_by_candidate:{stable_id}")

        prompt_summary = str(item.get("prompt_summary", "")).lower()
        if prompt_summary:
            if candidate_prefix.lower() in prompt_summary or str(visual_identity.get("subject_name", "")).lower() in prompt_summary:
                identity_linked_items += 1
            elif any(token in prompt_summary for token in identity_tokens):
                identity_linked_items += 1
            else:
                warnings.append(f"weak_prompt_identity_link:{role}")
        else:
            review_flags.append(f"visual_identity_review_required:{role}")

    quality_status = quality_report.get("status") if isinstance(quality_report, dict) else None
    if quality_status == "failed":
        issues.append("quality_report_failed")
    elif quality_status == "needs_review":
        review_flags.append("quality_report_needs_review")

    role_coverage = len(expected_roles & roles_present) / max(len(expected_roles), 1)
    provider_score = 1.0 if len(providers) <= 1 else 0.6
    model_score = 1.0 if len(models) <= 1 else 0.7
    dimension_score = 1.0 if len(dimensions) <= 1 else 0.75
    identity_score = identity_linked_items / max(len(items), 1) if items else 0.0
    quality_score = 1.0 if quality_status == "passed" else 0.75 if quality_status == "needs_review" else 0.55 if quality_status is None else 0.25
    total = (
        role_coverage * 0.30
        + provider_score * 0.15
        + model_score * 0.10
        + dimension_score * 0.15
        + identity_score * 0.20
        + quality_score * 0.10
    ) * 100.0

    status = "passed"
    if issues or total < 55:
        status = "failed"
    elif warnings or review_flags or total < 82:
        status = "needs_review"

    return {
        "report_version": MEDIA_CONSISTENCY_VERSION,
        "candidate_id": candidate_prefix,
        "asset_type": asset_type(candidate),
        "status": status,
        "consistency_score": round(total, 1),
        "expected_roles": sorted(expected_roles),
        "roles_present": sorted(roles_present),
        "provider_profiles": sorted(providers),
        "models": sorted(models),
        "dimensions": [list(dim) for dim in sorted(dimensions)],
        "issues": issues,
        "warnings": sorted(set(warnings)),
        "review_flags": sorted(set(review_flags)),
        "visual_identity_ref": {
            "spec_version": visual_identity.get("spec_version"),
            "subject_name": visual_identity.get("subject_name"),
            "identity_tokens": visual_identity.get("identity_tokens", []),
        },
        "notes": [
            "Consistency is metadata-based in v0.1.",
            "A vision-model reviewer should be added before trusting semantic consistency.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_identity = sub.add_parser("identity")
    p_identity.add_argument("--candidate", required=True)
    p_identity.add_argument("--output")

    p_quality = sub.add_parser("quality")
    p_quality.add_argument("--candidate", required=True)
    p_quality.add_argument("--media-metadata", required=True)
    p_quality.add_argument("--output")

    p_consistency = sub.add_parser("consistency")
    p_consistency.add_argument("--candidate", required=True)
    p_consistency.add_argument("--media-metadata", required=True)
    p_consistency.add_argument("--visual-identity", required=True)
    p_consistency.add_argument("--quality-report")
    p_consistency.add_argument("--output")

    args = parser.parse_args()
    candidate = load_json(Path(args.candidate))
    if not isinstance(candidate, dict):
        print("candidate must be an object")
        return 1

    if args.command == "identity":
        report = build_visual_identity_spec(candidate)
    elif args.command == "quality":
        media_metadata = load_json(Path(args.media_metadata))
        report = assess_media_quality(candidate, media_metadata)
    else:
        media_metadata = load_json(Path(args.media_metadata))
        visual_identity = load_json(Path(args.visual_identity))
        quality_report = load_json(Path(args.quality_report)) if args.quality_report else None
        report = assess_media_consistency(
            candidate,
            media_metadata,
            visual_identity,
            quality_report=quality_report if isinstance(quality_report, dict) else None,
        )

    if args.output:
        write_json(Path(args.output), report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
