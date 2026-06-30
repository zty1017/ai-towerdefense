#!/usr/bin/env python3
"""Vision-model media review for generated game assets.

This module sends local generated images plus VisualIdentitySpec context to a
multimodal chat model and normalizes the result into
media_vision_review_report.v0.1. It is live-only by default and never stores
raw prompts, raw provider responses, or API keys in the output artifact.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import media_review


REPORT_VERSION = "media_vision_review_report.v0.1"


@dataclass(frozen=True)
class VisionProfile:
    name: str
    env_key: str
    base_url: str
    model: str
    path: str = "/chat/completions"
    supports_json_object: bool = True


PROFILES: dict[str, VisionProfile] = {
    "glm_5v_turbo": VisionProfile(
        name="glm_5v_turbo",
        env_key="GLM_API_KEY",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-5v-turbo",
    ),
    "glmfree_4_6v_flash": VisionProfile(
        name="glmfree_4_6v_flash",
        env_key="GLM_API_KEY_FREE",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4.6v-flash",
    ),
    "agnes_multimodal_flash": VisionProfile(
        name="agnes_multimodal_flash",
        env_key="AGNES_API_KEY",
        base_url="https://apihub.agnes-ai.com/v1",
        model="agnes-2.0-flash",
        supports_json_object=False,
    ),
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key(profile: VisionProfile) -> str:
    key = os.environ.get(profile.env_key)
    if not key:
        raise RuntimeError(
            f"Missing environment variable: {profile.env_key} "
            f"(required for profile {profile.name!r})"
        )
    return key


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def detect_mime(path: Path) -> str:
    header = path.read_bytes()[:16]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"RIFF") and b"WEBP" in header[:12]:
        return "image/webp"
    return "application/octet-stream"


def encode_image_data_url(path: Path, max_bytes: int = 8 * 1024 * 1024) -> str:
    image_bytes = path.read_bytes()
    if len(image_bytes) > max_bytes:
        raise RuntimeError(f"image too large for inline review: {path}")
    mime = detect_mime(path)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def extract_json(text: str) -> dict[str, Any] | None:
    match = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    decoder = json.JSONDecoder()
    for token in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[token.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def normalize_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "是", "有"}:
            return True
        if lowered in {"false", "no", "否", "无"}:
            return False
    return None


def normalize_status(value: Any) -> str:
    if value in {"passed", "needs_review", "failed"}:
        return str(value)
    return "needs_review"


def normalize_fit(value: Any) -> str:
    if value in {"passed", "needs_review", "failed", "unknown"}:
        return str(value)
    return "unknown"


def normalize_action(value: Any, status: str) -> str:
    if value in {"promote", "manual_review", "revise_prompt", "regenerate_media", "reject"}:
        return str(value)
    if status == "passed":
        return "promote"
    if status == "failed":
        return "regenerate_media"
    return "manual_review"


def summarize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    presentation = as_obj(candidate.get("presentation"))
    gameplay = as_obj(candidate.get("gameplay"))
    return {
        "candidate_id": candidate.get("id"),
        "asset_type": media_review.asset_type(candidate),
        "name": presentation.get("name"),
        "short_description": presentation.get("short_description"),
        "visual_tags": presentation.get("visual_tags", []),
        "effect_blocks": [
            effect.get("type")
            for effect in as_list(gameplay.get("effect_blocks"))
            if isinstance(effect, dict) and effect.get("type")
        ],
    }


def local_review_items(media_metadata: dict[str, Any], max_images: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in media_review.media_items(media_metadata):
        local_path = item.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            continue
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            continue
        items.append(
            {
                "stable_internal_id": str(item.get("stable_internal_id", "")),
                "media_role": str(item.get("media_role", "unknown")),
                "local_path": path,
                "width": item.get("width"),
                "height": item.get("height"),
            }
        )
        if len(items) >= max_images:
            break
    return items


def build_review_prompt(
    candidate: dict[str, Any],
    visual_identity: dict[str, Any],
    review_items: list[dict[str, Any]],
    quality_report: dict[str, Any] | None,
    consistency_report: dict[str, Any] | None,
) -> str:
    role_labels = [
        {
            "index": idx + 1,
            "stable_internal_id": item["stable_internal_id"],
            "media_role": item["media_role"],
            "width": item.get("width"),
            "height": item.get("height"),
        }
        for idx, item in enumerate(review_items)
    ]
    context = {
        "candidate": summarize_candidate(candidate),
        "visual_identity": {
            "subject_name": visual_identity.get("subject_name"),
            "asset_type": visual_identity.get("asset_type"),
            "silhouette": visual_identity.get("silhouette"),
            "identity_tokens": visual_identity.get("identity_tokens", []),
            "palette": visual_identity.get("palette", []),
            "required_motifs": visual_identity.get("required_motifs", []),
            "forbidden_elements": visual_identity.get("forbidden_elements", []),
            "role_directives": visual_identity.get("role_directives", {}),
        },
        "role_labels": role_labels,
        "deterministic_quality_status": quality_report.get("status") if isinstance(quality_report, dict) else None,
        "deterministic_consistency_status": consistency_report.get("status") if isinstance(consistency_report, dict) else None,
    }
    return (
        "你是 2D/伪3D 塔防游戏素材的视觉审查器。请查看随后给出的图片，"
        "判断它们是否能作为同一个游戏资产的不同媒体角色。\n"
        "重点检查：是否有可读文字/伪文字/数字，是否有水印或模型标识，"
        "是否像同一个主体，是否符合长夜灯火式的黑暗灯火世界观，"
        "effect_preview/battle_preview 中敌人是否更像影潮或抽象敌意轮廓，而不是现代人类士兵，"
        "以及每张图是否符合 media_role。\n"
        "只输出一个 JSON 对象，不要 Markdown，不要解释正文。字段必须为：\n"
        "report_version, candidate_id, asset_type, status, vision_score, reviewer_profile, "
        "checked_roles, item_reviews, global_issues, global_warnings, recommended_action, notes。\n"
        "item_reviews 每项字段必须为 stable_internal_id, media_role, status, text_detected, "
        "watermark_detected, same_subject, world_fit, role_fit, issues, warnings, notes。\n"
        "status 只能是 passed / needs_review / failed；recommended_action 只能是 "
        "promote / manual_review / revise_prompt / regenerate_media / reject。\n"
        "如果看不清或不能确定，请使用 needs_review，不要假装确定。\n"
        "上下文如下：\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def call_vision_model(
    profile: VisionProfile,
    prompt: str,
    review_items: list[dict[str, Any]],
    *,
    max_tokens: int,
    timeout: int,
) -> str:
    api_key = get_api_key(profile)
    url = profile.base_url.rstrip("/") + profile.path
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for idx, item in enumerate(review_items, start=1):
        label = (
            f"图片 {idx}: stable_internal_id={item['stable_internal_id']}; "
            f"media_role={item['media_role']}"
        )
        content.append({"type": "text", "text": label})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": encode_image_data_url(item["local_path"]),
                },
            }
        )

    payload: dict[str, Any] = {
        "model": profile.model,
        "messages": [
            {
                "role": "system",
                "content": "你是严格的游戏素材视觉审查器。只返回合法 JSON。",
            },
            {"role": "user", "content": content},
        ],
        "stream": False,
        "max_tokens": max_tokens,
    }
    if profile.supports_json_object:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    if not body:
        raise RuntimeError("empty response from vision provider")
    raw = json.loads(body)
    choices = raw.get("choices", [])
    if not choices:
        raise RuntimeError("no choices in vision provider response")
    message = choices[0].get("message", {})
    content_out = message.get("content", "")
    if isinstance(content_out, str):
        return content_out
    if isinstance(content_out, list):
        text_parts = [
            str(part.get("text"))
            for part in content_out
            if isinstance(part, dict) and part.get("text")
        ]
        return "\n".join(text_parts)
    raise RuntimeError(f"unexpected vision response content type: {type(content_out).__name__}")


def empty_report(
    candidate: dict[str, Any],
    reviewer_profile: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "candidate_id": str(candidate.get("id", "unknown_candidate")),
        "asset_type": media_review.asset_type(candidate),
        "status": "failed",
        "vision_score": 0.0,
        "reviewer_profile": reviewer_profile,
        "checked_roles": [],
        "item_reviews": [],
        "global_issues": [reason],
        "global_warnings": [],
        "recommended_action": "regenerate_media",
        "notes": ["No local reviewable image files were available."],
    }


def normalize_report(
    raw_report: dict[str, Any],
    *,
    candidate: dict[str, Any],
    profile_name: str,
    review_items: list[dict[str, Any]],
) -> dict[str, Any]:
    item_by_id = {item["stable_internal_id"]: item for item in review_items}
    normalized_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_item in as_list(raw_report.get("item_reviews")):
        if not isinstance(raw_item, dict):
            continue
        stable_id = str(raw_item.get("stable_internal_id", ""))
        media_role = str(raw_item.get("media_role") or item_by_id.get(stable_id, {}).get("media_role", "unknown"))
        status = normalize_status(raw_item.get("status"))
        normalized = {
            "stable_internal_id": stable_id,
            "media_role": media_role,
            "status": status,
            "text_detected": normalize_bool_or_none(raw_item.get("text_detected")),
            "watermark_detected": normalize_bool_or_none(raw_item.get("watermark_detected")),
            "same_subject": normalize_bool_or_none(raw_item.get("same_subject")),
            "world_fit": normalize_fit(raw_item.get("world_fit")),
            "role_fit": normalize_fit(raw_item.get("role_fit")),
            "issues": [str(v) for v in as_list(raw_item.get("issues"))],
            "warnings": [str(v) for v in as_list(raw_item.get("warnings"))],
            "notes": [str(v) for v in as_list(raw_item.get("notes"))],
        }
        normalized_items.append(normalized)
        if stable_id:
            seen_ids.add(stable_id)

    for item in review_items:
        stable_id = item["stable_internal_id"]
        if stable_id in seen_ids:
            continue
        normalized_items.append(
            {
                "stable_internal_id": stable_id,
                "media_role": item["media_role"],
                "status": "needs_review",
                "text_detected": None,
                "watermark_detected": None,
                "same_subject": None,
                "world_fit": "unknown",
                "role_fit": "unknown",
                "issues": [],
                "warnings": ["vision_model_did_not_return_item_review"],
                "notes": [],
            }
        )

    statuses = [item["status"] for item in normalized_items]
    status = normalize_status(raw_report.get("status"))
    if "failed" in statuses:
        status = "failed"
    elif "needs_review" in statuses and status == "passed":
        status = "needs_review"

    try:
        score = float(raw_report.get("vision_score"))
    except (TypeError, ValueError):
        score = 80.0 if status == "passed" else 55.0 if status == "needs_review" else 20.0
    score = max(0.0, min(100.0, score))

    return {
        "report_version": REPORT_VERSION,
        "candidate_id": str(raw_report.get("candidate_id") or candidate.get("id", "unknown_candidate")),
        "asset_type": str(raw_report.get("asset_type") or media_review.asset_type(candidate)),
        "status": status,
        "vision_score": round(score, 1),
        "reviewer_profile": profile_name,
        "checked_roles": [str(item["media_role"]) for item in review_items],
        "item_reviews": normalized_items,
        "global_issues": [str(v) for v in as_list(raw_report.get("global_issues"))],
        "global_warnings": [str(v) for v in as_list(raw_report.get("global_warnings"))],
        "recommended_action": normalize_action(raw_report.get("recommended_action"), status),
        "notes": [str(v) for v in as_list(raw_report.get("notes"))],
    }


def review_media_with_vision(
    candidate: dict[str, Any],
    media_metadata: dict[str, Any],
    visual_identity: dict[str, Any],
    *,
    quality_report: dict[str, Any] | None = None,
    consistency_report: dict[str, Any] | None = None,
    profile_name: str = "glm_5v_turbo",
    max_images: int = 4,
    max_tokens: int = 4096,
    timeout: int = 180,
) -> dict[str, Any]:
    profile = PROFILES.get(profile_name)
    if profile is None:
        raise RuntimeError(f"unknown vision profile {profile_name!r}; known: {sorted(PROFILES)}")
    items = local_review_items(media_metadata, max_images=max_images)
    if not items:
        return empty_report(candidate, profile_name, "no_local_reviewable_images")

    prompt = build_review_prompt(
        candidate,
        visual_identity,
        items,
        quality_report=quality_report,
        consistency_report=consistency_report,
    )
    content = call_vision_model(
        profile,
        prompt,
        items,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    parsed = extract_json(content)
    if parsed is None:
        raise RuntimeError("failed to extract JSON from vision provider response")
    return normalize_report(
        parsed,
        candidate=candidate,
        profile_name=profile_name,
        review_items=items,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--media-metadata", required=True)
    parser.add_argument("--visual-identity", required=True)
    parser.add_argument("--quality-report")
    parser.add_argument("--consistency-report")
    parser.add_argument("--profile", default="glm_5v_turbo", choices=sorted(PROFILES))
    parser.add_argument("--max-images", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--dotenv", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    if not args.live:
        print("Refusing to call a vision provider without --live.")
        return 2
    if args.dotenv:
        load_dotenv(Path(args.dotenv))

    candidate = load_json(Path(args.candidate))
    media_metadata = load_json(Path(args.media_metadata))
    visual_identity = load_json(Path(args.visual_identity))
    quality_report = load_json(Path(args.quality_report)) if args.quality_report else None
    consistency_report = load_json(Path(args.consistency_report)) if args.consistency_report else None

    report = review_media_with_vision(
        candidate,
        media_metadata,
        visual_identity,
        quality_report=quality_report if isinstance(quality_report, dict) else None,
        consistency_report=consistency_report if isinstance(consistency_report, dict) else None,
        profile_name=args.profile,
        max_images=args.max_images,
        max_tokens=args.max_tokens,
        timeout=args.request_timeout,
    )

    if args.output:
        write_json(Path(args.output), report)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
