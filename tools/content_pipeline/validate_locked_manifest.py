#!/usr/bin/env python3
"""Validate a LockedManifest v0.1 file.

Uses jsonschema if available; otherwise falls back to a pure-Python check
that mirrors the same contract. Either way, an additional recursive scan
rejects forbidden fields (provider, model, raw_prompt, full_trace, raw_json,
api_key, secret, unreviewed_content) anywhere in the document, and media_refs
URLs are checked for forbidden http(s)/provider temporary links.

The validator never reads .env and never prints API keys or secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/locked_manifest.v0.1.schema.json"

FORBIDDEN_FIELDS = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)

VISUAL_RECIPE_KINDS = frozenset(
    {
        "ring_pulse",
        "beam",
        "chain_arc",
        "sprite_flash",
        "particle_burst",
        "aura_field",
        "screen_shake",
        "floating_text",
    }
)

LIFECYCLE_STATES = frozenset(
    {"ephemeral", "session_blueprint", "stabilized_blueprint"}
)
BATTLE_SURFACES = frozenset({"battle_hotbar", "node_supply"})
DELIVERY_STATES = frozenset(
    {"research_in_progress", "sample_ready", "sample_delivered", "battle_used"}
)
INTENSITY_LEVELS = frozenset({"low", "medium", "high"})
PARTICLE_DENSITY_LEVELS = frozenset({"low", "medium", "high"})
BLEND_MODES = frozenset({"normal", "additive", "multiply"})
ARC_STYLES = frozenset({"straight", "curved", "jagged"})

HEX6_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

# Media URL rules: must start with /assets/, must not contain http(s) schemes
# or common provider temporary-link markers.
FORBIDDEN_URL_MARKERS = ("http://", "https://", "://")
PROVIDER_DOMAIN_HINTS = (
    ".openai.com",
    ".anthropic.com",
    ".volces.com",
    ".tencentcloudapi.com",
    ".hunyuan.",
    ".ark.",
    ".deepseek.com",
    ".baidubce.com",
    ".aliyuncs.com",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    """Recursively walk the document and reject forbidden keys anywhere."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(
                    f"forbidden field '{child_path}' is not allowed in a "
                    f"locked manifest (must not carry provider/trace/raw "
                    f"payloads)"
                )
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_forbidden_fields(child, child_path, errors)


def check_media_url(url: Any, path: str, errors: list[str]) -> None:
    if not isinstance(url, str):
        errors.append(f"{path} must be a string URL")
        return
    if not url.startswith("/assets/"):
        errors.append(
            f"{path}={url!r} must start with '/assets/' (local cached asset only)"
        )
    lowered = url.lower()
    for marker in FORBIDDEN_URL_MARKERS:
        if marker in lowered:
            errors.append(
                f"{path}={url!r} must not contain '{marker}' (no provider URLs)"
            )
            break
    for hint in PROVIDER_DOMAIN_HINTS:
        if hint in lowered:
            errors.append(
                f"{path}={url!r} appears to reference a provider domain ({hint})"
            )
            break


