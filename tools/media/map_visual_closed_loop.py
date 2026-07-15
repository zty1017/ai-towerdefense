#!/usr/bin/env python3
"""Generate, review, repair, and stage layered map visual candidates."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
import shutil
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

try:
    from . import generate_layered_map_visual_candidates as candidate_generator
    from . import image_provider, png_pipeline, vision_review
    from . import map_visual_candidate_cache
except ImportError:  # pragma: no cover - direct script/import from tools path.
    import generate_layered_map_visual_candidates as candidate_generator  # type: ignore[no-redef]
    import image_provider  # type: ignore[no-redef]
    import map_visual_candidate_cache  # type: ignore[no-redef]
    import png_pipeline  # type: ignore[no-redef]
    import vision_review  # type: ignore[no-redef]


REPORT_VERSION = "map_visual_closed_loop_report.v0.1"
DEFAULT_MIN_VISION_SCORE = 0.78
CRITICAL_ROLES = {"terrain_base", "road_surface", "build_slot_platform"}
SYNCHRONOUS_PROVIDER_ROLES = {"terrain_base", "build_slot_platform"}
REVIEWED_FALLBACK_ROLES = {"road_surface", "build_slot_platform"}
CUTOUT_ROLES = {
    "build_slot_platform",
    "objective_foundation",
    "spawn_marker",
    "non_blocking_decoration",
}
DECORATION_VARIANT_ROLES = (
    "non_blocking_decoration_architecture",
    "non_blocking_decoration_natural",
    "non_blocking_decoration_debris",
    "non_blocking_decoration_prop",
)
CUTOUT_ROLES.update(DECORATION_VARIANT_ROLES)
DEFAULT_CACHE_DIR = candidate_generator.ROOT / "backend" / "data" / "map_visual_candidate_cache"
DEFAULT_MAX_TRANSPORT_RETRIES = 4
DEFAULT_TRANSPORT_BACKOFF_BASE = 2.0
DEFAULT_TRANSPORT_BACKOFF_CAP = 16.0
REVIEW_POLICY_REVISIONS = {
    "terrain_base": "material_tile_semantics_v5",
    "road_surface": "matte_non_emissive_material_v2",
    "build_slot_platform": "contrasting_solid_cutout_v2",
}


def review_policy_revision(
    role: str,
    secondary_style_profile: vision_review.VisionProfile | None = None,
) -> str:
    revision = REVIEW_POLICY_REVISIONS.get(role, "v1")
    if secondary_style_profile is not None:
        revision += f":secondary:{secondary_style_profile.name}"
    return revision


class MapVisualStageError(RuntimeError):
    """Keep provider failures diagnosable without retaining provider bodies."""

    def __init__(self, stage: str, cause: Exception):
        super().__init__(f"{stage}:{type(cause).__name__}")
        self.stage = stage
        self.cause_type = type(cause).__name__
COMMON_CHECKS = (
    "no_people_or_creatures",
    "no_readable_text_or_watermark",
    "no_incompatible_world_elements",
    "no_baked_ui_or_combat_effects",
)
ROLE_CHECKS = {
    "terrain_base": (
        "usable_terrain_material_tile",
        "material_contract_present",
        "uniform_material_scale_no_edge_frame",
        "no_symbolic_ground_markings",
        "no_baked_border_scenery_or_architecture",
        "no_baked_traversal_route",
        "no_baked_build_slots",
        "no_baked_objective_or_monument",
    ),
    "road_surface": (
        "usable_road_material_source",
        "no_large_scenery_or_architecture",
    ),
    "build_slot_platform": (
        "game_ready_material_finish",
        "consistent_game_camera",
        "single_component_only",
        "plain_white_background",
        "single_empty_low_foundation",
    ),
    "objective_foundation": (
        "game_ready_material_finish",
        "consistent_game_camera",
        "single_component_only",
        "plain_white_background",
        "single_compact_object",
        "recognizable_protected_objective_structure",
        "not_empty_foundation_or_platform",
    ),
    "spawn_marker": (
        "game_ready_material_finish",
        "consistent_game_camera",
        "single_component_only",
        "plain_white_background",
        "low_profile_marker",
    ),
    "non_blocking_decoration": (
        "game_ready_material_finish",
        "consistent_game_camera",
        "plain_white_background",
        "four_separated_quadrant_modules",
        "rich_border_scenery_modules",
        "no_square_ground_tiles_or_shared_plate",
    ),
}
for _decoration_role in DECORATION_VARIANT_ROLES:
    ROLE_CHECKS[_decoration_role] = (
        "game_ready_material_finish",
        "consistent_game_camera",
        "single_component_only",
        "plain_white_background",
        "usable_border_scenery_component",
        "world_specific_material_finish",
        "no_square_ground_tiles_or_shared_plate",
    )
REPAIR_TEXT = {
    "no_people_or_creatures": "remove every human, humanoid, creature, silhouette and character-like statue",
    "no_readable_text_or_watermark": "remove readable writing, labels, signage, logos and watermarks; abstract non-linguistic surface motifs are allowed",
    "no_incompatible_world_elements": "remove elements from any culture, technology level or world genre that conflicts with this request's style contract",
    "material_contract_present": "make the requested terrain materials, weathering and palette clearly readable without adding architecture or gameplay semantics",
    "uniform_material_scale_no_edge_frame": "use uniform texel density across the entire tile; remove edge vegetation, border rocks, vignette, diorama framing and large material islands",
    "no_symbolic_ground_markings": "remove every circle, ring, rune, emblem, socket, carved symbol and deliberately arranged ground marking, even if it could be interpreted as natural terrain",
    "premium_non_cartoon_finish": "replace flat mobile-game illustration, thick ink contours, cel shading and toy-like forms with high-fidelity painterly realism, nuanced material roughness and soft natural edges",
    "target_style_reference_match": "match this request's style contract and supplied style reference palette, material detail, texture density, contrast and rendering finish",
    "game_ready_material_finish": "use a polished premium strategy-game finish with readable materials and restrained detail",
    "consistent_game_camera": "use a consistent elevated three-quarter top-down game camera suitable for this asset set",
    "no_baked_ui_or_combat_effects": "remove UI, selection rings, health bars, beams, explosions, magic circles and combat action",
    "no_baked_traversal_route": "remove broad traversable roads, trails, route bands and directional paths; thin cracks and material veins are allowed",
    "no_baked_build_slots": "remove every deployment pad, circular platform, socket and tower base",
    "no_baked_objective_or_monument": "remove central objectives, monuments, portals, shrines and large landmarks",
    "no_baked_border_scenery_or_architecture": "remove walls, stairs, bridges, buildings, cliff borders, tree clusters, foreground props and complete scenery composition; retain only continuous traversable terrain",
    "no_large_scenery_or_architecture": "remove buildings, horizons, landscape scenery and unrelated props while retaining enough unobstructed road material for deterministic center cropping",
    "not_empty_foundation_or_platform": "add one compact vertical protected core above the low base so the result is a complete gameplay objective, never an empty pad, plinth or foundation",
    "no_square_ground_tiles_or_shared_plate": "remove every square model base, floor tile and shared ground plate; each border module needs an irregular transparent footprint that can blend into the map edge",
    "usable_border_scenery_component": "show exactly one compact reusable edge prop cluster with a readable silhouette and no surrounding scene",
    "world_specific_material_finish": "replace neutral gray-block or primitive prototype geometry with polished materials, color variation and detail appropriate to the current world style contract",
    "single_component_only": "show only the requested component with no unrelated props, surrounding scene, landscape or decorative frame",
    "plain_white_background": "use a completely flat pure-white background extending to all four canvas edges",
    "usable_terrain_material_tile": "show a reusable full-frame terrain material tile with consistent scale and no architectural, symbolic or gameplay-semantic object",
    "usable_road_material_source": "show a broad unobstructed paving-material sample that deterministic cropping can turn into a road brush",
    "no_complete_map_or_scene": "remove horizons, complete map layouts, miniature landscapes, staged dioramas and scene composition",
    "single_empty_low_foundation": "show exactly one empty low foundation with no tower, lantern or mounted object",
    "single_compact_object": "show exactly one compact object with a clear anchor and no extra props",
    "recognizable_protected_objective_structure": "show one compact world-specific protected objective structure mounted on a low foundation, not an empty pad or generic plinth",
    "low_profile_marker": "keep the entrance marker low-profile, restrained and free of creatures or warning icons",
    "four_separated_quadrant_modules": "place exactly one isolated scenery module in each quadrant with clear white gutters; visible grid lines are neither required nor desired",
    "rich_border_scenery_modules": "make the top two modules substantial architecture, ruin, cliff or vegetation edge prefabs and the bottom two medium border prop clusters, not four tiny icons",
    "deterministic_png_invalid": "return a standard non-interlaced RGB or RGBA PNG",
    "deterministic_canvas_too_small": "render the asset at the requested resolution with crisp edges",
    "deterministic_background_not_white": "replace the entire component background with flat neutral pure white",
    "deterministic_slot_foreground_too_light": "replace every pale, white, ivory, porcelain and polished-jade surface with medium-dark weathered charcoal stone; keep the inset center darker than the rim",
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


def resolve_cache_dir() -> Path:
    configured = os.environ.get("AI_TD_MAP_VISUAL_CACHE_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_CACHE_DIR


def _transport_backoff_delay(attempt: int, base: float, cap: float) -> float:
    return min(base * (2 ** attempt), cap)


def generate_with_transport_retries(
    run_once,
    *,
    max_retries: int = DEFAULT_MAX_TRANSPORT_RETRIES,
    base_backoff: float = DEFAULT_TRANSPORT_BACKOFF_BASE,
    max_backoff: float = DEFAULT_TRANSPORT_BACKOFF_CAP,
    retry_count: list[int] | None = None,
):
    """Call ``run_once`` with bounded transport-layer retries and backoff.

    Only :class:`image_provider.TransientProviderError` (identifiable transient
    HTTP 429/500/502/503/504 and transport errors) is retried within the same
    visual attempt; a transient 503 no longer consumes a visual repair attempt.
    All other errors propagate immediately. ``retry_count`` is a one-element
    list updated in place so callers can record the count even when the final
    retry raises. Returns ``(result, transport_retry_count)`` on success.

    No provider response body is retained: transient errors carry only the
    status code or cause type, never the upstream payload.
    """
    if retry_count is None:
        retry_count = [0]
    retry_count[0] = 0
    last_error: Exception | None = None
    total_attempts = max(1, max_retries + 1)
    for attempt in range(total_attempts):
        try:
            result = run_once()
            return result, retry_count[0]
        except image_provider.TransientProviderError as exc:
            last_error = exc
            if attempt + 1 < total_attempts:
                retry_count[0] += 1
                time.sleep(_transport_backoff_delay(attempt, base_backoff, max_backoff))
    raise last_error  # type: ignore[misc]


def review_with_transport_retries(
    run_once,
    *,
    max_retries: int = DEFAULT_MAX_TRANSPORT_RETRIES,
    base_backoff: float = DEFAULT_TRANSPORT_BACKOFF_BASE,
    max_backoff: float = DEFAULT_TRANSPORT_BACKOFF_CAP,
    retry_count: list[int] | None = None,
):
    """Retry transient multimodal-review transport failures without regenerating media."""
    if retry_count is None:
        retry_count = [0]
    retry_count[0] = 0
    total_attempts = max(1, max_retries + 1)
    for attempt in range(total_attempts):
        try:
            return run_once(), retry_count[0]
        except urllib.error.HTTPError as exc:
            transient = int(exc.code) in image_provider.TRANSIENT_HTTP_STATUS
            if not transient or attempt + 1 >= total_attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 >= total_attempts:
                raise
        retry_count[0] += 1
        time.sleep(_transport_backoff_delay(attempt, base_backoff, max_backoff))
    raise RuntimeError("unreachable review retry state")


def required_review_checks(role: str, *, has_style_reference: bool = False) -> list[str]:
    checks = [*COMMON_CHECKS]
    if has_style_reference:
        checks.append("target_style_reference_match")
    checks.extend(ROLE_CHECKS.get(role, ()))
    return checks


def cache_fingerprints(
    pack: dict[str, Any],
    request: dict[str, Any],
    image_profile: image_provider.ImageProfile,
    vision_profile: vision_review.VisionProfile,
    minimum_score: float,
    secondary_style_profile: vision_review.VisionProfile | None = None,
) -> tuple[str, str]:
    role = str(request.get("role") or "unknown")
    return (
        map_visual_candidate_cache.request_fingerprint(
            pack,
            request,
            image_profile_name=image_profile.name,
            image_model=image_profile.model,
        ),
        map_visual_candidate_cache.review_policy_fingerprint(
            role=role,
            required_checks=required_review_checks(
                role,
                has_style_reference=isinstance(request.get("style_reference"), dict),
            ),
            minimum_score=minimum_score,
            reviewer_profile_name=vision_profile.name,
            reviewer_model=vision_profile.model,
            policy_revision=review_policy_revision(role, secondary_style_profile),
        ),
    )


def image_profiles_for_request(
    request: dict[str, Any], default: image_provider.ImageProfile
) -> list[image_provider.ImageProfile]:
    names = request.get("image_profile_candidates")
    if not isinstance(names, list):
        return [default]
    profiles: list[image_provider.ImageProfile] = []
    for name in names:
        profile = image_provider.PROFILES.get(str(name))
        if profile is None or not profile.name.startswith("agnes_"):
            continue
        if profile.name not in {item.name for item in profiles}:
            profiles.append(profile)
    return profiles or [default]


def find_existing_candidates(
    output_dir: Path,
    pack: dict[str, Any],
    request: dict[str, Any],
    profiles: list[image_provider.ImageProfile],
    request_pack_path: Path | None = None,
) -> list[tuple[Path, image_provider.ImageProfile, dict[str, Any]]]:
    """Find every intact prior candidate for this role, including repair passes."""

    node_id = candidate_generator.safe_id(pack.get("node_id"))
    role = candidate_generator.safe_id(request.get("role"))
    request_id = str(request.get("request_id") or "")
    generation_reference = request.get("generation_reference")
    expected_reference = (
        str(generation_reference.get("sha256") or "")
        if isinstance(generation_reference, dict)
        else None
    )
    expected_prompt_sha = hashlib.sha256(
        str(request.get("prompt_brief") or "").encode("utf-8")
    ).hexdigest()
    profile_order = {profile.name: index for index, profile in enumerate(profiles)}
    found: list[
        tuple[int, int, Path, image_provider.ImageProfile, dict[str, Any]]
    ] = []
    for profile in profiles:
        filename = f"{node_id}.{role}.{profile.name}.candidate.png.candidate.json"
        for sidecar in output_dir.glob(f"attempt_*/{filename}"):
            try:
                metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if metadata.get("request_id") not in {None, request_id}:
                continue
            recorded_pack = metadata.get("request_pack_path")
            if recorded_pack and request_pack_path is not None:
                recorded_path = Path(str(recorded_pack))
                if not recorded_path.is_absolute():
                    recorded_path = candidate_generator.ROOT / recorded_path
                if recorded_path.resolve() != request_pack_path.resolve():
                    continue
            if metadata.get("generation_reference_sha256") != expected_reference:
                continue
            recorded_prompt_sha = str(metadata.get("prompt_sha256") or "")
            if recorded_prompt_sha and recorded_prompt_sha != expected_prompt_sha:
                continue
            candidate = Path(str(sidecar)[: -len(".candidate.json")])
            if not candidate.is_file():
                continue
            expected_image_sha = str(metadata.get("image_sha256") or "")
            if expected_image_sha and sha256_file(candidate) != expected_image_sha:
                continue
            attempt_name = sidecar.parent.name.removeprefix("attempt_")
            attempt_number = int(attempt_name) if attempt_name.isdigit() else 0
            found.append(
                (
                    attempt_number,
                    profile_order[profile.name],
                    candidate,
                    profile,
                    metadata,
                )
            )
    return [
        (path, profile, metadata)
        for _attempt, _order, path, profile, metadata in sorted(found)
    ]


def build_review_prompt(request: dict[str, Any]) -> str:
    role = str(request.get("role") or "unknown")
    required = required_review_checks(
        role,
        has_style_reference=isinstance(request.get("style_reference"), dict),
    )
    context = {
        "role": role,
        "worldbook_id": request.get("worldbook_id"),
        "required_checks": required,
        "intended_visual": request.get("prompt_sections", {}),
        "style_contract": request.get("style_contract", {}),
        "style_reference_present": isinstance(request.get("style_reference"), dict),
    }
    role_guidance = ""
    if role == "road_surface":
        role_guidance = (
            "当前第一张图已经是确定性中央裁切和边缘混合后的运行时道路材质预览。"
            "usable_road_material_source 只要求它能作为低透明度笔刷沿逻辑路径填充；"
            "轻微材质明暗和石块自身的浅透视不构成失败。世界样式明确要求的克制矿物色脉络"
            "不属于 UI、战斗特效或世界元素冲突，除非它形成魔法阵、按钮、光束或强烈自发光。"
        )
    elif role == "terrain_base":
        role_guidance = (
            "terrain_base 是无玩法语义的连续地表底材，之后会由确定性合成器添加边缘景观、道路、塔位、目标和出生点。"
            "整幅图都应由近乎平坦、可通行的地表组成；墙、楼梯、桥、建筑、围栏、悬崖边界、大树群和前景道具"
            "即使只出现在边缘也必须让 no_baked_border_scenery_or_architecture=false。"
            "usable_terrain_material_tile 要求画面边到边都是可复用地表；低矮苔藓、浅水、细碎石和小裂纹"
            "属于材质细节，不得当成前景道具或大型障碍。material_contract_present 只审查"
            "style_contract 指定的泥、石、金属、苔藓、积水、尘土等地表材料和色调是否可读，不要求出现建筑文化。"
            "uniform_material_scale_no_edge_frame 要求四边与中心具有一致的 texel 密度，不得用成排树木、岩石、"
            "深色晕影或连续高起伏围出边框；局部低矮苔藓与浅水分布不构成边框。任何清晰圆环、同心纹、符文、底座轮廓或人工排列标记都必须让"
            "no_symbolic_ground_markings=false，不得以“可能是自然浅坑”为理由放行。"
            "premium_non_cartoon_finish 必须严格审查：明显粗描边、均匀平涂、卡通比例、塑料玩具质感或"
            "廉价移动游戏插画都判 false；只有材质粗糙度和自然边缘达到高质量游戏材质才判 true。"
            "该项只判断卡通化与完成度，不能因为存在轻微方向光或材质高度感就判 false。"
            "自然地面、稀疏低矮植被和色调变化是允许的。普通铺地石板的接缝、"
            "随机裂纹、材质色带和透视线不属于 traversal route；只有具有连续方向、明显边界并贯穿画面的"
            "道路或小径才算烘焙路线。位于外围的小钟、树、柱、灯笼或屋舍不是 objective/monument；"
            "只有占据战场中心、明显承担玩法目标视觉焦点的大型地标才算失败。"
            "no_incompatible_world_elements 只审查明确混入另一文化或技术时代的元素，不得用它惩罚石板形状、"
            "自然地貌、材质细节、边缘建筑数量或与文字描述的轻微差异。"
        )
    return (
        "你是严格的 2D/伪3D 塔防地图分层素材审查器。只判断图片是否满足指定 role，"
        "不要因为画面好看而放宽要求。所有 required_checks 都必须明确判断。\n"
        "只输出合法 JSON 对象，字段为 score、checks、notes。score 是 0 到 1 的数字；"
        "checks 是对象，键必须覆盖 required_checks，值只能是 true 或 false；notes 是简短字符串数组。"
        "第一张图是待审候选；如果提供第二张图，它是只用于画风、材质细节、色调和完成度比较的基准图，"
        "不得要求候选复制基准图布局。没有第二张图时，不得因缺少参考图而扣分；"
        "no_incompatible_world_elements 只在明显混入不兼容文化、科技或世界类型时判 false，"
        "不得因为轻微色差、笔触或材质明暗差异判 false。材质角色的无缝化、裁切和缩放由确定性后处理完成，"
        "不要要求原始候选已经像素级无缝。道路候选允许带边缘，只要中央有足够纯净材质可供裁切；"
        "地形中的细裂纹和材质脉络不等于可通行路线。no_readable_text_or_watermark 允许抽象、不可读的装饰纹样。"
        "组件可使用高质量 3D、手绘或混合渲染，只要游戏可用且镜头一致。"
        f"{role_guidance}"
        "score 必须与 checks 一致：全部通过时不得低于 0.8。看不清或不确定时填 false。不得输出 Markdown。\n"
        f"审查上下文：{json.dumps(context, ensure_ascii=False)}"
    )


def deterministic_issues(
    path: Path, role: str, expected_ratio: float | None = None
) -> tuple[list[str], dict[str, Any]]:
    try:
        image = png_pipeline.read_png(path)
    except (OSError, ValueError):
        return ["deterministic_png_invalid"], {}
    issues: list[str] = []
    minimum_dimensions = {
        "terrain_base": (512, 512),
        "road_surface": (384, 192),
    }
    minimum_width, minimum_height = minimum_dimensions.get(role, (512, 512))
    if image.width < minimum_width or image.height < minimum_height:
        issues.append("deterministic_canvas_too_small")
    metrics: dict[str, Any] = {"width": image.width, "height": image.height}
    if role in {"terrain_base", "road_surface"} and expected_ratio:
        ratio = image.width / image.height
        metrics["aspect_ratio"] = round(ratio, 4)
        if abs(ratio - expected_ratio) > 0.04:
            issues.append("deterministic_aspect_ratio_mismatch")
    if role in CUTOUT_ROLES:
        background = png_pipeline.estimate_background_rgb(image)
        luma = (background[0] * 299 + background[1] * 587 + background[2] * 114) // 1000
        chroma = max(background) - min(background)
        metrics.update({"estimated_background_rgb": list(background), "background_luma": luma, "background_chroma": chroma})
        if luma < 225 or chroma > 30:
            issues.append("deterministic_background_not_white")
        if role == "build_slot_platform":
            foreground_pixels = 0
            pale_foreground_pixels = 0
            for offset in range(0, len(image.pixels), 4):
                red, green, blue = image.pixels[offset : offset + 3]
                distance = max(
                    abs(red - background[0]),
                    abs(green - background[1]),
                    abs(blue - background[2]),
                )
                if distance < 12:
                    continue
                foreground_pixels += 1
                pixel_luma = (red * 299 + green * 587 + blue * 114) // 1000
                if pixel_luma >= 185 and max(red, green, blue) - min(red, green, blue) <= 42:
                    pale_foreground_pixels += 1
            pale_ratio = pale_foreground_pixels / max(1, foreground_pixels)
            metrics["pale_foreground_ratio"] = round(pale_ratio, 4)
            if pale_ratio > 0.34:
                issues.append("deterministic_slot_foreground_too_light")
    return issues, metrics


def normalize_vision_review(
    raw: dict[str, Any],
    request: dict[str, Any],
    *,
    minimum_score: float = DEFAULT_MIN_VISION_SCORE,
) -> dict[str, Any]:
    role = str(request.get("role") or "unknown")
    required = required_review_checks(
        role,
        has_style_reference=isinstance(request.get("style_reference"), dict),
    )
    raw_checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    checks = {key: raw_checks.get(key) is True for key in required}
    try:
        score = max(0.0, min(1.0, float(raw.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    failed = [key for key, passed in checks.items() if not passed]
    if not failed and score < 0.8:
        score = 0.8
    return {
        "score": round(score, 4),
        "checks": checks,
        "failed_checks": failed,
        "notes": [str(item)[:240] for item in raw.get("notes", []) if isinstance(item, str)][:8],
        "status": "passed" if not failed and score >= minimum_score else "failed",
    }


def build_secondary_style_review_prompt(request: dict[str, Any]) -> str:
    contract = request.get("style_contract")
    contract = contract if isinstance(contract, dict) else {}
    generation_briefs = contract.get("generation_briefs")
    generation_briefs = generation_briefs if isinstance(generation_briefs, dict) else {}
    prompt_sections = request.get("prompt_sections")
    prompt_sections = prompt_sections if isinstance(prompt_sections, dict) else {}
    context = {
        "theme_terms": contract.get("theme_terms") or [],
        "rendering_style": generation_briefs.get("rendering_style"),
        "terrain_brief": prompt_sections.get("environment"),
    }
    return (
        "只审查这张塔防环境底图的美术风格，不审查路线、塔位、人物、文字或构图。"
        "premium_non_cartoon_finish 只有在材质粗糙度、光照层次、自然边缘和整体完成度达到"
        "高质量半写实游戏环境图时才为 true；粗描边、均匀平涂、卡通比例、塑料玩具感或"
        "廉价移动游戏插画必须为 false。material_contract_present 只有在画面清楚体现 terrain_brief"
        "要求的地表材料、风化状态与色调时才为 true；不要求也不允许用建筑或地标证明世界类型。"
        "只返回合法 JSON，不要 Markdown，字段固定为："
        '{"premium_non_cartoon_finish":true或false,'
        '"material_contract_present":true或false,'
        '"style_category":"cartoon|stylized|semi_realistic|realistic",'
        '"notes":["最多两条短说明"]}。'
        f"审查上下文：{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def normalize_secondary_style_review(raw: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "premium_non_cartoon_finish": raw.get("premium_non_cartoon_finish") is True,
        "material_contract_present": raw.get("material_contract_present") is True,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "failed_checks": [key for key, passed in checks.items() if not passed],
        "style_category": str(raw.get("style_category") or "unknown")[:40],
        "notes": [
            str(item)[:240]
            for item in raw.get("notes", [])
            if isinstance(item, str)
        ][:2],
    }


def review_candidate(
    request: dict[str, Any],
    candidate_path: Path,
    request_pack_path: Path,
    profile: vision_review.VisionProfile,
    *,
    timeout: int,
    max_tokens: int,
    credential_index: int = 0,
    minimum_score: float = DEFAULT_MIN_VISION_SCORE,
    secondary_style_profile: vision_review.VisionProfile | None = None,
) -> dict[str, Any]:
    contract = request.get("output_contract")
    contract = contract if isinstance(contract, dict) else {}
    ratio_text = str(contract.get("ratio") or "")
    expected_ratio = None
    if ":" in ratio_text:
        left, right = ratio_text.split(":", 1)
        expected_ratio = int(left) / int(right)
    role = str(request.get("role") or "")
    review_path = candidate_path
    if role == "terrain_base":
        review_path = candidate_path.with_suffix(".review.png")
        postprocess_terrain_texture(candidate_path, review_path)
        expected_ratio = 1.0
    elif role == "road_surface":
        review_path = candidate_path.with_suffix(".review.png")
        postprocess_road_texture(candidate_path, review_path)
        expected_ratio = 2.0
    deterministic, metrics = deterministic_issues(review_path, role, expected_ratio)
    review_item = {
        "stable_internal_id": str(request.get("request_id") or "map_visual"),
        "media_role": str(request.get("role") or "unknown"),
        "local_path": review_path,
        "width": metrics.get("width"),
        "height": metrics.get("height"),
    }
    review_items = [review_item]
    style_reference = request.get("style_reference")
    if isinstance(style_reference, dict):
        reference_path = candidate_generator.resolve_reference_path(
            str(style_reference.get("local_path") or ""), request_pack_path
        )
        if candidate_generator.sha256_file(reference_path) != str(
            style_reference.get("sha256") or ""
        ):
            raise ValueError("style reference sha256 mismatch")
        review_items.append(
            {
                "stable_internal_id": "target_style_reference",
                "media_role": "style_reference",
                "local_path": reference_path,
            }
        )
    raw_text = vision_review.call_vision_model(
        profile,
        build_review_prompt(request),
        review_items,
        max_tokens=max_tokens,
        timeout=timeout,
        credential_index=credential_index,
    )
    parsed = vision_review.extract_json(raw_text) or {}
    normalized = normalize_vision_review(parsed, request, minimum_score=minimum_score)
    failed = list(dict.fromkeys([*deterministic, *normalized["failed_checks"]]))
    secondary_style_review = None
    if (
        role == "terrain_base"
        and not failed
        and normalized["status"] == "passed"
        and secondary_style_profile is not None
    ):
        try:
            secondary_raw_text = vision_review.call_vision_model(
                secondary_style_profile,
                build_secondary_style_review_prompt(request),
                [review_item],
                max_tokens=min(max_tokens, 1000),
                timeout=min(timeout, 45),
                credential_index=credential_index,
            )
            secondary_parsed = vision_review.extract_json(secondary_raw_text) or {}
            secondary_style_review = normalize_secondary_style_review(secondary_parsed)
            failed = list(
                dict.fromkeys([*failed, *secondary_style_review["failed_checks"]])
            )
            for check, passed in secondary_style_review["checks"].items():
                normalized["checks"][check] = passed
            normalized["notes"] = [
                *normalized.get("notes", []),
                *secondary_style_review.get("notes", []),
            ][:8]
        except Exception as exc:  # Best-effort cross-provider style audit.
            secondary_style_review = {
                "status": "deferred_provider_unavailable",
                "checks": {},
                "failed_checks": [],
                "style_category": "not_checked",
                "notes": [f"secondary style review deferred: {type(exc).__name__}"],
            }
    normalized.update(
        {
            "status": "passed" if not failed and normalized["status"] == "passed" else "failed",
            "failed_checks": failed,
            "deterministic_metrics": metrics,
            "reviewer_profile": profile.name,
            "raw_response_stored": False,
            "secondary_style_review": secondary_style_review,
        }
    )
    return normalized


def repaired_request(request: dict[str, Any], failed_checks: list[str]) -> dict[str, Any]:
    repaired = copy.deepcopy(request)
    sections = repaired.get("prompt_sections")
    sections = dict(sections) if isinstance(sections, dict) else {}
    corrections = [REPAIR_TEXT[check] for check in failed_checks if check in REPAIR_TEXT]
    role = str(repaired.get("role") or "")
    if role == "terrain_base":
        failed = set(failed_checks)
        if failed.intersection(
            {
                "usable_terrain_material_tile",
                "no_baked_border_scenery_or_architecture",
                "no_baked_traversal_route",
                "no_baked_build_slots",
                "no_baked_objective_or_monument",
            }
        ):
            sections["composition"] = (
                "wide elevated three-quarter top-down material plane; fill the entire frame edge to edge "
                "with one continuous nearly flat traversable ground substrate; remove every wall, building, "
                "cliff boundary, tree cluster, bridge, stair, fence and foreground prop; use natural diffuse "
                "material variation without a directional strip, branch, lane or endpoint; "
                "no road, trail, deployment pad, socket, objective, portal, unit or interaction marker"
            )
            sections["quality"] = (
                "presentation-ready premium terrain substrate with coherent material roughness and no baked "
                "scenery composition; every border prop, route, build slot, objective, spawn and runtime "
                "highlight will be added later by deterministic composition"
            )
    elif role == "objective_foundation" and set(failed_checks).intersection(
        {
            "no_incompatible_world_elements",
            "recognizable_protected_objective_structure",
            "not_empty_foundation_or_platform",
            "single_compact_object",
        }
    ):
        sections["subject"] = (
            "one compact protected battlefield ward anchor: a short solid opaque weathered-stone monolith "
            "secured by restrained dark iron braces on one low irregular stone footing; the vertical core is "
            "sealed, inert, readable and completely solid"
        )
        sections["environment"] = (
            "isolated on a flat pure-white studio background; no terrain patch, mud puddle, floor tile, "
            "wooden deck, square base plate, surrounding scenery or detached props"
        )
        sections["composition"] = (
            "consistent elevated three-quarter top-down game asset view; exactly one compact solid object; "
            "clear bottom-center anchor, generous white margin, no scene or diorama"
        )
        sections["quality"] = (
            "premium semi-realistic game component with an opaque closed silhouette; absolutely no glass, "
            "transparent chamber, crystal, flame, furnace, lamp, glow, smoke, machinery, dome, roof, doorway, "
            "platform deck, building, text or miniature environment"
        )
    elif role in DECORATION_VARIANT_ROLES:
        original_sections = request.get("prompt_sections")
        original_sections = original_sections if isinstance(original_sections, dict) else {}
        original_subject = str(original_sections.get("subject") or sections.get("subject") or "")
        sections["subject"] = (
            f"{original_subject}; correction: render only the one exact named object in this sentence and no "
            "other object category"
        )
        sections["environment"] = (
            "the single object rests directly on a completely flat pure-white studio background; no soil, "
            "puddle, vegetation mat, rubble pile, floor tile, circular disk, glass plate or shared base"
        )
        sections["composition"] = (
            "consistent elevated three-quarter top-down game asset view; one centered object and no second "
            "object category; generous white margin and no scene or diorama"
        )
        sections["quality"] = (
            "premium semi-realistic world-specific material finish with one clean silhouette and a clear "
            "bottom-center anchor; no cartoon proportions, multiple props, landscape, frame, text, glow or UI"
        )
    contract = repaired.get("style_contract")
    if isinstance(contract, dict) and any(
        check in {
            "no_incompatible_world_elements",
            "target_style_reference_match",
            "game_ready_material_finish",
        }
        for check in failed_checks
    ):
        corrections.append(
            "exact style contract: "
            + json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    if corrections:
        correction_text = "Correction pass: " + "; ".join(dict.fromkeys(corrections))
        sections["quality"] = f"{sections.get('quality', '')}; {correction_text}".strip("; ")
    repaired["prompt_sections"] = sections
    repaired["prompt_brief"] = compose_prompt(sections)
    repaired["repair_source_checks"] = list(dict.fromkeys(failed_checks))
    return repaired


def postprocess_component(
    source: Path,
    output: Path,
    *,
    keep_largest: bool,
    remove_white_islands: bool = True,
    matte_threshold: int = 42,
) -> dict[str, Any]:
    image = png_pipeline.read_png(source)
    image = png_pipeline.remove_edge_matte_background(image, threshold=matte_threshold)
    if remove_white_islands:
        image = png_pipeline.remove_near_white_background_islands(image, min_pixels=64)
    image = png_pipeline.remove_small_alpha_components(image, min_pixels=96)
    if keep_largest:
        image = png_pipeline.keep_largest_alpha_component(image)
    image = png_pipeline.crop_and_pad(image, padding=32)
    image = png_pipeline.normalize_canvas(image, square=True, min_size=512)
    image = png_pipeline.clear_transparent_rgb(image)
    png_pipeline.write_png(output, image)
    return {"width": image.width, "height": image.height, "sha256": sha256_file(output)}


def postprocess_decoration_atlas(source: Path, output: Path) -> dict[str, Any]:
    image = png_pipeline.read_png(source)
    image = png_pipeline.remove_edge_matte_background(image, threshold=42)
    image = png_pipeline.remove_near_white_background_islands(image, min_pixels=64)
    image = png_pipeline.remove_small_alpha_components(image, min_pixels=96)
    image = png_pipeline.normalize_canvas(image, square=True, min_size=1024)
    image = png_pipeline.clear_transparent_rgb(image)
    png_pipeline.write_png(output, image)
    return {"width": image.width, "height": image.height, "sha256": sha256_file(output)}


def pack_decoration_components(
    component_paths: list[Path], output: Path
) -> dict[str, Any]:
    """Pack four reviewed cutouts into the runtime's deterministic 2x2 atlas."""

    if len(component_paths) != 4:
        raise ValueError("decoration atlas requires exactly four reviewed components")
    images = [png_pipeline.read_png(path) for path in component_paths]
    cell_size = max(max(image.width, image.height) for image in images)
    normalized = [
        png_pipeline.normalize_canvas(image, square=True, min_size=cell_size)
        for image in images
    ]
    atlas = png_pipeline.transparent_image(cell_size * 2, cell_size * 2)
    for image, (x, y) in zip(
        normalized,
        ((0, 0), (cell_size, 0), (0, cell_size), (cell_size, cell_size)),
    ):
        png_pipeline.paste(atlas, image, x, y)
    atlas = png_pipeline.clear_transparent_rgb(atlas)
    output.parent.mkdir(parents=True, exist_ok=True)
    png_pipeline.write_png(output, atlas)
    return {
        "width": atlas.width,
        "height": atlas.height,
        "cell_size": cell_size,
        "sha256": sha256_file(output),
    }


