#!/usr/bin/env python3
"""Generate, review, repair, and stage layered map visual candidates."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

try:
    from . import generate_layered_map_visual_candidates as candidate_generator
    from . import image_provider, png_pipeline, vision_review
except ImportError:  # pragma: no cover - direct script/import from tools path.
    import generate_layered_map_visual_candidates as candidate_generator  # type: ignore[no-redef]
    import image_provider  # type: ignore[no-redef]
    import png_pipeline  # type: ignore[no-redef]
    import vision_review  # type: ignore[no-redef]


REPORT_VERSION = "map_visual_closed_loop_report.v0.1"
CRITICAL_ROLES = {"terrain_base", "road_surface", "build_slot_platform"}
COMPONENT_ROLES = {
    "road_surface",
    "build_slot_platform",
    "objective_foundation",
    "spawn_marker",
    "non_blocking_decoration",
}
COMMON_CHECKS = (
    "no_people_or_creatures",
    "no_text_symbols_or_watermark",
    "worldbook_style_fit",
    "correct_game_camera",
    "no_baked_ui_or_combat_effects",
)
ROLE_CHECKS = {
    "terrain_base": (
        "central_playable_clearance",
        "no_baked_route",
        "no_baked_build_slots",
        "no_baked_objective_or_monument",
        "architecture_kept_to_perimeter",
    ),
    "road_surface": ("isolated_asset", "plain_white_background", "single_road_strip"),
    "build_slot_platform": (
        "isolated_asset",
        "plain_white_background",
        "single_empty_low_foundation",
    ),
    "objective_foundation": ("isolated_asset", "plain_white_background", "single_compact_object"),
    "spawn_marker": ("isolated_asset", "plain_white_background", "low_profile_marker"),
    "non_blocking_decoration": ("isolated_asset", "plain_white_background", "compact_separated_props"),
}
REPAIR_TEXT = {
    "no_people_or_creatures": "remove every human, humanoid, creature, silhouette and character-like statue",
    "no_text_symbols_or_watermark": "remove every inscription, pseudo-text, symbol, sign, watermark and emblem",
    "worldbook_style_fit": "use restrained late-Ming Chinese frontier materials and architecture with only subtle dark-fantasy influence",
    "correct_game_camera": "use a consistent elevated three-quarter top-down game camera",
    "no_baked_ui_or_combat_effects": "remove UI, selection rings, health bars, beams, explosions, magic circles and combat action",
    "central_playable_clearance": "make the central seventy percent calm, open, low-detail and free of focal objects",
    "no_baked_route": "remove all painted roads, trails, route bands and directional paths",
    "no_baked_build_slots": "remove every deployment pad, circular platform, socket and tower base",
    "no_baked_objective_or_monument": "remove central objectives, monuments, portals, shrines and large landmarks",
    "architecture_kept_to_perimeter": "confine all buildings, walls and large props to the outer twenty percent",
    "isolated_asset": "show only the requested asset with no surrounding scene, landscape or decorative frame",
    "plain_white_background": "use a completely flat pure-white background extending to all four canvas edges",
    "single_road_strip": "show exactly one reusable road material strip and nothing else",
    "single_empty_low_foundation": "show exactly one empty low foundation with no tower, lantern or mounted object",
    "single_compact_object": "show exactly one compact object with a clear anchor and no extra props",
    "low_profile_marker": "keep the entrance marker low-profile, restrained and free of creatures or warning icons",
    "compact_separated_props": "show a small separated set of compact edge props without scenery",
    "deterministic_png_invalid": "return a standard non-interlaced RGB or RGBA PNG",
    "deterministic_canvas_too_small": "render the asset at the requested resolution with crisp edges",
    "deterministic_background_not_white": "replace the entire component background with flat neutral pure white",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compose_prompt(sections: dict[str, str]) -> str:
    order = ("subject", "environment", "style", "lighting", "composition", "quality")
    return " ".join(
        f"{key.title()}: {sections[key].strip().rstrip('.')}."
        for key in order
        if sections.get(key, "").strip()
    )


def build_review_prompt(request: dict[str, Any]) -> str:
    role = str(request.get("role") or "unknown")
    required = [*COMMON_CHECKS, *ROLE_CHECKS.get(role, ())]
    context = {
        "role": role,
        "worldbook_id": request.get("worldbook_id"),
        "required_checks": required,
        "intended_visual": request.get("prompt_sections", {}),
    }
    return (
        "你是严格的 2D/伪3D 塔防地图分层素材审查器。只判断图片是否满足指定 role，"
        "不要因为画面好看而放宽要求。所有 required_checks 都必须明确判断。\n"
        "只输出合法 JSON 对象，字段为 score、checks、notes。score 是 0 到 1 的数字；"
        "checks 是对象，键必须覆盖 required_checks，值只能是 true 或 false；notes 是简短字符串数组。"
        "看不清或不确定时填 false。不得输出 Markdown。\n"
        f"审查上下文：{json.dumps(context, ensure_ascii=False)}"
    )


def deterministic_issues(path: Path, role: str) -> tuple[list[str], dict[str, Any]]:
    try:
        image = png_pipeline.read_png(path)
    except (OSError, ValueError):
        return ["deterministic_png_invalid"], {}
    issues: list[str] = []
    if image.width < 512 or image.height < 512:
        issues.append("deterministic_canvas_too_small")
    metrics: dict[str, Any] = {"width": image.width, "height": image.height}
    if role in COMPONENT_ROLES:
        background = png_pipeline.estimate_background_rgb(image)
        luma = (background[0] * 299 + background[1] * 587 + background[2] * 114) // 1000
        chroma = max(background) - min(background)
        metrics.update({"estimated_background_rgb": list(background), "background_luma": luma, "background_chroma": chroma})
        if luma < 225 or chroma > 30:
            issues.append("deterministic_background_not_white")
    return issues, metrics


def normalize_vision_review(raw: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    role = str(request.get("role") or "unknown")
    required = [*COMMON_CHECKS, *ROLE_CHECKS.get(role, ())]
    raw_checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    checks = {key: raw_checks.get(key) is True for key in required}
    try:
        score = max(0.0, min(1.0, float(raw.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    failed = [key for key, passed in checks.items() if not passed]
    return {
        "score": round(score, 4),
        "checks": checks,
        "failed_checks": failed,
        "notes": [str(item)[:240] for item in raw.get("notes", []) if isinstance(item, str)][:8],
        "status": "passed" if not failed and score >= 0.78 else "failed",
    }


def review_candidate(
    request: dict[str, Any],
    candidate_path: Path,
    profile: vision_review.VisionProfile,
    *,
    timeout: int,
    max_tokens: int,
    credential_index: int = 0,
) -> dict[str, Any]:
    deterministic, metrics = deterministic_issues(candidate_path, str(request.get("role") or ""))
    review_item = {
        "stable_internal_id": str(request.get("request_id") or "map_visual"),
        "media_role": str(request.get("role") or "unknown"),
        "local_path": candidate_path,
        "width": metrics.get("width"),
        "height": metrics.get("height"),
    }
    raw_text = vision_review.call_vision_model(
        profile,
        build_review_prompt(request),
        [review_item],
        max_tokens=max_tokens,
        timeout=timeout,
        credential_index=credential_index,
    )
    parsed = vision_review.extract_json(raw_text) or {}
    normalized = normalize_vision_review(parsed, request)
    failed = list(dict.fromkeys([*deterministic, *normalized["failed_checks"]]))
    normalized.update(
        {
            "status": "passed" if not failed and normalized["status"] == "passed" else "failed",
            "failed_checks": failed,
            "deterministic_metrics": metrics,
            "reviewer_profile": profile.name,
            "raw_response_stored": False,
        }
    )
    return normalized


def repaired_request(request: dict[str, Any], failed_checks: list[str]) -> dict[str, Any]:
    repaired = copy.deepcopy(request)
    sections = repaired.get("prompt_sections")
    sections = dict(sections) if isinstance(sections, dict) else {}
    corrections = [REPAIR_TEXT[check] for check in failed_checks if check in REPAIR_TEXT]
    if corrections:
        correction_text = "Correction pass: " + "; ".join(dict.fromkeys(corrections))
        sections["quality"] = f"{sections.get('quality', '')}; {correction_text}".strip("; ")
    repaired["prompt_sections"] = sections
    repaired["prompt_brief"] = compose_prompt(sections)
    repaired["repair_source_checks"] = list(dict.fromkeys(failed_checks))
    return repaired


def postprocess_component(source: Path, output: Path, *, keep_largest: bool) -> dict[str, Any]:
    image = png_pipeline.read_png(source)
    image = png_pipeline.remove_edge_matte_background(image, threshold=42)
    image = png_pipeline.remove_near_white_background_islands(image, min_pixels=64)
    image = png_pipeline.remove_small_alpha_components(image, min_pixels=96)
    if keep_largest:
        image = png_pipeline.keep_largest_alpha_component(image)
    image = png_pipeline.crop_and_pad(image, padding=32)
    image = png_pipeline.normalize_canvas(image, square=True, min_size=512)
    image = png_pipeline.clear_transparent_rgb(image)
    png_pipeline.write_png(output, image)
    return {"width": image.width, "height": image.height, "sha256": sha256_file(output)}


def promote_candidate(node_id: str, role: str, source: Path, reviewed_dir: Path) -> dict[str, Any]:
    if role == "terrain_base":
        output = reviewed_dir / "backdrops" / f"{node_id}.reviewed_painted_backdrop.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        metrics = {"sha256": sha256_file(output)}
        consumed_by_runtime = True
    else:
        filename = {"road_surface": "road_tile.png", "build_slot_platform": "slot_tile.png"}.get(role, f"{role}.png")
        folder = "textures" if role in {"road_surface", "build_slot_platform"} else "components"
        output = reviewed_dir / folder / filename
        metrics = postprocess_component(source, output, keep_largest=role != "non_blocking_decoration")
        consumed_by_runtime = role in {"road_surface", "build_slot_platform"}
    return {
        "role": role,
        "source_path": str(source.resolve()),
        "reviewed_path": str(output.resolve()),
        "consumed_by_current_runtime": consumed_by_runtime,
        "status": "promoted_to_reviewed_staging",
        **metrics,
    }


def run_role(
    request_pack_path: Path,
    pack: dict[str, Any],
    request: dict[str, Any],
    output_dir: Path,
    image_profile: image_provider.ImageProfile,
    vision_profile: vision_review.VisionProfile,
    *,
    request_index: int,
    max_attempts: int,
    generation_timeout: int,
    review_timeout: int,
    review_max_tokens: int,
) -> dict[str, Any]:
    current = copy.deepcopy(request)
    current.setdefault("worldbook_id", pack.get("worldbook_id"))
    attempts: list[dict[str, Any]] = []
    accepted_path: Path | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        attempt_dir = output_dir / f"attempt_{attempt:02d}"
        generated = candidate_generator.run_request(
            request_pack_path,
            pack,
            current,
            attempt_dir,
            image_profile,
            size_override=None,
            timeout=generation_timeout,
            live=True,
            credential_index=request_index + attempt - 1,
        )
        candidate_path = Path(str(generated["candidate_path"]))
        if not candidate_path.is_absolute():
            candidate_path = candidate_generator.ROOT / candidate_path
        review = review_candidate(
            current,
            candidate_path,
            vision_profile,
            timeout=review_timeout,
            max_tokens=review_max_tokens,
            credential_index=request_index + attempt - 1,
        )
        attempts.append(
            {
                "attempt": attempt,
                "candidate_path": str(candidate_path.resolve()),
                "candidate_sha256": sha256_file(candidate_path),
                "prompt_sha256": hashlib.sha256(str(current.get("prompt_brief") or "").encode("utf-8")).hexdigest(),
                "review": review,
            }
        )
        if review["status"] == "passed":
            accepted_path = candidate_path
            break
        current = repaired_request(current, review["failed_checks"])
    return {
        "request_id": request.get("request_id"),
        "role": request.get("role"),
        "status": "passed" if accepted_path else "failed_after_retries",
        "accepted_candidate_path": str(accepted_path.resolve()) if accepted_path else None,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


def run_closed_loop(
    request_pack_path: Path,
    pack: dict[str, Any],
    output_dir: Path,
    reviewed_dir: Path,
    image_profile: image_provider.ImageProfile,
    vision_profile: vision_review.VisionProfile,
    *,
    max_attempts: int = 2,
    max_workers: int = 3,
    generation_timeout: int = 240,
    review_timeout: int = 180,
    review_max_tokens: int = 1200,
) -> dict[str, Any]:
    requests = candidate_generator.selected_requests(pack, [])
    results_by_index: dict[int, dict[str, Any]] = {}
    failures_by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(requests) or 1))) as executor:
        futures = {
            executor.submit(
                run_role,
                request_pack_path,
                pack,
                request,
                output_dir,
                image_profile,
                vision_profile,
                request_index=index,
                max_attempts=max_attempts,
                generation_timeout=generation_timeout,
                review_timeout=review_timeout,
                review_max_tokens=review_max_tokens,
            ): (index, request)
            for index, request in enumerate(requests)
        }
        for future in as_completed(futures):
            index, request = futures[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:  # pragma: no cover - live provider failure path.
                failures_by_index[index] = {
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                    "error": f"{type(exc).__name__}:provider_or_review_call_failed",
                }
    results = [results_by_index[index] for index in sorted(results_by_index)]
    failures = [failures_by_index[index] for index in sorted(failures_by_index)]
    passed = {str(item["role"]): item for item in results if item["status"] == "passed"}
    critical_ready = CRITICAL_ROLES.issubset(passed)
    promotions = []
    if critical_ready:
        for role, result in passed.items():
            promotions.append(
                promote_candidate(
                    str(pack.get("node_id") or "map"),
                    role,
                    Path(str(result["accepted_candidate_path"])),
                    reviewed_dir,
                )
            )
    report = {
        "schema_version": REPORT_VERSION,
        "node_id": pack.get("node_id"),
        "worldbook_id": pack.get("worldbook_id"),
        "status": "runtime_visuals_ready" if critical_ready else "blocked_after_retries",
        "runtime_critical_roles": sorted(CRITICAL_ROLES),
        "runtime_critical_roles_ready": critical_ready,
        "summary": {
            "request_count": len(requests),
            "passed_count": len(passed),
            "failed_count": len(requests) - len(passed),
            "provider_failure_count": len(failures),
            "attempt_count": sum(int(item.get("attempt_count") or 0) for item in results),
            "provider_call_count": sum(int(item.get("attempt_count") or 0) for item in results),
            "vision_review_call_count": sum(int(item.get("attempt_count") or 0) for item in results),
            "promotion_count": len(promotions),
        },
        "results": results,
        "failures": failures,
        "promotions": promotions,
        "reviewed_backdrop_source_dir": str((reviewed_dir / "backdrops").resolve()) if critical_ready else None,
        "reviewed_texture_source_dir": str((reviewed_dir / "textures").resolve()) if critical_ready else None,
        "reviewed_component_source_dir": (
            str((reviewed_dir / "components").resolve())
            if critical_ready and (reviewed_dir / "components").is_dir()
            else None
        ),
        "policy": {
            "runtime_semantics_source": "MapRuntimePackage",
            "image_to_semantic_inference": False,
            "raw_prompt_stored": False,
            "raw_provider_response_stored": False,
            "automatic_promotion_scope": "reviewed_visual_staging_only",
            "unreviewed_candidate_player_visible": False,
        },
    }
    report_path = output_dir / REPORT_VERSION.replace(".v0.1", ".v0.1.json")
    candidate_generator.write_json(report_path, report)
    report["report_path"] = str(report_path.resolve())
    return report
