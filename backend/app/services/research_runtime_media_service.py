"""Optional live visual compilation for player-created battle objects.

Generated provider media is never trusted directly. A candidate must pass a
small deterministic image gate and a multimodal review before it is processed,
published locally, and referenced by a runtime package. Any failure returns a
compact fallback result so gameplay can continue with reviewed media.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MEDIA_TOOLS = _REPO_ROOT / "tools" / "media"
if str(_MEDIA_TOOLS) not in sys.path:
    sys.path.insert(0, str(_MEDIA_TOOLS))

import image_provider  # type: ignore  # noqa: E402
import png_pipeline  # type: ignore  # noqa: E402
import vision_review  # type: ignore  # noqa: E402


_DEFAULT_IMAGE_PROFILE = "agnes_image_flash"
_DEFAULT_VISION_PROFILE = "agnes_multimodal_flash"
_URL_PREFIX = "/assets/generated_runtime"
_REQUIRED_CHECKS = (
    "single_isolated_object",
    "no_people_or_creatures",
    "no_text_or_watermark",
    "no_baked_combat_effects",
    "complete_silhouette",
    "correct_game_camera",
    "asset_kind_match",
    "world_style_fit",
)

# Bounded, check-specific correction directives used by the second repair pass.
# Each directive is short and dedicated to one failed check rather than a fixed
# block of text, so the repair actually targets what the vision review flagged.
_REPAIR_DIRECTIVES = {
    "single_isolated_object": "只保留正中央一个完整对象，移除其他任何物体、场景与背景",
    "no_people_or_creatures": "擦除所有人物、人形、生物剪影与角色",
    "no_text_or_watermark": "擦除所有文字、数字、书法、印章、水印与符号",
    "no_baked_combat_effects": "擦除闪电、电弧、光环、法阵、射线、弹道、爆炸、火花、烟雾与粒子",
    "complete_silhouette": "补全被裁切的主体外轮廓，使对象完整入镜",
    "correct_game_camera": "恢复三分之二俯视等距游戏视角",
    "asset_kind_match": "将主体修正为无人可进入的紧凑机械防御装置，底座明确",
    "world_style_fit": "服从世界书材质语言，移除其他文明的标志性结构",
}


def _build_repair_directives(
    failed_checks: list[str] | None, notes: list[str] | None
) -> str:
    """Build a bounded, dedicated correction clause from review failures.

    Selects check-specific directives and a small number of truncated review
    notes. Output is intentionally short and never echoes prompt or provider
    bodies.
    """
    directives = [
        _REPAIR_DIRECTIVES[check]
        for check in (failed_checks or [])
        if check in _REPAIR_DIRECTIVES
    ]
    clean_notes = [
        str(item).strip()[:120]
        for item in (notes or [])
        if isinstance(item, str) and item.strip()
    ][:4]
    parts: list[str] = []
    if directives:
        parts.append("针对性纠正：" + "；".join(directives))
    if clean_notes:
        parts.append("审查备注参考：" + "；".join(clean_notes))
    return "；".join(parts)


def published_root() -> Path:
    configured = os.environ.get("AI_TD_GENERATED_RUNTIME_MEDIA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return _REPO_ROOT / "backend" / "data" / "generated_runtime_media"


def _dotenv_path() -> Path:
    configured = os.environ.get("AI_TD_ENV_FILE")
    if configured:
        return Path(configured).expanduser()
    local = _REPO_ROOT / ".env"
    if local.is_file():
        return local
    git_pointer = _REPO_ROOT / ".git"
    if git_pointer.is_file():
        try:
            marker = git_pointer.read_text(encoding="utf-8").strip()
            if marker.startswith("gitdir:"):
                git_dir = Path(marker.partition(":")[2].strip()).resolve()
                for parent in git_dir.parents:
                    candidate = parent / ".env"
                    if (parent / ".git").exists() and candidate.is_file():
                        return candidate
        except OSError:
            pass
    return local


def _mode() -> str:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return "off"
    value = os.environ.get("AI_TD_LIVE_MEDIA", "auto").strip().lower()
    return value if value in {"auto", "live", "off"} else "auto"


def _safe_id(value: Any, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "")).strip("_")
    return normalized[:80] or fallback


def _physical_style_hint(presentation: dict[str, Any]) -> str:
    """Keep physical art direction while dropping effect-bearing prompt clauses."""
    source = str(presentation.get("icon_prompt") or "")[:600]
    blocked = (
        "lightning", "electric", "arc", "beam", "explosion", "projectile",
        "attack", "enemy", "aura", "glow", "light", "magic circle", "particle",
        "闪电", "电弧", "射线", "爆炸", "弹道", "攻击", "敌人", "光环", "法阵", "粒子",
    )
    clauses = re.split(r"[,;，；]", source)
    kept = [
        clause.strip()
        for clause in clauses
        if clause.strip() and not any(token in clause.lower() for token in blocked)
    ]
    return ", ".join(kept[:5])[:280]


def _world_style(candidate: dict[str, Any]) -> str:
    provenance = candidate.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    worldbook_id = str(provenance.get("worldbook_id") or "long_night_lanterns")
    if worldbook_id == "long_night_lanterns":
        return (
            "中国古代边镇器械材质：深色木构、青灰砖石、青铜灯械、榫卯结构；"
            "仅允许小型防雨檐片，不得形成完整屋顶；禁止欧洲城堡、哥特尖塔、"
            "西式城垛、楼阁和现代科幻建筑"
        )
    return "服从候选对象的世界书材质与建筑语言，不混入其他文明的标志性结构"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{secrets.token_hex(6)}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def _prompt(
    candidate: dict[str, Any],
    asset_kind: str,
    attempt: int = 0,
    repair_feedback: dict[str, Any] | None = None,
) -> str:
    presentation = candidate.get("presentation")
    presentation = presentation if isinstance(presentation, dict) else {}
    visual_tags = presentation.get("visual_tags")
    tags = "、".join(
        str(item)[:24]
        for item in visual_tags[:6]
        if not any(
            token in str(item).lower()
            for token in (
                "damage", "slow", "aura", "beam", "chain", "blueprint",
                "compiled", "asset", "tower", "temporary", "爆", "电", "光环",
            )
        )
    ) if isinstance(visual_tags, list) else ""
    physical_style = _physical_style_hint(presentation)
    world_style = _world_style(candidate)
    kind_hint = {
        "tower_blueprint": (
            "一个无人可进入的紧凑机械防御装置，整体高度不超过底座宽度的两倍，"
            "适合放在单个塔位；它不是建筑，不得出现门、窗、房间、台阶、城墙、"
            "楼阁、宫殿、完整屋顶或可供人物活动的平台"
        ),
        "temporary_trap_sample": "一个低矮的地面陷阱或临时机关，轮廓清楚",
        "field_device": "一个可部署的战场机关，底座稳定，轮廓清楚",
        "support_item": "一个可识别的战场支援道具，主体完整",
    }.get(asset_kind, "一个完整、可部署的塔防游戏对象")
    if attempt > 0:
        repair_directives = _build_repair_directives(
            list(repair_feedback.get("failed_checks") or [])
            if isinstance(repair_feedback, dict)
            else [],
            list(repair_feedback.get("notes") or [])
            if isinstance(repair_feedback, dict)
            else [],
        )
        return (
            "编辑参考图，制作干净的游戏对象抠图源。只保留参考图正中央的主装置或主道具，"
            "保持它的基本造型、视角和材质。彻底擦除主体周围以及主体表面的闪电、电弧、光圈、法阵、"
            "射线、弹道、爆炸、火花、烟雾、碎石、漂浮物、阴影和地面，把擦除区域恢复为均匀纯白。"
            "对象必须静止、完整、未激活、未受攻击、未损坏。画面中只有一个对象，不要文字、人物、敌人或UI。"
            f"世界风格硬约束：{world_style}。如果参考图含有西式塔顶、城垛或大型屋顶，必须完整移除。"
            "最终主体必须是无人可进入的紧凑机械装置，不是楼阁或建筑；彻底移除门、窗、房间、"
            "台阶、城墙、完整屋顶、人物活动平台和大面积场景底座。"
            f"{repair_directives}。"
            "纯白背景必须延伸到四角，对象外轮廓清晰且与白底完全分离。"
        )
    return (
        "制作游戏美术资源库中的单体对象抠图源，不是战斗插画，不讲故事，不表现任何动作。"
        f"对象要求：{kind_hint}。世界风格硬约束：{world_style}。"
        f"附加视觉关键词：{tags or '青铜灯械、榫卯结构、灰石底座'}。"
        f"物理造型参考：{physical_style or 'compact tower-defense structure, readable silhouette, bronze and dark wood materials'}。"
        "只设计对象本体的物理结构，画成静止、断能、未激活的工坊陈列状态；不要根据对象名称猜测功能。"
        "画面中只能有一个居中的完整对象，三分之二俯视等距游戏视角，完整轮廓和底座全部入镜，"
        "纯白无纹理背景，背景必须一直延伸到四角。高质量游戏贴图，清晰边缘，材质细节适中。"
        "严禁人物、怪物、动物、文字、数字、书法、印章、水印、UI、边框、场景、地面、建筑群；"
        "严禁门、窗、房间、台阶、城墙、楼阁、宫殿、完整屋顶、桥梁、浮岛和可供人物活动的平台；"
        "严禁光环、法阵、闪电、电弧、射线、弹道、爆炸、火花、烟雾、粒子、漂浮碎片和任何已经烙在对象周围的战斗特效。"
    )


def _corner_gate(image: Any) -> dict[str, Any]:
    radius = max(2, min(image.width, image.height) // 64)
    samples: list[tuple[int, int, int]] = []
    for y0 in (0, image.height - radius):
        for x0 in (0, image.width - radius):
            for y in range(y0, y0 + radius):
                for x in range(x0, x0 + radius):
                    pos = (y * image.width + x) * 4
                    samples.append(tuple(image.pixels[pos : pos + 3]))
    light = 0
    for r, g, b in samples:
        luma = (r * 299 + g * 587 + b * 114) // 1000
        if luma >= 225 and max(r, g, b) - min(r, g, b) <= 32:
            light += 1
    ratio = light / max(1, len(samples))
    return {"passed": image.width >= 512 and image.height >= 512 and ratio >= 0.9, "white_corner_ratio": round(ratio, 4)}


def _vision_gate(
    *, path: Path, candidate: dict[str, Any], asset_kind: str,
    profile: Any, timeout: int, credential_index: int = 0,
) -> dict[str, Any]:
    context = {
        "candidate_id": candidate.get("id"),
        "asset_kind": asset_kind,
        "name": (candidate.get("presentation") or {}).get("name")
        if isinstance(candidate.get("presentation"), dict) else None,
        "expected_world_style": _world_style(candidate),
        "required_checks": list(_REQUIRED_CHECKS),
    }
    prompt = (
        "你是严格的塔防游戏单体素材审查器。检查图片是否适合自动抠图并直接作为运行时对象。"
        "只输出一个JSON对象，字段为 score(0到1), checks, notes。checks必须包含上下文列出的全部键，值只能为true或false。"
        "有任意人物、怪物、文字、水印、场景背景、地面、法阵、光环、弹道或残缺主体时，对应检查必须为false。"
        "world_style_fit 必须严格服从 expected_world_style；出现欧洲城堡垛口、哥特尖塔或现代科幻主体时必须为false。"
        f"上下文：{json.dumps(context, ensure_ascii=False)}"
    )
    raw = vision_review.call_vision_model(
        profile,
        prompt,
        [{"stable_internal_id": str(candidate.get("id") or "candidate"), "media_role": "runtime_object", "local_path": path}],
        max_tokens=int(os.environ.get("AI_TD_MEDIA_REVIEW_MAX_TOKENS", "900")),
        timeout=timeout,
        credential_index=credential_index,
    )
    parsed = vision_review.extract_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("vision review did not return JSON")
    checks = parsed.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    normalized_checks = {key: checks.get(key) is True for key in _REQUIRED_CHECKS}
    try:
        score = max(0.0, min(1.0, float(parsed.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    minimum = float(os.environ.get("AI_TD_MEDIA_MINIMUM_SCORE", "0.78"))
    return {
        "passed": score >= minimum and all(normalized_checks.values()),
        "score": score,
        "minimum_score": minimum,
        "checks": normalized_checks,
        "failed_checks": [
            key for key, passed in normalized_checks.items() if passed is not True
        ],
        "notes": [str(item)[:240] for item in parsed.get("notes", [])[:6]]
        if isinstance(parsed.get("notes"), list) else [],
    }


def _process(raw_path: Path, output_path: Path) -> dict[str, Any]:
    image = png_pipeline.read_png(raw_path)
    image = png_pipeline.remove_edge_matte_background(image, threshold=42)
    image = png_pipeline.remove_near_white_background_islands(image)
    image = png_pipeline.remove_small_alpha_components(image, min_pixels=96)
    image = png_pipeline.keep_largest_alpha_component(image)
    image = png_pipeline.crop_and_pad(image, padding=48)
    image = png_pipeline.normalize_canvas(image, square=True, min_size=512, align="bottom_center", bottom_padding=24)
    image = png_pipeline.clear_transparent_rgb(image)
    total = image.width * image.height
    opaque = sum(1 for pos in range(3, len(image.pixels), 4) if image.pixels[pos] > 8)
    coverage = opaque / max(1, total)
    if not (0.03 <= coverage <= 0.8 and opaque < total):
        raise ValueError("processed alpha coverage is outside the runtime-safe range")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(
        f".{output_path.stem}.{secrets.token_hex(6)}.tmp.png"
    )
    png_pipeline.write_png(temporary, image)
    temporary.replace(output_path)
    return {"width": image.width, "height": image.height, "opaque_coverage": round(coverage, 4)}


def _fallback(
    job_dir: Path,
    candidate_id: str,
    reason: str,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compact_diagnostic = None
    if isinstance(diagnostic, dict):
        compact_diagnostic = {
            "score": diagnostic.get("score"),
            "minimum_score": diagnostic.get("minimum_score"),
            "failed_checks": [
                str(key)[:80]
                for key, passed in (diagnostic.get("checks") or {}).items()
                if passed is not True
            ][:16],
            "notes": [str(item)[:160] for item in (diagnostic.get("notes") or [])[:6]],
        }
    evidence_path = _write_json(
        job_dir / "runtime_media" / "runtime_media_evidence.v0.1.json",
        {
            "schema_version": "runtime_media_evidence.v0.1",
            "candidate_id": candidate_id,
            "status": "fallback",
            "reason": reason,
            **({"visual_review": compact_diagnostic} if compact_diagnostic else {}),
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "stores_secret": False,
            "uses_temporary_url": False,
        },
    )
    return {"status": "fallback", "reason": reason, "media_refs": None, "evidence_path": str(evidence_path), "published_ref": None}


def compile_runtime_media(
    *, candidate: dict[str, Any], asset_kind: str, session_id: str,
    job_id: str, job_dir: Path,
) -> dict[str, Any]:
    """Compile one provider-backed candidate into reviewed local runtime media."""
    candidate_id = _safe_id(candidate.get("id"), "compiled_object")
    if _mode() == "off":
        return _fallback(job_dir, candidate_id, "disabled")
    try:
        image_provider.load_dotenv(_dotenv_path())
        vision_review.load_dotenv(_dotenv_path())
        image_profile_name = os.environ.get("AI_TD_RUNTIME_IMAGE_PROFILE", _DEFAULT_IMAGE_PROFILE)
        vision_profile_name = os.environ.get("AI_TD_RUNTIME_VISION_PROFILE", _DEFAULT_VISION_PROFILE)
        image_profile = image_provider.PROFILES.get(image_profile_name)
        vision_profile = vision_review.PROFILES.get(vision_profile_name)
        if image_profile is None or vision_profile is None:
            return _fallback(job_dir, candidate_id, "profile_unavailable")
        image_provider.get_api_key(image_profile)
        vision_review.get_api_key(vision_profile)

        work_dir = job_dir / "runtime_media"
        max_attempts = max(1, min(2, int(os.environ.get("AI_TD_MEDIA_MAX_ATTEMPTS", "2"))))
        last_reason = "visual_review_failed"
        previous_raw_path: Path | None = None
        last_review: dict[str, Any] | None = None
        for attempt in range(max_attempts):
            raw_path = work_dir / f"raw_candidate_attempt_{attempt + 1}.png"
            try:
                response = image_provider.generate_image(
                    image_profile,
                    _prompt(candidate, asset_kind, attempt, last_review),
                    size="1K",
                    ratio="1:1",
                    input_images=(
                        [image_provider.image_data_uri(previous_raw_path)]
                        if attempt > 0 and previous_raw_path is not None
                        else None
                    ),
                    response_format="url",
                    timeout=int(os.environ.get("AI_TD_MEDIA_GENERATION_TIMEOUT", "45")),
                    credential_index=attempt,
                )
                image_provider.download_image(
                    image_provider.extract_image_url(response),
                    raw_path,
                    timeout=int(os.environ.get("AI_TD_MEDIA_DOWNLOAD_TIMEOUT", "20")),
                )
                raw_image = png_pipeline.read_png(raw_path)
                previous_raw_path = raw_path
                deterministic = _corner_gate(raw_image)
                if not deterministic["passed"]:
                    last_reason = "white_background_gate_failed"
                    continue
                review = _vision_gate(
                    path=raw_path,
                    candidate=candidate,
                    asset_kind=asset_kind,
                    profile=vision_profile,
                    timeout=int(os.environ.get("AI_TD_MEDIA_REVIEW_TIMEOUT", "45")),
                    credential_index=attempt,
                )
                if not review["passed"]:
                    last_reason = "visual_review_failed"
                    last_review = review
                    continue
                break
            except TimeoutError:
                return _fallback(job_dir, candidate_id, "TimeoutError")
            except Exception as exc:
                last_reason = type(exc).__name__
                continue
        else:
            return _fallback(job_dir, candidate_id, last_reason, last_review)

        relative = Path(_safe_id(session_id, "session")) / _safe_id(job_id, "job") / f"{candidate_id}.png"
        published_path = published_root() / relative
        processed = _process(raw_path, published_path)
        digest = hashlib.sha256(published_path.read_bytes()).hexdigest()
        url = f"{_URL_PREFIX}/{relative.as_posix()}"
        atlas_relative = relative.with_suffix(".atlas.json")
        atlas_path = published_root() / atlas_relative
        atlas_payload = {
            "frames": {
                candidate_id: {
                    "frame": {"x": 0, "y": 0, "w": processed["width"], "h": processed["height"]},
                    "rotated": False,
                    "trimmed": False,
                    "spriteSourceSize": {"x": 0, "y": 0, "w": processed["width"], "h": processed["height"]},
                    "sourceSize": {"w": processed["width"], "h": processed["height"]},
                    "anchor": {"x": 0.5, "y": 1.0},
                }
            },
            "meta": {
                "image": relative.name,
                "format": "RGBA8888",
                "size": {"w": processed["width"], "h": processed["height"]},
                "scale": "1",
            },
        }
        _write_json(atlas_path, atlas_payload)
        atlas_digest = hashlib.sha256(atlas_path.read_bytes()).hexdigest()
        atlas_url = f"{_URL_PREFIX}/{atlas_relative.as_posix()}"
        media_refs = {
            "icon": {"url": url, "width": processed["width"], "height": processed["height"], "sha256": digest},
            "sprite": {"texture_key": f"runtime_{candidate_id}", "atlas": atlas_url, "image": url},
        }
        evidence_path = _write_json(
            work_dir / "runtime_media_evidence.v0.1.json",
            {
                "schema_version": "runtime_media_evidence.v0.1",
                "candidate_id": candidate_id,
                "asset_kind": asset_kind,
                "status": "passed",
                "image_profile": image_profile.name,
                "image_model": image_profile.model,
                "vision_profile": vision_profile.name,
                "vision_model": vision_profile.model,
                "deterministic_gate": deterministic,
                "vision_gate": review,
                "processed": processed,
                "published": {
                    "image": {"path": str(published_path), "url": url, "sha256": digest},
                    "atlas": {"path": str(atlas_path), "url": atlas_url, "sha256": atlas_digest},
                },
                "stores_prompt_body": False,
                "stores_provider_body": False,
                "stores_secret": False,
                "uses_temporary_url": False,
            },
        )
        return {
            "status": "passed",
            "reason": None,
            "media_refs": media_refs,
            "evidence_path": str(evidence_path),
            "published_ref": {"path": str(published_path), "kind": "runtime_sprite", "sha256": digest},
            "published_refs": [
                {"path": str(published_path), "kind": "runtime_sprite", "sha256": digest},
                {"path": str(atlas_path), "kind": "runtime_atlas", "sha256": atlas_digest},
            ],
        }
    except Exception as exc:  # Provider/media failures must not abort gameplay.
        return _fallback(job_dir, candidate_id, type(exc).__name__)
