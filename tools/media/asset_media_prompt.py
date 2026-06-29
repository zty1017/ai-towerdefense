"""Media prompt and metadata helpers for CompiledAssetCandidate image generation.

Generates image prompts for icon and tower_sprite roles based on a
CompiledAssetCandidate's presentation and gameplay fields.
Produces raw media item metadata compatible with the media processing pipeline.
"""

from __future__ import annotations

import hashlib
from typing import Any


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
        "2D game icon, square, clean silhouette, no text, no letters",
    ]
    if icon_prompt:
        parts.append(icon_prompt)
    else:
        parts.append(f"tower defense turret, {name}")
    if desc:
        parts.append(desc)
    if visual_tags:
        parts.append(", ".join(str(t) for t in visual_tags))
    parts.append("game asset icon, flat design, clear background")
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
        "2D tower defense sprite, single frame, pseudo-isometric view, no text, no letters",
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
    parts.append("game asset sprite, battlefield ready")
    return ", ".join(parts)


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
