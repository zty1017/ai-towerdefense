"""Media prompt and metadata helpers for CompiledAssetCandidate image generation.

Generates image prompts for multiple media roles based on a
CompiledAssetCandidate's presentation and gameplay fields.
Produces raw media item metadata compatible with the media processing pipeline.
"""

from __future__ import annotations

import hashlib
from typing import Any

MEDIA_ROLES = {
    "icon",
    "tower_sprite",
    "ui_card",
    "effect_preview",
    "battle_preview",
}


CUTOUT_GENERATION_RULES = (
    "single isolated subject only, solid pure white matte background, no scenery, "
    "no cast shadow, no ground shadow, no particles, no aura baked into the image, "
    "no text, no letters, no watermark, leave clean empty padding around the subject"
)


def asset_type(candidate: dict[str, Any]) -> str:
    gameplay = candidate.get("gameplay", {})
    if isinstance(gameplay, dict):
        return str(gameplay.get("asset_type", "unknown"))
    return "unknown"


def default_media_roles(candidate: dict[str, Any]) -> list[str]:
    """Return role defaults that match the asset type."""
    kind = asset_type(candidate)
    if kind == "tower_blueprint":
        return ["icon", "tower_sprite", "battle_preview"]
    if kind in {"support_item", "temporary_mod"}:
        return ["icon", "ui_card", "effect_preview"]
    if kind == "intel_asset":
        return ["icon", "ui_card", "effect_preview"]
    return ["icon", "ui_card"]


def stable_media_id(candidate: dict[str, Any], role: str) -> str:
    raw = f"{candidate.get('id', 'unknown')}_{role}"
    return f"{raw}_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def build_prompt_summary(candidate: dict[str, Any], role: str) -> str:
    """Build a short, non-reconstructive prompt summary for metadata."""
    presentation = candidate.get("presentation", {})
    gameplay = candidate.get("gameplay", {})
    effect_blocks = gameplay.get("effect_blocks", [])
    effect_types = [
        str(e.get("type"))
        for e in effect_blocks
        if isinstance(e, dict) and e.get("type")
    ]
    return "; ".join(
        part
        for part in (
            f"role={role}",
            f"name={presentation.get('name', candidate.get('id', 'unknown'))}",
            f"asset_type={gameplay.get('asset_type', 'unknown')}",
            f"effects={','.join(effect_types)}" if effect_types else "",
        )
        if part
    )


def build_icon_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for the icon role.

    UI icon: square, clear silhouette, no text.
    """
    presentation = candidate.get("presentation", {})
    name = presentation.get("name", "tower")
    desc = presentation.get("short_description", "")
    icon_prompt = presentation.get("icon_prompt", "")
    visual_tags = presentation.get("visual_tags", [])

    parts: list[str] = [
        "2D game icon, square, clean silhouette, centered object, game-ready UI asset",
        CUTOUT_GENERATION_RULES,
    ]
    if icon_prompt:
        parts.append(icon_prompt)
    else:
        parts.append(f"tower defense game asset, {name}")
    if desc:
        parts.append(desc)
    if visual_tags:
        parts.append(", ".join(str(t) for t in visual_tags))
    parts.append("flat-to-painterly game icon, readable at small size")
    return ", ".join(parts)


def build_tower_sprite_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for the tower_sprite role.

    2D/pseudo-3D single-frame tower sprite suitable for tower defense battlefield.
    No text.
    """
    presentation = candidate.get("presentation", {})
    gameplay = candidate.get("gameplay", {})
    name = presentation.get("name", "tower")
    desc = presentation.get("short_description", "")
    anim_prompt = presentation.get("animation_card_prompt", "")
    visual_tags = presentation.get("visual_tags", [])
    effect_blocks = gameplay.get("effect_blocks", [])

    parts: list[str] = [
        "2D tower defense tower sprite, isolated object, single frame, pseudo-isometric view",
        CUTOUT_GENERATION_RULES,
        "centered base, game-ready cutout, effects must be separate overlay recipes not painted on the tower body",
    ]
    if anim_prompt:
        parts.append(anim_prompt)
    else:
        parts.append(f"tower defense turret, {name}")
    if desc:
        parts.append(desc)
    if visual_tags:
        parts.append(", ".join(str(t) for t in visual_tags))
    effect_types = [e.get("type", "") for e in effect_blocks if isinstance(e, dict)]
    if effect_types:
        parts.append(f"effects: {', '.join(effect_types)}")
    parts.append("clean tower body sprite, anchor at bottom center")
    return ", ".join(parts)


