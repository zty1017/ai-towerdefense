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
    "no enemies, no monsters, no human characters, no text, no letters, no numbers, "
    "no Chinese characters, no watermark, leave clean empty padding around the subject"
)

CLEAN_ASSET_NEGATIVE_RULES = (
    "no battlefield, no environment, no UI frame, no card border, no title plaque, "
    "no captions, no symbols, no readable glyphs, no speech bubble, no extra objects, "
    "no beam, no explosion, no smoke, no sparks, no floating debris, "
    "no readable runes, no engraved letters, no compass letters, no map markings"
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
        return ["icon", "tower_sprite"]
    if kind in {"support_item", "temporary_mod"}:
        return ["icon", "ui_card"]
    if kind == "intel_asset":
        return ["icon", "ui_card"]
    return ["icon", "ui_card"]


def stable_media_id(candidate: dict[str, Any], role: str) -> str:
    raw = f"{candidate.get('id', 'unknown')}_{role}"
    return f"{raw}_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def safe_ascii_tags(candidate: dict[str, Any]) -> list[str]:
    """Return short ASCII-only style tags that are safe for image prompts."""
    presentation = candidate.get("presentation", {})
    tags = presentation.get("visual_tags", []) if isinstance(presentation, dict) else []
    safe: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if value and value.isascii():
            safe.append(value.replace("_", " "))
    return safe[:6]


def candidate_motifs(candidate: dict[str, Any]) -> list[str]:
    """Infer visual motifs from stable IDs without using player-facing prose."""
    raw = str(candidate.get("id", "")).lower()
    motifs: list[str] = []
    if "ash" in raw:
        motifs.append("ash chamber")
        motifs.append("vented brass resonator")
    if "burst" in raw:
        motifs.append("reinforced pressure core")
    if "slow" in raw or "light" in raw:
        motifs.append("plain blue white glass lens")
        motifs.append("closed adjustable shutters")
    if "barrier" in raw or "pylon" in raw:
        motifs.append("wick lattice pylon")
        motifs.append("insulated field rods")
    if "mirror" in raw or "lure" in raw:
        motifs.append("mirror shard housing")
        motifs.append("small decoy lantern")
    if "signal" in raw or "decoy" in raw:
        motifs.append("signal wick beacon")
        motifs.append("folded tripod base")
    if "survey" in raw or "intel" in raw:
        motifs.append("sealed brass survey meter")
        motifs.append("blank smooth dial plate")
    if "chain" in raw or "arc" in raw or "overload" in raw:
        motifs.append("coiled conductor module")
        motifs.append("insulated copper clamps")
    return motifs[:5]


def clean_subject_description(candidate: dict[str, Any]) -> str:
    """Describe the asset body only; frontend effects are rendered separately."""
    kind = asset_type(candidate)
    motifs = candidate_motifs(candidate)
    motif_text = ", ".join(motifs) if motifs else "brass, crystal, lantern-world machinery"
    if kind == "tower_blueprint":
        return (
            "subject: one dormant lantern-inspired tower defense device only, "
            "inactive mechanical body, pseudo-isometric body, sturdy base, clear bottom anchor, "
            f"visible motifs: {motif_text}"
        )
    if kind == "support_item":
        return (
            "subject: one small deployable trap or utility device only, "
            "portable game item, readable silhouette, "
            f"visible motifs: {motif_text}"
        )
    if kind == "temporary_mod":
        return (
            "subject: one compact tower upgrade module only, mechanical component, "
            "readable silhouette, "
            f"visible motifs: {motif_text}"
        )
    if kind == "intel_asset":
        return (
            "subject: one portable survey instrument only, sealed brass meter with blank glass lens, "
            "smooth blank plates, no compass face, no map sheet, no writing or map labels, "
            f"visible motifs: {motif_text}"
        )
    return (
        "subject: one isolated tower defense game item only, readable silhouette, "
        f"visible motifs: {motif_text}"
    )


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
    parts: list[str] = [
        "2D game asset source image for an icon, one centered object, clean silhouette",
        CUTOUT_GENERATION_RULES,
        CLEAN_ASSET_NEGATIVE_RULES,
        clean_subject_description(candidate),
        "dormant object before gameplay effects are applied, subtle attached ornament is allowed if it is not readable writing",
        "plain white background, no baked gameplay effects, no glow rings, no beams, no explosions",
        "clean production sprite reference, readable at small size, brass and weathered metal materials",
    ]
    tags = safe_ascii_tags(candidate)
    if tags:
        parts.append("style tags: " + ", ".join(tags))
    return ", ".join(parts)


def build_tower_sprite_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for the tower_sprite role.

    2D/pseudo-3D single-frame tower sprite suitable for tower defense battlefield.
    No text.
    """
    parts: list[str] = [
        "2D tower defense deployable sprite, isolated tower body only, single frame, pseudo-isometric view",
        CUTOUT_GENERATION_RULES,
        CLEAN_ASSET_NEGATIVE_RULES,
        clean_subject_description(candidate),
        "centered base, game-ready cutout, anchor at bottom center",
        "dormant tower before gameplay effects are applied, subtle attached ornament is allowed if it is not readable writing",
        "effects are separate frontend overlays, do not paint beams, shockwaves, rings, smoke, sparks, enemies, or paths",
        "plain white background, no floor tile, no terrain, no shadows",
    ]
    tags = safe_ascii_tags(candidate)
    if tags:
        parts.append("style tags: " + ", ".join(tags))
    return ", ".join(parts)


def build_ui_card_prompt(candidate: dict[str, Any]) -> str:
    """Build a prompt for a player-facing inventory/research card image."""
    parts: list[str] = [
        "2D game inventory item source image, one isolated object only, not a card UI",
        CUTOUT_GENERATION_RULES,
        CLEAN_ASSET_NEGATIVE_RULES,
        clean_subject_description(candidate),
        "frontend will draw all UI frames and labels separately",
        "dormant object before gameplay effects are applied, subtle attached ornament is allowed if it is not readable writing",
        "plain white background, no baked gameplay effects, no glow rings, no beams, no explosions",
        "clean production sprite reference, clear subject, polished item illustration, brass and weathered metal materials",
    ]
    tags = safe_ascii_tags(candidate)
    if tags:
        parts.append("style tags: " + ", ".join(tags))
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
            "2D game inventory item source image, one isolated small mirror-shard lure device only, "
            "solid pure white matte background, no text, no letters, no numbers, no watermark, "
            "no UI frame, no card border, no title plaque, no writing, no enemies, no scene"
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
