"""Prompt helpers for developer-compiled frontend battle mock art."""

from __future__ import annotations

import hashlib
from typing import Any


MEDIA_ROLES = {
    "icon",
    "unit_sprite",
    "objective_sprite",
    "defense_sprite",
    "portrait",
}

CUTOUT_RULES = (
    "single isolated subject only, solid pure white matte background, no scenery, "
    "no battlefield, no text, no letters, no numbers, no Chinese characters, no watermark, "
    "no UI frame, no title plaque, no speech bubble, no extra characters, "
    "clean empty padding around the subject"
)

SPRITE_RULES = (
    "2D game production sprite, pseudo-isometric view, readable silhouette, "
    "centered subject, game-ready cutout source, no cast shadow, no ground tile, "
    "no baked attack effect, no projectile, no explosion, no smoke cloud"
)

PORTRAIT_RULES = (
    "2D dialogue bust sprite of a fictional game character, non-photorealistic concept art, "
    "upper body bust view, clean white matte background, no text, no logo, no frame, "
    "no UI border, no extra characters, not based on any real individual"
)


def stable_media_id(asset: dict[str, Any], role: str) -> str:
    raw = f"{asset.get('stable_internal_id', 'unknown')}_{role}"
    return f"{raw}_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def build_prompt(asset: dict[str, Any], role: str) -> str:
    asset_kind = str(asset.get("asset_kind", "runtime_art"))
    visual_prompt = str(asset.get("visual_prompt", "lantern wasteland game asset"))

    if role == "portrait":
        parts = [
            PORTRAIT_RULES,
            "long night lantern wasteland visual style, painterly but clean, warm brass and muted blue shadows",
            f"subject: {visual_prompt}",
        ]
    elif role == "icon":
        parts = [
            "2D game icon source image, one centered object or character, clear silhouette",
            CUTOUT_RULES,
            "readable at small size, no baked gameplay effects",
            f"asset kind: {asset_kind}",
            f"subject: {visual_prompt}",
        ]
    else:
        parts = [
            SPRITE_RULES,
            CUTOUT_RULES,
            "anchor will be assigned by the game, keep lower body or base fully visible",
            f"asset kind: {asset_kind}",
            f"subject: {visual_prompt}",
        ]

    parts.append("white background must remain blank and contain no writing")
    return ", ".join(parts)
