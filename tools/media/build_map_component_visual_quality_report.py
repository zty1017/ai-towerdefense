#!/usr/bin/env python3
"""Build MapComponent generated-candidate visual quality report v0.1.

This gate only inspects generated candidates already admitted by
MapComponentCandidateReviewReport. Deterministic baseline SVG fixtures are not
treated as generated candidates and never enter this report as checked items.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import png_pipeline  # noqa: E402


REPORT_VERSION = "map_component_visual_quality_report.v0.1"
DEFAULT_CANDIDATE_REVIEW = ROOT / "examples/review_packs/map_component_candidate_review_report.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_component_visual_quality_report.v0.1.json"

USAGE_POLICY = [
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "generated_candidates_only",
    "baseline_fixture_is_not_generated_candidate",
    "no_frontend_default_consumption",
    "no_manifest_or_style_pack_or_render_plan_mutation",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]
NEXT_ACTIONS = [
    "complete human visual review against component role and StylePack",
    "complete cutout and normalization review for raster candidates",
    "refresh MapStyleComponentBindingReport after accepted local artifacts exist",
    "run explicit MapComponentPromotionGateReport before any manifest replacement",
]
REMOTE_REF_RE = re.compile(
    r"(?:href|src)\s*=\s*['\"][^'\"]*(?:https?://|://)|url\(\s*['\"]?(?:https?://|://)",
    re.IGNORECASE,
)


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extension_kind(path_value: str) -> str:
    suffix = Path(path_value).suffix.lower().lstrip(".")
    return suffix if suffix in {"png", "svg", "webp"} else "unknown"


def detect_file_type(path: Path) -> str:
    try:
        head = path.read_bytes()[:512]
    except OSError:
        return "unknown"
    if head.startswith(png_pipeline.PNG_SIG):
        return "png"
    if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP":
        return "webp"
    if b"<svg" in head.lower():
        return "svg"
    return "unknown"


def empty_png_checks() -> dict[str, Any]:
    return {
        "decode_status": "not_applicable",
        "width": None,
        "height": None,
        "matches_target_size": None,
        "alpha_visible_ratio": None,
        "alpha_transparent_ratio": None,
        "subject_bbox": None,
        "subject_bbox_coverage": None,
        "edge_contact": {"top": False, "right": False, "bottom": False, "left": False},
    }


def empty_svg_checks() -> dict[str, Any]:
    return {
        "parse_status": "not_applicable",
        "contains_svg_root": None,
        "has_script": None,
        "has_remote_reference": None,
    }


def empty_webp_checks() -> dict[str, Any]:
    return {"decode_status": "not_applicable", "needs_manual_review": False}


def png_edge_contact(image: png_pipeline.PngImage, *, alpha_threshold: int) -> dict[str, bool]:
    top = bottom = left = right = False
    for x in range(image.width):
        top = top or image.pixels[x * 4 + 3] > alpha_threshold
        bottom = bottom or image.pixels[((image.height - 1) * image.width + x) * 4 + 3] > alpha_threshold
    for y in range(image.height):
        left = left or image.pixels[(y * image.width) * 4 + 3] > alpha_threshold
        right = right or image.pixels[(y * image.width + image.width - 1) * 4 + 3] > alpha_threshold
    return {"top": top, "right": right, "bottom": bottom, "left": left}


def build_png_checks(path: Path, target_size: dict[str, Any], issues: list[str], warnings: list[str]) -> dict[str, Any]:
    try:
        image = png_pipeline.read_png(path)
    except Exception as exc:
        issues.append(f"png_decode_failed:{exc}")
        checks = empty_png_checks()
        checks["decode_status"] = "decode_failed"
        return checks

    alpha_values = image.pixels[3::4]
    total_pixels = len(alpha_values)
    visible_pixels = sum(1 for alpha in alpha_values if alpha > 8)
    transparent_pixels = total_pixels - visible_pixels
    bbox = png_pipeline.alpha_bbox(image, alpha_threshold=8)
    bbox_payload = None
    bbox_area = 0
    if bbox:
        x0, y0, x1, y1 = bbox
        bbox_area = (x1 - x0) * (y1 - y0)
        bbox_payload = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}

    matches_target = (
        target_size.get("width") == image.width
        and target_size.get("height") == image.height
    )
    if not matches_target:
        warnings.append("png_dimensions_do_not_match_target_size")
    if visible_pixels <= 0:
        issues.append("png_has_no_visible_pixels")
    visible_ratio = round(visible_pixels / total_pixels, 4) if total_pixels else 0
    transparent_ratio = round(transparent_pixels / total_pixels, 4) if total_pixels else 0
    if visible_ratio >= 0.98:
        warnings.append("png_has_little_or_no_transparency")

    edge_contact = png_edge_contact(image, alpha_threshold=8)
    if any(edge_contact.values()):
        warnings.append("png_visible_subject_contacts_canvas_edge")

    return {
        "decode_status": "decoded",
        "width": image.width,
        "height": image.height,
        "matches_target_size": matches_target,
        "alpha_visible_ratio": visible_ratio,
        "alpha_transparent_ratio": transparent_ratio,
        "subject_bbox": bbox_payload,
        "subject_bbox_coverage": round(bbox_area / total_pixels, 4) if total_pixels else 0,
        "edge_contact": edge_contact,
    }


def build_svg_checks(path: Path, issues: list[str], warnings: list[str]) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
        warnings.append("svg_text_decoded_with_replacement_characters")
    except OSError as exc:
        issues.append(f"svg_read_failed:{exc}")
        checks = empty_svg_checks()
        checks["parse_status"] = "read_failed"
        return checks

    lowered = text.lower()
    contains_svg_root = "<svg" in lowered
    has_script = "<script" in lowered or "</script" in lowered
    has_remote_reference = bool(REMOTE_REF_RE.search(text))
    if not contains_svg_root:
        issues.append("svg_root_missing")
    if has_script:
        issues.append("svg_script_not_allowed")
    if has_remote_reference:
        issues.append("svg_remote_reference_not_allowed")
    return {
        "parse_status": "checked",
        "contains_svg_root": contains_svg_root,
        "has_script": has_script,
        "has_remote_reference": has_remote_reference,
    }


def build_item(candidate: dict[str, Any]) -> dict[str, Any]:
    path_value = str(candidate.get("candidate_local_path") or "")
    declared_sha = candidate.get("candidate_sha256")
    target_size = as_obj(candidate.get("target_size"))
    path = resolve_path(path_value) if path_value else ROOT / "__missing__"
    issues: list[str] = []
    warnings: list[str] = []
    ext = extension_kind(path_value)
    exists = path.exists()
    actual_sha = sha256_file(path) if exists and path.is_file() else None
    size_bytes = path.stat().st_size if exists and path.is_file() else None
    detected_type = detect_file_type(path) if exists and path.is_file() else "unknown"

    if not path_value:
        issues.append("candidate_local_path_missing")
    if not exists:
        issues.append("candidate_local_path_missing_on_disk")
    if not isinstance(declared_sha, str) or not declared_sha:
        issues.append("candidate_sha256_missing")
        declared_sha_value = None
    else:
        declared_sha_value = declared_sha
    sha_matches = actual_sha == declared_sha if actual_sha and isinstance(declared_sha, str) else None
    if sha_matches is False:
        issues.append("candidate_sha256_mismatch")
    file_type_matches = detected_type == ext if exists and ext != "unknown" and detected_type != "unknown" else None
    if file_type_matches is False:
        issues.append("candidate_file_type_mismatch")
    if ext == "unknown":
        issues.append("candidate_extension_unsupported")

    png_checks = empty_png_checks()
    svg_checks = empty_svg_checks()
    webp_checks = empty_webp_checks()
    cutout_status = "blocked_file_level_issue"
    if exists and ext == "png":
        png_checks = build_png_checks(path, target_size, issues, warnings)
        cutout_status = "pending_png_cutout_review" if not issues else "blocked_file_level_issue"
    elif exists and ext == "svg":
        svg_checks = build_svg_checks(path, issues, warnings)
        cutout_status = "not_applicable_svg_vector_review" if not issues else "blocked_file_level_issue"
    elif exists and ext == "webp":
        webp_checks = {"decode_status": "unsupported_decode", "needs_manual_review": True}
        warnings.append("webp_decode_not_available_needs_manual_review")
        cutout_status = "needs_review_unsupported_decode"

    if ext == "webp" and not issues:
        review_status = "needs_review_unsupported_decode"
    elif issues:
        review_status = "blocked_pending_quality_gates"
    else:
        review_status = "needs_review"
        if cutout_status == "not_applicable_svg_vector_review":
            warnings.append("svg_requires_human_visual_review_before_promotion")
        elif cutout_status == "pending_png_cutout_review":
            warnings.append("png_cutout_normalization_requires_review_before_promotion")

    return {
        "candidate_id": candidate.get("candidate_id"),
        "request_id": candidate.get("request_id"),
        "component_id": candidate.get("component_id"),
        "component_role": candidate.get("component_role"),
        "style_pack_id": candidate.get("style_pack_id"),
        "node_id": candidate.get("node_id"),
        "candidate_kind": "generated_candidate",
        "source_candidate_local_path": path_value,
        "source_candidate_sha256": declared_sha,
        "target_size": target_size,
        "review_status": review_status,
        "promotion_allowed_now": False,
        "runtime_ready": False,
        "file_checks": {
            "local_file_exists": exists,
            "declared_sha256": declared_sha_value,
            "actual_sha256": actual_sha,
            "sha256_matches_declared": sha_matches,
            "file_size_bytes": size_bytes,
            "extension": ext,
            "detected_file_type": detected_type,
            "file_type_matches_extension": file_type_matches,
        },
        "png_checks": png_checks,
        "svg_checks": svg_checks,
        "webp_checks": webp_checks,
        "cutout_normalization_status": cutout_status,
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "required_next_actions": NEXT_ACTIONS,
        "usage_policy": USAGE_POLICY,
    }


def generated_candidates(candidate_review: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict) and candidate.get("candidate_kind") == "generated_candidate"
    ]


def build_report(
    candidate_review_path: Path,
    *,
    output_path: Path,
    created_at: str | None,
) -> dict[str, Any]:
    candidate_review = as_obj(load_json(candidate_review_path))
    source_candidates = [
        candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict)
    ]
    generated = generated_candidates(candidate_review)
    items = [build_item(candidate) for candidate in generated]
    status_counts = Counter(str(item.get("review_status")) for item in items)
    file_type_counts = Counter(str(as_obj(item.get("file_checks")).get("extension")) for item in items)
    issue_counts: Counter[str] = Counter()
    for item in items:
        issue_counts.update(str(issue) for issue in as_list(item.get("issues")))

    blocked_count = status_counts.get("blocked_pending_quality_gates", 0)
    if not generated:
        status = "awaiting_generated_candidates"
    elif blocked_count:
        status = "blocked_pending_quality_gates"
    else:
        status = "needs_review"

    return {
        "schema_version": REPORT_VERSION,
        "report_id": "map_component_visual_quality_report_v0_1",
        "created_at": created_at or str(candidate_review.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_candidate_review_report_path": rel(candidate_review_path),
        "status": status,
        "usage_policy": USAGE_POLICY,
        "summary": {
            "source_candidate_count": len(source_candidates),
            "generated_candidate_count": len(generated),
            "checked_candidate_count": len(items),
            "passed_count": status_counts.get("passed", 0),
            "blocked_pending_quality_gates_count": blocked_count,
            "needs_review_count": status_counts.get("needs_review", 0),
            "unsupported_decode_count": status_counts.get("needs_review_unsupported_decode", 0),
            "status_counts": dict(sorted(status_counts.items())),
            "file_type_counts": dict(sorted(file_type_counts.items())),
            "issue_counts": dict(sorted(issue_counts.items())),
        },
        "items": items,
        "runtime_effect": {
            "manifest_replacement_written": False,
            "style_pack_modified": False,
            "render_plan_modified": False,
            "frontend_default_modified": False,
            "runtime_map_truth_modified": False,
        },
        "promotion_effect": {
            "generated_candidate_promoted": False,
            "promotion_gate_bypassed": False,
            "candidate_marked_runtime_ready": False,
        },
        "validation": {
            "validator": "tools/media/validate_map_component_visual_quality_report.py",
            "commands": [
                f"python3 tools/media/validate_map_component_visual_quality_report.py {rel(output_path)}"
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapComponentVisualQualityReport v0.1.")
    parser.add_argument("--candidate-review", default=str(DEFAULT_CANDIDATE_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    candidate_review_path = resolve_path(args.candidate_review)
    output_path = resolve_path(args.output)
    report = build_report(
        candidate_review_path,
        output_path=output_path,
        created_at=args.created_at,
    )
    write_json(output_path, report)
    print(f"OK: wrote {output_path}")
    print(f"- status: {report['status']}")
    print(f"- generated_candidate_count: {report['summary']['generated_candidate_count']}")
    print(f"- checked_candidate_count: {report['summary']['checked_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