def postprocess_terrain_texture(source: Path, output: Path) -> dict[str, Any]:
    """Extract a large square terrain field and blend opposite edges.

    The compositor consumes this as one full-frame material field. Keeping the
    largest square sample avoids the obvious repeated-grid pattern produced by
    shrinking a reviewed candidate to a small texture tile.
    """

    image = png_pipeline.read_png(source)
    size = min(image.width, image.height)
    image = png_pipeline.center_crop_dimensions(image, size, size)
    image = png_pipeline.edge_blended_seamless_tile(image, blend_fraction=0.12)
    png_pipeline.write_png(output, image)
    return {
        "width": image.width,
        "height": image.height,
        "aspect_ratio": round(image.width / image.height, 4),
        "sha256": sha256_file(output),
    }


def postprocess_road_texture(source: Path, output: Path) -> dict[str, Any]:
    """Extract a material sample and guarantee matching edges for route pattern fill."""

    image = png_pipeline.read_png(source)
    image = png_pipeline.center_crop_fraction(image, 0.68)
    target_height = min(image.height, image.width // 2)
    image = png_pipeline.center_crop_dimensions(
        image, target_height * 2, target_height
    )
    image = png_pipeline.edge_blended_seamless_tile(image)
    png_pipeline.write_png(output, image)
    return {
        "width": image.width,
        "height": image.height,
        "aspect_ratio": round(image.width / image.height, 4),
        "sha256": sha256_file(output),
    }


def _hex_rgb(value: object, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def derive_road_surface_from_terrain(
    terrain_source: Path,
    output: Path,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a quiet road brush from the reviewed world-specific terrain.

    This is the deterministic ReAct fallback for illustration-oriented image
    providers that keep turning material requests into glowing map objects.
    """

    image = png_pipeline.read_png(terrain_source)
    image = png_pipeline.center_crop_fraction(image, 0.34)
    target_height = min(image.height, image.width // 2)
    image = png_pipeline.center_crop_dimensions(
        image, target_height * 2, target_height
    )
    contract = request.get("style_contract") if isinstance(request, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    palette = contract.get("palette")
    palette = palette if isinstance(palette, dict) else {}
    road_base = _hex_rgb(palette.get("road_base"), (128, 132, 124))
    road_edge = _hex_rgb(palette.get("road_edge"), (108, 104, 92))
    accent = _hex_rgb(palette.get("accent"), (154, 124, 72))
    # A road must remain readable after multiply-compositing without becoming
    # the pale translucent ribbon that illustration models tend to produce.
    # Treat the world palette as hue guidance and normalize it to a quiet
    # medium-dark material value.
    target = tuple(
        round((road_base[index] * 0.45 + road_edge[index] * 0.35 + accent[index] * 0.20) * 0.54)
        for index in range(3)
    )
    target = (
        min(160, target[0] + 6),
        min(160, target[1]),
        max(34, target[2] - 8),
    )
    pixels = bytearray(image.pixels)
    for offset in range(0, len(pixels), 4):
        red, green, blue = pixels[offset], pixels[offset + 1], pixels[offset + 2]
        luma = (red * 299 + green * 587 + blue * 114) // 1000
        source = (
            round(luma * 0.76 + red * 0.24),
            round(luma * 0.76 + green * 0.24),
            round(luma * 0.76 + blue * 0.24),
        )
        for channel in range(3):
            value = round(source[channel] * 0.46 + target[channel] * 0.54)
            pixels[offset + channel] = max(34, min(160, value))
        pixels[offset + 3] = 255
    derived = png_pipeline.PngImage(image.width, image.height, pixels)
    derived = png_pipeline.edge_blended_seamless_tile(derived, blend_fraction=0.14)
    png_pipeline.write_png(output, derived)
    return {
        "role": "road_surface",
        "source_path": str(terrain_source.resolve()),
        "reviewed_path": str(output.resolve()),
        "consumed_by_current_runtime": True,
        "status": "derived_from_reviewed_terrain",
        "derivation_graph": [
            "reviewed_terrain_backdrop",
            "center_material_sample",
            "desaturate_and_tone_match",
            "edge_seam_blend",
            "runtime_road_brush",
        ],
        "width": derived.width,
        "height": derived.height,
        "sha256": sha256_file(output),
    }


def promote_candidate(node_id: str, role: str, source: Path, reviewed_dir: Path) -> dict[str, Any]:
    if role == "terrain_base":
        output = reviewed_dir / "textures" / "terrain_tile.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        metrics = postprocess_terrain_texture(source, output)
        consumed_by_runtime = True
    elif role == "road_surface":
        output = reviewed_dir / "textures" / "road_tile.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        metrics = postprocess_road_texture(source, output)
        consumed_by_runtime = True
    elif role == "non_blocking_decoration":
        output = reviewed_dir / "components" / "non_blocking_decoration.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        metrics = postprocess_decoration_atlas(source, output)
        consumed_by_runtime = True
    else:
        filename = {"build_slot_platform": "slot_tile.png"}.get(role, f"{role}.png")
        folder = "textures" if role == "build_slot_platform" else "components"
        output = reviewed_dir / folder / filename
        metrics = postprocess_component(
            source,
            output,
            keep_largest=role not in DECORATION_VARIANT_ROLES,
            remove_white_islands=True,
            matte_threshold=64 if role == "build_slot_platform" else 52,
        )
        consumed_by_runtime = role in {"road_surface", "build_slot_platform"}
    return {
        "role": role,
        "source_path": str(source.resolve()),
        "reviewed_path": str(output.resolve()),
        "consumed_by_current_runtime": consumed_by_runtime,
        "status": "promoted_to_reviewed_staging",
        **metrics,
    }


def reuse_reviewed_fallback(
    node_id: str, role: str, source_dir: Path, reviewed_dir: Path
) -> dict[str, Any] | None:
    names = {
        "road_surface": ("textures", f"{node_id}.road_tile.png", "road_tile.png"),
        "build_slot_platform": ("textures", f"{node_id}.slot_tile.png", "slot_tile.png"),
    }
    spec = names.get(role)
    if spec is None:
        return None
    folder, source_name, output_name = spec
    source = source_dir / folder / source_name
    if not source.is_file():
        return None
    output = reviewed_dir / folder / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    image = png_pipeline.read_png(output)
    return {
        "role": role,
        "source_path": str(source.resolve()),
        "reviewed_path": str(output.resolve()),
        "consumed_by_current_runtime": True,
        "status": "reused_reviewed_fallback",
        "width": image.width,
        "height": image.height,
        "sha256": sha256_file(output),
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
    minimum_score: float = DEFAULT_MIN_VISION_SCORE,
    credential_locks: list[threading.Lock] | None = None,
    candidate_cache: map_visual_candidate_cache.CandidateCache | None = None,
    max_transport_retries: int = DEFAULT_MAX_TRANSPORT_RETRIES,
    transport_backoff_base: float = DEFAULT_TRANSPORT_BACKOFF_BASE,
    transport_backoff_cap: float = DEFAULT_TRANSPORT_BACKOFF_CAP,
    attempt_offset: int | None = None,
) -> dict[str, Any]:
    current = copy.deepcopy(request)
    current.setdefault("worldbook_id", pack.get("worldbook_id"))
    secondary_style_profile = None
    secondary_mode = os.environ.get("AI_TD_MAP_SECONDARY_STYLE_REVIEW", "off").strip().lower()
    if (
        str(request.get("role") or "") == "terrain_base"
        and secondary_mode in {"1", "true", "on", "required"}
    ):
        candidate_secondary = vision_review.PROFILES.get("ark_kimi_k2_6")
        if candidate_secondary is not None and any(
            os.environ.get(env_key) for env_key in candidate_secondary.env_keys
        ):
            secondary_style_profile = candidate_secondary
    base_prompt_sha = hashlib.sha256(
        str(request.get("prompt_brief") or "").encode("utf-8")
    ).hexdigest()
    attempts: list[dict[str, Any]] = []
    accepted_path: Path | None = None
    request_fp, policy_fp = cache_fingerprints(
        pack,
        request,
        image_profiles_for_request(request, image_profile)[0],
        vision_profile,
        minimum_score,
        secondary_style_profile,
    )
    image_profiles = image_profiles_for_request(request, image_profile)
    cache_status: dict[str, Any] = {"status": "disabled"}
    if candidate_cache is not None:
        restored_path = (
            output_dir
            / "cache_restore"
            / f"{candidate_generator.safe_id(pack.get('node_id'))}."
            f"{candidate_generator.safe_id(request.get('role'))}.cached.candidate.png"
        )
        restored = candidate_cache.restore(
            request_fingerprint_value=request_fp,
            review_policy_fingerprint_value=policy_fp,
            output_path=restored_path,
        )
        if restored is None:
            role = str(request.get("role") or "")
            required = required_review_checks(
                role,
                has_style_reference=isinstance(request.get("style_reference"), dict),
            )
            restored = candidate_cache.restore_compatible(
                review_policy_fingerprint_value=policy_fp,
                base_prompt_sha256=base_prompt_sha,
                source_prompt_sha256=base_prompt_sha,
                provenance_match={
                    "node_id": pack.get("node_id"),
                    "worldbook_id": pack.get("worldbook_id"),
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                },
                required_checks=required,
                minimum_score=minimum_score,
                output_path=restored_path,
                required_policy_revision=review_policy_revision(
                    role, secondary_style_profile
                ),
            )
        if restored is not None:
            role = str(request.get("role") or "")
            contract = request.get("output_contract")
            contract = contract if isinstance(contract, dict) else {}
            ratio_text = str(contract.get("ratio") or "")
            expected_ratio = None
            if ":" in ratio_text:
                left, right = ratio_text.split(":", 1)
                expected_ratio = int(left) / int(right)
            deterministic_path = restored_path
            if role == "terrain_base":
                deterministic_path = restored_path.with_suffix(".review.png")
                postprocess_terrain_texture(restored_path, deterministic_path)
                expected_ratio = 1.0
            elif role == "road_surface":
                deterministic_path = restored_path.with_suffix(".review.png")
                postprocess_road_texture(restored_path, deterministic_path)
                expected_ratio = 2.0
            deterministic, metrics = deterministic_issues(
                deterministic_path, role, expected_ratio
            )
            review = copy.deepcopy(restored["review"])
            required = required_review_checks(
                role,
                has_style_reference=isinstance(request.get("style_reference"), dict),
            )
            checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}
            score = float(review.get("score") or 0)
            failed = list(
                dict.fromkeys(
                    [
                        *deterministic,
                        *[name for name in required if checks.get(name) is not True],
                    ]
                )
            )
            if not failed and score >= minimum_score:
                review.update(
                    {
                        "status": "passed",
                        "failed_checks": [],
                        "deterministic_metrics": metrics,
                        "cache_review_reused": True,
                    }
                )
                return {
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                    "status": "passed",
                    "accepted_candidate_path": str(restored_path.resolve()),
                    "attempt_count": 0,
                    "attempts": [],
                    "cache": {
                        "status": "hit",
                        "request_fingerprint": request_fp,
                        "review_policy_fingerprint": policy_fp,
                        "cache_entry_path": restored["cache_entry_path"],
                        "candidate_sha256": restored["candidate_sha256"],
                        "match_mode": restored.get("match_mode", "exact_fingerprint"),
                        "review": review,
                    },
                }
            restored_path.unlink(missing_ok=True)
            cache_status = {
                "status": "rejected_by_current_policy",
                "request_fingerprint": request_fp,
                "review_policy_fingerprint": policy_fp,
                "failed_checks": failed,
            }
        else:
            cache_status = {
                "status": "miss",
                "request_fingerprint": request_fp,
                "review_policy_fingerprint": policy_fp,
            }
    best_existing_review: dict[str, Any] | None = None
    best_existing_pass: tuple[
        Path, image_provider.ImageProfile, dict[str, Any], dict[str, Any]
    ] | None = None
    existing_candidates = find_existing_candidates(
        output_dir, pack, request, image_profiles, request_pack_path
    )
    for existing_index, (
        existing_candidate,
        existing_profile,
        existing_metadata,
    ) in enumerate(existing_candidates):
        credential_index = request_index + existing_index
        lock = (
            credential_locks[credential_index % len(credential_locks)]
            if credential_locks
            else contextlib.nullcontext()
        )
        review_retry_count_holder = [0]
        try:
            with lock:
                review, review_transport_retry_count = review_with_transport_retries(
                    lambda: review_candidate(
                        request,
                        existing_candidate,
                        request_pack_path,
                        vision_profile,
                        timeout=review_timeout,
                        max_tokens=review_max_tokens,
                        credential_index=credential_index,
                        minimum_score=minimum_score,
                        secondary_style_profile=secondary_style_profile,
                    ),
                    max_retries=max_transport_retries,
                    base_backoff=transport_backoff_base,
                    max_backoff=transport_backoff_cap,
                    retry_count=review_retry_count_holder,
                )
        except Exception as exc:
            attempts.append(
                {
                    "attempt": 0,
                    "status": "reused_candidate_review_error",
                    "source_attempt_dir": existing_candidate.parent.name,
                    "candidate_path": str(existing_candidate.resolve()),
                    "candidate_sha256": sha256_file(existing_candidate),
                    "error": f"{type(exc).__name__}:external_call_failed",
                    "review_transport_retry_count": review_retry_count_holder[0],
                }
            )
        else:
            attempts.append(
                {
                    "attempt": 0,
                    "status": "reused_candidate_reviewed",
                    "source_attempt_dir": existing_candidate.parent.name,
                    "candidate_path": str(existing_candidate.resolve()),
                    "candidate_sha256": sha256_file(existing_candidate),
                    "prompt_sha256": str(
                        existing_metadata.get("prompt_sha256") or base_prompt_sha
                    ),
                    "review_transport_retry_count": review_transport_retry_count,
                    "review": review,
                }
            )
            if review["status"] == "passed":
                if best_existing_pass is None or float(review.get("score") or 0) > float(
                    best_existing_pass[3].get("score") or 0
                ):
                    best_existing_pass = (
                        existing_candidate,
                        existing_profile,
                        existing_metadata,
                        review,
                    )
                continue
            if best_existing_review is None or float(review.get("score") or 0) > float(
                best_existing_review.get("score") or 0
            ):
                best_existing_review = review
    if best_existing_pass is not None:
        selected_candidate, selected_profile, selected_metadata, selected_review = (
            best_existing_pass
        )
        accepted_path = selected_candidate
        if candidate_cache is not None:
            stored = candidate_cache.store(
                request_fingerprint_value=request_fp,
                review_policy_fingerprint_value=policy_fp,
                candidate_path=selected_candidate,
                review=selected_review,
                base_prompt_sha256=base_prompt_sha,
                source_prompt_sha256=str(
                    selected_metadata.get("prompt_sha256") or base_prompt_sha
                ),
                provenance={
                    "node_id": pack.get("node_id"),
                    "worldbook_id": pack.get("worldbook_id"),
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                    "image_profile": selected_profile.name,
                    "reviewer_profile": vision_profile.name,
                    "review_policy_revision": review_policy_revision(
                        str(request.get("role") or ""), secondary_style_profile
                    ),
                    "reused_candidate": True,
                    "selection_policy": "highest_review_score",
                },
            )
            cache_status = {
                "status": "stored",
                "request_fingerprint": request_fp,
                "review_policy_fingerprint": policy_fp,
                **stored,
            }
        return {
            "request_id": request.get("request_id"),
            "role": request.get("role"),
            "status": "passed",
            "accepted_candidate_path": str(selected_candidate.resolve()),
            "accepted_image_profile": selected_profile.name,
            "attempt_count": 0,
            "attempts": attempts,
            "cache": cache_status,
        }
    if best_existing_review is not None:
        current = repaired_request(request, best_existing_review["failed_checks"])
    if attempt_offset is None:
        existing_attempt_numbers = [
            int(path.name.removeprefix("attempt_"))
            for path in output_dir.glob("attempt_[0-9][0-9]")
            if path.is_dir() and path.name.removeprefix("attempt_").isdigit()
        ]
        attempt_offset = max(existing_attempt_numbers, default=0)
    for attempt in range(1, max(1, max_attempts) + 1):
        attempt_number = attempt_offset + attempt
        attempt_dir = output_dir / f"attempt_{attempt_number:02d}"
        active_image_profile = image_profiles[(attempt - 1) % len(image_profiles)]
        credential_index = request_index + attempt - 1
        lock = (
            credential_locks[credential_index % len(credential_locks)]
            if credential_locks
            else contextlib.nullcontext()
        )
        transport_retry_count_holder = [0]
        try:
            with lock:
                generated, transport_retry_count = generate_with_transport_retries(
                    lambda: candidate_generator.run_request(
                        request_pack_path,
                        pack,
                        current,
                        attempt_dir,
                        active_image_profile,
                        size_override=None,
                        timeout=generation_timeout,
                        live=True,
                        credential_index=credential_index,
                    ),
                    max_retries=max_transport_retries,
                    base_backoff=transport_backoff_base,
                    max_backoff=transport_backoff_cap,
                    retry_count=transport_retry_count_holder,
                )
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt_number,
                    "status": "generation_error",
                    "error": f"{type(exc).__name__}:external_call_failed",
                    "transport_retry_count": transport_retry_count_holder[0],
                }
            )
            if attempt < max_attempts:
                time.sleep(min(2.0 * attempt, 4.0))
            continue
        candidate_path = Path(str(generated["candidate_path"]))
        if not candidate_path.is_absolute():
            candidate_path = candidate_generator.ROOT / candidate_path
        review_retry_count_holder = [0]
        try:
            with lock:
                review, review_transport_retry_count = review_with_transport_retries(
                    lambda: review_candidate(
                        current,
                        candidate_path,
                        request_pack_path,
                        vision_profile,
                        timeout=review_timeout,
                        max_tokens=review_max_tokens,
                        credential_index=credential_index,
                        minimum_score=minimum_score,
                        secondary_style_profile=secondary_style_profile,
                    ),
                    max_retries=max_transport_retries,
                    base_backoff=transport_backoff_base,
                    max_backoff=transport_backoff_cap,
                    retry_count=review_retry_count_holder,
                )
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt_number,
                    "status": "vision_review_error",
                    "candidate_path": str(candidate_path.resolve()),
                    "candidate_sha256": sha256_file(candidate_path),
                    "error": f"{type(exc).__name__}:external_call_failed",
                    "review_transport_retry_count": review_retry_count_holder[0],
                }
            )
            if attempt < max_attempts:
                time.sleep(min(2.0 * attempt, 4.0))
            continue
        attempts.append(
            {
                "attempt": attempt_number,
                "status": "reviewed",
                "candidate_path": str(candidate_path.resolve()),
                "candidate_sha256": sha256_file(candidate_path),
                "prompt_sha256": hashlib.sha256(str(current.get("prompt_brief") or "").encode("utf-8")).hexdigest(),
                "transport_retry_count": transport_retry_count,
                "review_transport_retry_count": review_transport_retry_count,
                "review": review,
            }
        )
        if review["status"] == "passed":
            accepted_path = candidate_path
            if candidate_cache is not None:
                source_prompt_sha = hashlib.sha256(
                    str(current.get("prompt_brief") or "").encode("utf-8")
                ).hexdigest()
                stored = candidate_cache.store(
                    request_fingerprint_value=request_fp,
                    review_policy_fingerprint_value=policy_fp,
                    candidate_path=candidate_path,
                    review=review,
                    base_prompt_sha256=base_prompt_sha,
                    source_prompt_sha256=source_prompt_sha,
                    provenance={
                        "node_id": pack.get("node_id"),
                        "worldbook_id": pack.get("worldbook_id"),
                        "request_id": request.get("request_id"),
                        "role": request.get("role"),
                        "image_profile": active_image_profile.name,
                        "reviewer_profile": vision_profile.name,
                        "review_policy_revision": review_policy_revision(
                            str(request.get("role") or ""), secondary_style_profile
                        ),
                    },
                )
                cache_status = {
                    "status": "stored",
                    "request_fingerprint": request_fp,
                    "review_policy_fingerprint": policy_fp,
                    **stored,
                }
            break
        current = repaired_request(current, review["failed_checks"])
    return {
        "request_id": request.get("request_id"),
        "role": request.get("role"),
        "status": "passed" if accepted_path else "failed_after_retries",
        "accepted_candidate_path": str(accepted_path.resolve()) if accepted_path else None,
        "accepted_image_profile": (
            active_image_profile.name if accepted_path else None
        ),
        "attempt_count": sum(1 for item in attempts if int(item.get("attempt") or 0) > 0),
        "attempts": attempts,
        "cache": cache_status,
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
    minimum_score: float = DEFAULT_MIN_VISION_SCORE,
    reviewed_fallback_dir: Path | None = None,
    cache_dir: Path | None = None,
    max_transport_retries: int = DEFAULT_MAX_TRANSPORT_RETRIES,
    transport_backoff_base: float = DEFAULT_TRANSPORT_BACKOFF_BASE,
    transport_backoff_cap: float = DEFAULT_TRANSPORT_BACKOFF_CAP,
    include_optional_roles: bool = False,
) -> dict[str, Any]:
    requests = candidate_generator.selected_requests(pack, [])
    provider_requests = [
        (index, request)
        for index, request in enumerate(requests)
        if str(request.get("role") or "") in SYNCHRONOUS_PROVIDER_ROLES
        or (
            include_optional_roles
            and str(request.get("role") or "") != "road_surface"
        )
    ]
    credential_count = max(
        1,
        sum(1 for env_key in image_profile.env_keys if os.environ.get(env_key)),
    )
    credential_locks = [threading.Lock() for _ in range(credential_count)]
    candidate_cache = (
        map_visual_candidate_cache.CandidateCache(cache_dir)
        if cache_dir is not None
        else None
    )
    existing_attempt_numbers = [
        int(path.name.removeprefix("attempt_"))
        for path in output_dir.glob("attempt_[0-9][0-9]")
        if path.is_dir() and path.name.removeprefix("attempt_").isdigit()
    ]
    run_attempt_offset = max(existing_attempt_numbers, default=0)
    results_by_index: dict[int, dict[str, Any]] = {
        index: {
            "request_id": request.get("request_id"),
            "role": "road_surface",
            "status": "skipped_provider_for_deterministic_derivation",
            "accepted_candidate_path": None,
            "accepted_image_profile": None,
            "attempt_count": 0,
            "attempts": [],
            "cache": {"status": "not_applicable"},
        }
        for index, request in enumerate(requests)
        if str(request.get("role") or "") == "road_surface"
    }
    for index, request in enumerate(requests):
        role = str(request.get("role") or "")
        if (
            role in SYNCHRONOUS_PROVIDER_ROLES
            or role == "road_surface"
            or include_optional_roles
        ):
            continue
        results_by_index[index] = {
            "request_id": request.get("request_id"),
            "role": role,
            "status": "deferred_optional_visual_role",
            "accepted_candidate_path": None,
            "accepted_image_profile": None,
            "attempt_count": 0,
            "attempts": [],
            "cache": {"status": "deferred"},
        }
    failures_by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(provider_requests) or 1))) as executor:
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
                minimum_score=minimum_score,
                credential_locks=credential_locks,
                candidate_cache=candidate_cache,
                max_transport_retries=max_transport_retries,
                transport_backoff_base=transport_backoff_base,
                transport_backoff_cap=transport_backoff_cap,
                attempt_offset=run_attempt_offset,
            ): (index, request)
            for index, request in provider_requests
        }
        for future in as_completed(futures):
            index, request = futures[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:  # pragma: no cover - live provider failure path.
                stage = exc.stage if isinstance(exc, MapVisualStageError) else "closed_loop"
                error_type = exc.cause_type if isinstance(exc, MapVisualStageError) else type(exc).__name__
                failures_by_index[index] = {
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                    "stage": stage,
                    "error": f"{error_type}:external_call_failed",
                }
    results = [results_by_index[index] for index in sorted(results_by_index)]
    failures = [failures_by_index[index] for index in sorted(failures_by_index)]
    passed = {str(item["role"]): item for item in results if item["status"] == "passed"}
    reviewed_fallbacks = []
    request_by_role = {
        str(item.get("role") or ""): item
        for item in requests
        if isinstance(item, dict)
    }
    if "terrain_base" in passed and "road_surface" not in passed:
        terrain_source = Path(str(passed["terrain_base"]["accepted_candidate_path"]))
        reviewed_fallbacks.append(
            derive_road_surface_from_terrain(
                terrain_source,
                reviewed_dir / "textures" / "road_tile.png",
                request_by_role.get("road_surface"),
            )
        )
    if reviewed_fallback_dir is not None and "terrain_base" in passed:
        fallback_roles = {str(item.get("role") or "") for item in reviewed_fallbacks}
        for role in sorted(REVIEWED_FALLBACK_ROLES - set(passed) - fallback_roles):
            fallback = reuse_reviewed_fallback(
                str(pack.get("node_id") or "map"),
                role,
                reviewed_fallback_dir,
                reviewed_dir,
            )
            if fallback:
                reviewed_fallbacks.append(fallback)
    available_roles = set(passed) | {
        str(item["role"]) for item in reviewed_fallbacks
    }
    critical_ready = CRITICAL_ROLES.issubset(available_roles)
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
        promotions.extend(reviewed_fallbacks)
        promoted_by_role = {
            str(item.get("role")): item
            for item in promotions
            if isinstance(item, dict)
        }
        if all(role in promoted_by_role for role in DECORATION_VARIANT_ROLES):
            atlas_path = reviewed_dir / "components" / "non_blocking_decoration.png"
            metrics = pack_decoration_components(
                [
                    Path(str(promoted_by_role[role]["reviewed_path"]))
                    for role in DECORATION_VARIANT_ROLES
                ],
                atlas_path,
            )
            promotions.append(
                {
                    "role": "non_blocking_decoration",
                    "source_roles": list(DECORATION_VARIANT_ROLES),
                    "reviewed_path": str(atlas_path.resolve()),
                    "consumed_by_current_runtime": True,
                    "status": "packed_from_reviewed_components",
                    **metrics,
                }
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
            "failed_count": len(failures)
            + sum(item.get("status") == "failed_after_retries" for item in results),
            "provider_failure_count": len(failures)
            + sum(
                1
                for item in results
                for attempt in item.get("attempts", [])
                if str(attempt.get("status") or "").endswith("_error")
            ),
            "attempt_count": sum(int(item.get("attempt_count") or 0) for item in results),
            "provider_call_count": sum(
                1 + int(attempt.get("transport_retry_count", 0))
                for item in results
                for attempt in item.get("attempts", [])
                if attempt.get("status") in {"generation_error", "reviewed", "vision_review_error"}
            ),
            "vision_review_call_count": sum(
                1 + int(attempt.get("review_transport_retry_count", 0))
                for item in results
                for attempt in item.get("attempts", [])
                if attempt.get("status")
                in {
                    "reviewed",
                    "vision_review_error",
                    "reused_candidate_reviewed",
                    "reused_candidate_review_error",
                }
            )
            + sum(
                1
                for item in results
                for attempt in item.get("attempts", [])
                if isinstance(attempt.get("review"), dict)
                and attempt["review"].get("secondary_style_review") is not None
            ),
            "promotion_count": len(promotions),
            "reviewed_fallback_count": len(reviewed_fallbacks),
            "cache_hit_count": sum(
                1 for item in results if item.get("cache", {}).get("status") == "hit"
            ),
            "cache_store_count": sum(
                1 for item in results if item.get("cache", {}).get("status") == "stored"
            ),
            "transport_retry_count": sum(
                int(attempt.get("transport_retry_count", 0))
                + int(attempt.get("review_transport_retry_count", 0))
                for item in results
                for attempt in item.get("attempts", [])
            ),
        },
        "results": results,
        "failures": failures,
        "promotions": promotions,
        "reviewed_fallbacks": reviewed_fallbacks,
        "reviewed_backdrop_source_dir": None,
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
            "minimum_vision_score": minimum_score,
            "reviewed_candidate_cache_enabled": candidate_cache is not None,
            "optional_visual_roles_attempted": include_optional_roles,
        },
    }
    report_path = output_dir / REPORT_VERSION.replace(".v0.1", ".v0.1.json")
    candidate_generator.write_json(report_path, report)
    report["report_path"] = str(report_path.resolve())
    return report


def build_calibration_summary(report: dict[str, Any]) -> dict[str, Any]:
    roles: list[dict[str, Any]] = []
    accepted_scores: list[float] = []
    for result in report.get("results", []):
        if not isinstance(result, dict):
            continue
        attempts = [item for item in result.get("attempts", []) if isinstance(item, dict)]
        final_review = attempts[-1].get("review", {}) if attempts else {}
        score = float(final_review.get("score") or 0)
        if result.get("status") == "passed":
            accepted_scores.append(score)
        roles.append(
            {
                "role": result.get("role"),
                "status": result.get("status"),
                "attempt_count": result.get("attempt_count"),
                "final_score": score,
                "final_failed_checks": final_review.get("failed_checks", []),
            }
        )
    threshold = float(report.get("policy", {}).get("minimum_vision_score") or DEFAULT_MIN_VISION_SCORE)
    return {
        "schema_version": "map_visual_calibration_summary.v0.1",
        "node_id": report.get("node_id"),
        "closed_loop_status": report.get("status"),
        "configured_minimum_score": threshold,
        "roles": roles,
        "accepted_score_range": {
            "minimum": min(accepted_scores) if accepted_scores else None,
            "maximum": max(accepted_scores) if accepted_scores else None,
        },
        "recommendation": (
            "retain_threshold_and_perform_human_visual_confirmation"
            if report.get("runtime_critical_roles_ready")
            else "keep_hard_check_vetoes_and_revise_prompts_before_threshold_changes"
        ),
        "policy": [
            "A failed fixed check always blocks promotion regardless of score.",
            "One calibration run must not automatically lower the minimum score.",
            "Human visual confirmation is required before changing the project default threshold.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reviewed-dir", required=True, type=Path)
    parser.add_argument("--dotenv", required=True, type=Path)
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--vision-profile", default="agnes_multimodal_flash", choices=sorted(vision_review.PROFILES))
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--generation-timeout", type=int, default=300)
    parser.add_argument("--review-timeout", type=int, default=240)
    parser.add_argument("--review-max-tokens", type=int, default=1200)
    parser.add_argument("--minimum-score", type=float, default=DEFAULT_MIN_VISION_SCORE)
    parser.add_argument("--cache-dir", type=Path, default=resolve_cache_dir())
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include-optional-roles", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("--live is required because this command calls external providers")
    if not 0 <= args.minimum_score <= 1:
        raise SystemExit("--minimum-score must be between 0 and 1")
    report_path = args.output_dir / REPORT_VERSION.replace(".v0.1", ".v0.1.json")
    if report_path.exists() and not args.resume:
        raise SystemExit(f"output already contains a closed-loop report: {report_path}")
    pack = candidate_generator.load_json(args.request_pack)
    if pack.get("schema_version") != candidate_generator.PACK_VERSION:
        raise SystemExit(f"request pack must be {candidate_generator.PACK_VERSION}")
    image_provider.load_dotenv(args.dotenv)
    vision_review.load_dotenv(args.dotenv)
    report = run_closed_loop(
        args.request_pack,
        pack,
        args.output_dir,
        args.reviewed_dir,
        image_provider.PROFILES[args.image_profile],
        vision_review.PROFILES[args.vision_profile],
        max_attempts=args.max_attempts,
        max_workers=args.max_workers,
        generation_timeout=args.generation_timeout,
        review_timeout=args.review_timeout,
        review_max_tokens=args.review_max_tokens,
        minimum_score=args.minimum_score,
        cache_dir=args.cache_dir,
        include_optional_roles=args.include_optional_roles,
    )
    calibration = build_calibration_summary(report)
    calibration_path = args.output_dir / "map_visual_calibration_summary.v0.1.json"
    candidate_generator.write_json(calibration_path, calibration)
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "report_path": report["report_path"],
                "calibration_path": str(calibration_path.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["runtime_critical_roles_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