def build_ui_card_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for a player-facing inventory/research card image."""
    presentation = candidate.get("presentation", {})
    gameplay = candidate.get("gameplay", {})
    name = presentation.get("name", "asset")
    desc = presentation.get("short_description", "")
    anim_prompt = presentation.get("animation_card_prompt", "")
    visual_tags = presentation.get("visual_tags", [])
    kind = gameplay.get("asset_type", "asset") if isinstance(gameplay, dict) else "asset"

    parts: list[str] = [
        "2D game card illustration only, no text, no letters, no numbers, no watermark",
        "no readable glyphs, no captions, no UI labels, no generated writing",
        "portrait card composition for a tower defense strategy game, empty decorative frame allowed",
        f"asset type: {kind}, {name}",
    ]
    if anim_prompt:
        parts.append(str(anim_prompt))
    if desc:
        parts.append(str(desc))
    if visual_tags:
        parts.append(", ".join(str(t) for t in visual_tags))
    parts.append("dark fantasy lantern-world style, clear subject, polished card art with blank label areas")
    return ", ".join(parts)


def build_effect_preview_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for the asset's gameplay effect preview."""
    presentation = candidate.get("presentation", {})
    gameplay = candidate.get("gameplay", {})
    name = presentation.get("name", "asset")
    desc = presentation.get("short_description", "")
    effect_blocks = gameplay.get("effect_blocks", []) if isinstance(gameplay, dict) else []
    effect_types = [e.get("type", "") for e in effect_blocks if isinstance(e, dict)]

    parts: list[str] = [
        "2D tower defense gameplay effect preview, no text, no letters, no watermark",
        "small diorama scene showing the asset effect clearly",
        "enemies should be non-human shadow tide creatures or abstract hostile silhouettes",
        f"subject: {name}",
    ]
    if desc:
        parts.append(str(desc))
    if effect_types:
        parts.append(f"gameplay effects: {', '.join(effect_types)}")
    parts.append("pseudo-isometric 2D, readable action, limited background, game-ready preview")
    return ", ".join(parts)


def build_battle_preview_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for battle preview / animation card media."""
    presentation = candidate.get("presentation", {})
    gameplay = candidate.get("gameplay", {})
    name = presentation.get("name", "asset")
    desc = presentation.get("short_description", "")
    anim_prompt = presentation.get("animation_card_prompt", "")
    effect_blocks = gameplay.get("effect_blocks", []) if isinstance(gameplay, dict) else []
    effect_types = [e.get("type", "") for e in effect_blocks if isinstance(e, dict)]

    parts: list[str] = [
        "2D pseudo-isometric tower defense battle preview, no text, no letters, no watermark",
        f"asset in action: {name}",
    ]
    if anim_prompt:
        parts.append(str(anim_prompt))
    if desc:
        parts.append(str(desc))
    if effect_types:
        parts.append(f"effects visible: {', '.join(effect_types)}")
    parts.append("dark path battlefield, lantern light, cinematic but readable")
    return ", ".join(parts)


def repair_suffix_for_role(repair_plan: dict[str, Any] | None, role: str) -> str:
    if not isinstance(repair_plan, dict):
        return ""
    suffixes = repair_plan.get("prompt_suffix_by_role")
    if not isinstance(suffixes, dict):
        return ""
    value = suffixes.get(role)
    return str(value).strip() if value else ""


def target_roles_from_repair_plan(repair_plan: dict[str, Any]) -> list[str]:
    roles = repair_plan.get("target_roles") if isinstance(repair_plan, dict) else None
    if not isinstance(roles, list):
        return []
    return [str(role) for role in roles if str(role) in MEDIA_ROLES]


def build_prompt_for_role(
    candidate: dict[str, Any],
    role: str,
    *,
    repair_plan: dict[str, Any] | None = None,
) -> str:
    """Build a provider prompt for a supported media role."""
    suffix = repair_suffix_for_role(repair_plan, role)
    if suffix and role == "effect_preview":
        return (
            "2D fantasy game effect preview, small mirror shard device on the ground, "
            "amber light rings, soft dark mist wisps, no text, no logo, "
            "painterly game art, pseudo-isometric view, limited background, game-ready preview"
        )
    if suffix and role == "ui_card":
        return (
            "2D game card illustration only, no text, no letters, no numbers, no watermark, "
            "one small mirror-shard lure device, blank decorative frame, dark lantern-world style, "
            "clear subject, no writing"
        )

    if role == "icon":
        prompt = build_icon_prompt(candidate)
    elif role == "tower_sprite":
        prompt = build_tower_sprite_prompt(candidate)
    elif role == "ui_card":
        prompt = build_ui_card_prompt(candidate)
    elif role == "effect_preview":
        prompt = build_effect_preview_prompt(candidate)
    elif role == "battle_preview":
        prompt = build_battle_preview_prompt(candidate)
    else:
        raise ValueError(f"unknown media role: {role!r}")
    if suffix:
        prompt = f"{prompt}, {suffix}"
    return prompt


def build_raw_media_item(
    candidate: dict[str, Any],
    role: str,
    *,
    provider_profile: str,
    model: str,
    width: int,
    height: int,
    local_path: str,
    prompt_summary: str,
) -> dict[str, Any]:
    """Build a raw media item metadata dict for the given role.

    Fields follow the raw_media_sequence.v0.1 format.
    No provider temporary URL is written to metadata.
    """
    stable_internal_id = stable_media_id(candidate, role)
    return {
        "stable_internal_id": stable_internal_id,
        "media_layer": "raw_media",
        "source_layer": "raw_media",
        "source_kind": "generated_image",
        "media_role": role,
        "local_path": local_path,
        "width": width,
        "height": height,
        "fallback_used": False,
        "provider_profile": provider_profile,
        "model": model,
        "prompt_summary": prompt_summary,
    }


def build_raw_media_sequence(
    candidate: dict[str, Any],
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a raw_media_sequence.v0.1 document from a list of raw media items.

    Compatible with the mvp_media_processing_publish pipeline chain.
    """
    return {
        "metadata_version": "raw_media_sequence.v0.1",
        "media_layer": "raw_media",
        "items": items,
    }