def require_string(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a non-empty string")
        return ""
    return value


def require_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def reject_unknown_keys(
    obj: dict[str, Any], allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    """Mirror JSON Schema ``additionalProperties: false``.

    Any key not in ``allowed`` is reported with its concrete path so callers
    can locate the offending field even in deeply nested structures.
    """
    for key in obj.keys():
        if key not in allowed:
            loc = f"{path}.{key}" if path else key
            errors.append(
                f"unknown field '{loc}' is not allowed "
                f"(allowed: {sorted(allowed)})"
            )


# Allowed key sets mirror shared/schemas/locked_manifest.v0.1.schema.json.
# Keep these in sync with the schema's `additionalProperties: false` rules.
TOP_LEVEL_ALLOWED = frozenset(
    {
        "schema_version",
        "manifest_id",
        "session_id",
        "worldbook_id",
        "content_set",
        "created_at",
        "locked_assets",
    }
)
LOCKED_ASSET_ALLOWED = frozenset(
    {
        "stable_internal_id",
        "asset_kind",
        "template_id",
        "worldbook_id",
        "session_instance_id",
        "lifecycle_state",
        "display",
        "gameplay_ref",
        "media_refs",
        "visual_recipes",
        "battle_availability",
    }
)
DISPLAY_ALLOWED = frozenset({"name", "summary", "tags"})
GAMEPLAY_REF_ALLOWED = frozenset({"kind", "path", "sha256"})
MEDIA_REFS_ALLOWED = frozenset({"icon", "sprite"})
MEDIA_ICON_ALLOWED = frozenset({"url", "width", "height", "sha256"})
MEDIA_SPRITE_ALLOWED = frozenset({"texture_key", "atlas", "image"})
VISUAL_RECIPE_ALLOWED = frozenset(
    {
        "trigger",
        "kind",
        "palette_token",
        "color",
        "secondary_color",
        "intensity",
        "radius",
        "radius_from_effect",
        "max_links_from_effect",
        "particle_density",
        "blend_mode",
        "arc_style",
        "duration_ms",
    }
)
BATTLE_AVAILABILITY_ALLOWED = frozenset(
    {"surfaces", "uses_per_battle", "requires_delivery", "delivery_state"}
)


def require_enum(
    value: Any, allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    if value not in allowed:
        errors.append(
            f"{path}={value!r} must be one of {sorted(allowed)}"
        )


def check_pattern(value: Any, pattern: re.Pattern[str], path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not pattern.match(value):
        errors.append(f"{path}={value!r} does not match {pattern.pattern}")


def validate_pure_python(manifest: dict[str, Any]) -> list[str]:
    """Pure-Python validation mirroring the JSON Schema contract."""
    errors: list[str] = []

    # Reject unknown top-level keys (mirrors additionalProperties: false).
    reject_unknown_keys(manifest, TOP_LEVEL_ALLOWED, "", errors)

    top_required = [
        "schema_version",
        "manifest_id",
        "session_id",
        "worldbook_id",
        "content_set",
        "created_at",
        "locked_assets",
    ]
    for key in top_required:
        if key not in manifest:
            errors.append(f"missing top-level key: {key}")

    if manifest.get("schema_version") != "locked_manifest.v0.1":
        errors.append(
            f"schema_version must be 'locked_manifest.v0.1' "
            f"(got {manifest.get('schema_version')!r})"
        )

    for key in ("manifest_id", "session_id", "worldbook_id", "content_set"):
        require_string(manifest.get(key), key, errors)

    created_at = manifest.get("created_at")
    if not isinstance(created_at, str) or not DATETIME_RE.match(created_at):
        errors.append(
            f"created_at={created_at!r} must be an ISO-8601 datetime string"
        )

    locked_assets = manifest.get("locked_assets")
    if not isinstance(locked_assets, list):
        errors.append("locked_assets must be an array")
        locked_assets = []

    for index, asset in enumerate(locked_assets):
        validate_locked_asset_pure(asset, f"locked_assets[{index}]", errors)

    return errors


def validate_locked_asset_pure(
    asset: Any, path: str, errors: list[str]
) -> None:
    asset = require_object(asset, path, errors)
    if not asset:
        return

    # Reject unknown keys on the asset object itself.
    reject_unknown_keys(asset, LOCKED_ASSET_ALLOWED, path, errors)

    required_fields = [
        "stable_internal_id",
        "asset_kind",
        "template_id",
        "worldbook_id",
        "session_instance_id",
        "lifecycle_state",
        "display",
        "gameplay_ref",
        "media_refs",
        "visual_recipes",
        "battle_availability",
    ]
    for key in required_fields:
        if key not in asset:
            errors.append(f"missing key: {path}.{key}")

    for key in (
        "stable_internal_id",
        "asset_kind",
        "template_id",
        "worldbook_id",
        "session_instance_id",
    ):
        require_string(asset.get(key), f"{path}.{key}", errors)

    require_enum(asset.get("lifecycle_state"), LIFECYCLE_STATES, f"{path}.lifecycle_state", errors)

    display = require_object(asset.get("display"), f"{path}.display", errors)
    if display:
        reject_unknown_keys(display, DISPLAY_ALLOWED, f"{path}.display", errors)
        require_string(display.get("name"), f"{path}.display.name", errors)
        require_string(display.get("summary"), f"{path}.display.summary", errors)
        tags = display.get("tags")
        if not isinstance(tags, list) or not tags:
            errors.append(f"{path}.display.tags must be a non-empty array")
        elif not all(isinstance(t, str) and t for t in tags):
            errors.append(f"{path}.display.tags must contain non-empty strings")

    gameplay_ref = require_object(
        asset.get("gameplay_ref"), f"{path}.gameplay_ref", errors
    )
    if gameplay_ref:
        reject_unknown_keys(
            gameplay_ref, GAMEPLAY_REF_ALLOWED, f"{path}.gameplay_ref", errors
        )
        require_string(gameplay_ref.get("kind"), f"{path}.gameplay_ref.kind", errors)
        require_string(gameplay_ref.get("path"), f"{path}.gameplay_ref.path", errors)
        check_pattern(
            gameplay_ref.get("sha256"),
            SHA256_RE,
            f"{path}.gameplay_ref.sha256",
            errors,
        )

    media_refs = require_object(
        asset.get("media_refs"), f"{path}.media_refs", errors
    )
    if media_refs:
        reject_unknown_keys(
            media_refs, MEDIA_REFS_ALLOWED, f"{path}.media_refs", errors
        )
        icon = media_refs.get("icon")
        if icon is not None:
            icon = require_object(icon, f"{path}.media_refs.icon", errors)
            if icon:
                reject_unknown_keys(
                    icon, MEDIA_ICON_ALLOWED, f"{path}.media_refs.icon", errors
                )
                check_media_url(
                    icon.get("url"), f"{path}.media_refs.icon.url", errors
                )
                for dim_key in ("width", "height"):
                    dim_val = icon.get(dim_key)
                    if not isinstance(dim_val, int) or dim_val < 1 or isinstance(dim_val, bool):
                        errors.append(
                            f"{path}.media_refs.icon.{dim_key} must be a positive integer"
                        )
                check_pattern(
                    icon.get("sha256"),
                    SHA256_RE,
                    f"{path}.media_refs.icon.sha256",
                    errors,
                )
        sprite = media_refs.get("sprite")
        if sprite is not None:
            sprite = require_object(sprite, f"{path}.media_refs.sprite", errors)
            if sprite:
                reject_unknown_keys(
                    sprite, MEDIA_SPRITE_ALLOWED, f"{path}.media_refs.sprite", errors
                )
                require_string(
                    sprite.get("texture_key"),
                    f"{path}.media_refs.sprite.texture_key",
                    errors,
                )
                check_media_url(
                    sprite.get("atlas"), f"{path}.media_refs.sprite.atlas", errors
                )
                check_media_url(
                    sprite.get("image"), f"{path}.media_refs.sprite.image", errors
                )

    visual_recipes = asset.get("visual_recipes")
    if not isinstance(visual_recipes, list):
        errors.append(f"{path}.visual_recipes must be an array")
    else:
        for vr_index, vr in enumerate(visual_recipes):
            validate_visual_recipe_pure(
                vr, f"{path}.visual_recipes[{vr_index}]", errors
            )

    battle_availability = require_object(
        asset.get("battle_availability"),
        f"{path}.battle_availability",
        errors,
    )
    if battle_availability:
        reject_unknown_keys(
            battle_availability,
            BATTLE_AVAILABILITY_ALLOWED,
            f"{path}.battle_availability",
            errors,
        )
        surfaces = battle_availability.get("surfaces")
        if not isinstance(surfaces, list) or not surfaces:
            errors.append(
                f"{path}.battle_availability.surfaces must be a non-empty array"
            )
        else:
            for s_index, surface in enumerate(surfaces):
                require_enum(
                    surface,
                    BATTLE_SURFACES,
                    f"{path}.battle_availability.surfaces[{s_index}]",
                    errors,
                )
        uses_per_battle = battle_availability.get("uses_per_battle")
        if (
            not isinstance(uses_per_battle, int)
            or isinstance(uses_per_battle, bool)
            or uses_per_battle < 0
        ):
            errors.append(
                f"{path}.battle_availability.uses_per_battle must be a non-negative integer"
            )
        if not isinstance(battle_availability.get("requires_delivery"), bool):
            errors.append(
                f"{path}.battle_availability.requires_delivery must be a boolean"
            )
        require_enum(
            battle_availability.get("delivery_state"),
            DELIVERY_STATES,
            f"{path}.battle_availability.delivery_state",
            errors,
        )


def validate_visual_recipe_pure(
    vr: Any, path: str, errors: list[str]
) -> None:
    vr = require_object(vr, path, errors)
    if not vr:
        return

    reject_unknown_keys(vr, VISUAL_RECIPE_ALLOWED, path, errors)

    require_string(vr.get("trigger"), f"{path}.trigger", errors)
    require_enum(vr.get("kind"), VISUAL_RECIPE_KINDS, f"{path}.kind", errors)

    if "color" in vr:
        check_pattern(vr["color"], HEX6_RE, f"{path}.color", errors)
    if "secondary_color" in vr:
        check_pattern(
            vr["secondary_color"], HEX6_RE, f"{path}.secondary_color", errors
        )
    if "intensity" in vr:
        require_enum(vr["intensity"], INTENSITY_LEVELS, f"{path}.intensity", errors)
    if "particle_density" in vr:
        require_enum(
            vr["particle_density"],
            PARTICLE_DENSITY_LEVELS,
            f"{path}.particle_density",
            errors,
        )
    if "blend_mode" in vr:
        require_enum(vr["blend_mode"], BLEND_MODES, f"{path}.blend_mode", errors)
    if "arc_style" in vr:
        require_enum(vr["arc_style"], ARC_STYLES, f"{path}.arc_style", errors)
    if "duration_ms" in vr:
        duration = vr["duration_ms"]
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration < 0
            or duration > 10000
        ):
            errors.append(
                f"{path}.duration_ms must be an integer in [0, 10000]"
            )
    if "radius" in vr:
        radius = vr["radius"]
        if not isinstance(radius, (int, float)) or isinstance(radius, bool) or radius < 0:
            errors.append(f"{path}.radius must be a non-negative number")


def validate_with_jsonschema(
    manifest: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    """Validate using jsonschema if installed; return [] if not available.

    jsonschema 3.x only supports up to Draft7. The schema is written against
    2020-12 but uses only constructs (const, $defs, additionalProperties,
    pattern, enum) that Draft7 also understands, so we fall back to Draft7
    when Draft202012 is unavailable.
    """
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return []

    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator", None)
    if validator_cls is None:
        return []

    errors: list[str] = []
    validator = validator_cls(schema)
    for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in error.path) or "<root>"
        errors.append(f"schema violation at {location}: {error.message}")
    return errors


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []

    # Layer 1: jsonschema (if available). Falls through silently if not.
    if schema is not None:
        errors.extend(validate_with_jsonschema(manifest, schema))

    # Layer 2: pure-Python structural check (always runs as a backstop so the
    # validator remains useful even without jsonschema, and so custom rules
    # like datetime format and URL patterns are enforced consistently).
    errors.extend(validate_pure_python(manifest))

    # Layer 3: recursive forbidden-field scan (defense in depth — JSON Schema
    # additionalProperties:false covers direct children, but this guarantees
    # no forbidden key survives anywhere in nested structures).
    scan_forbidden_fields(manifest, "", errors)

    # Layer 4: media_refs URL policy (re-checked here regardless of schema,
    # because patternProperties-style checks can miss complex nesting).
    if isinstance(manifest.get("locked_assets"), list):
        for index, asset in enumerate(manifest["locked_assets"]):
            if isinstance(asset, dict) and isinstance(asset.get("media_refs"), dict):
                media = asset["media_refs"]
                if isinstance(media.get("icon"), dict):
                    check_media_url(
                        media["icon"].get("url"),
                        f"locked_assets[{index}].media_refs.icon.url",
                        errors,
                    )
                if isinstance(media.get("sprite"), dict):
                    check_media_url(
                        media["sprite"].get("atlas"),
                        f"locked_assets[{index}].media_refs.sprite.atlas",
                        errors,
                    )
                    check_media_url(
                        media["sprite"].get("image"),
                        f"locked_assets[{index}].media_refs.sprite.image",
                        errors,
                    )

    # Layer 5: visual_recipes kind whitelist (re-checked here as a backstop).
    if isinstance(manifest.get("locked_assets"), list):
        for a_index, asset in enumerate(manifest["locked_assets"]):
            if not isinstance(asset, dict):
                continue
            recipes = asset.get("visual_recipes")
            if not isinstance(recipes, list):
                continue
            for r_index, recipe in enumerate(recipes):
                if not isinstance(recipe, dict):
                    continue
                kind = recipe.get("kind")
                if kind not in VISUAL_RECIPE_KINDS:
                    errors.append(
                        f"locked_assets[{a_index}].visual_recipes[{r_index}].kind="
                        f"{kind!r} is not in the v0.1 whitelist "
                        f"{sorted(VISUAL_RECIPE_KINDS)}"
                    )

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique_errors: list[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            unique_errors.append(err)
    return unique_errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a LockedManifest v0.1 JSON file."
    )
    parser.add_argument(
        "manifest", help="Path to a locked manifest JSON file to validate."
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Path to the locked_manifest v0.1 JSON Schema (optional).",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    schema_path = Path(args.schema)

    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print(f"INVALID LockedManifest")
        print(f"- manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"INVALID LockedManifest")
        print(f"- manifest is not valid JSON: {exc}")
        return 1

    if not isinstance(manifest, dict):
        print("INVALID LockedManifest")
        print("- manifest root must be an object")
        return 1

    schema: dict[str, Any] | None = None
    if schema_path.exists():
        try:
            loaded = load_json(schema_path)
            if isinstance(loaded, dict):
                schema = loaded
        except (FileNotFoundError, json.JSONDecodeError):
            # Schema is optional; fall back to pure-Python only.
            pass

    errors = validate_manifest(manifest, schema)
    if errors:
        print("INVALID LockedManifest")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {manifest_path}")
    asset_count = len(manifest.get("locked_assets", []))
    print(f"- schema_version: {manifest.get('schema_version')}")
    print(f"- locked_assets: {asset_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
