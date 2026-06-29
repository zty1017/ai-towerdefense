"""Shared pure-Python validation and builder logic for RuntimePackage v0.1.

Both the validator CLI (``validate_runtime_package.py``) and the builder CLI
(``build_runtime_package.py``) import this module so that the safety rules are
enforced in one place. The AssetGraph node ``runtime.build_package_stub`` also
imports the builder so the workflow path and the CLI path produce identical,
runtime-safe packages.

Safety rules enforced here (mirrored in the JSON Schema and re-checked in pure
Python as defense in depth):

1. ``additionalProperties: false`` at every object layer (reject_unknown_keys).
2. Recursive forbidden field name scan: provider, model, raw_prompt,
   full_trace, raw_json, api_key, secret, unreviewed_content.
3. Recursive forbidden URL string scan: any string containing ``http://``,
   ``https://``, or ``://`` is rejected.
4. Recursive forbidden media-layer value scan: ``raw_media`` and
   ``processed_media`` are not allowed anywhere in a runtime package.
5. Recursive forbidden ``source_layer`` field scan.
6. ``media_refs`` URLs must start with ``/assets/`` (local cached published
   assets only).
7. ``visual_recipes.kind`` must be in the 8-value v0.1 whitelist.

This module never reads ``.env`` and never prints API keys or secrets.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Constants — kept in sync with shared/schemas/runtime_package.v0.1.schema.json
# ---------------------------------------------------------------------------

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

# Any string value containing these substrings is rejected anywhere in the
# package. Runtime packages must reference only local /assets/ paths.
FORBIDDEN_URL_MARKERS = ("http://", "https://", "://")

# Media-layer values that must never appear in a runtime_public artifact.
# Only published_media may be runtime_public; raw_media and processed_media
# are internal-only.
FORBIDDEN_MEDIA_LAYER_VALUES = frozenset({"raw_media", "processed_media"})

# source_layer is a raw->published provenance field that must stay in the
# execution trace / internal logs and never leak to the runtime side.
FORBIDDEN_SOURCE_LAYER_FIELD = "source_layer"

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

# Allowed key sets mirror shared/schemas/runtime_package.v0.1.schema.json.
# Keep these in sync with the schema's `additionalProperties: false` rules.
TOP_LEVEL_ALLOWED = frozenset(
    {
        "schema_version",
        "package_id",
        "session_id",
        "worldbook_id",
        "node_id",
        "battle_display_name",
        "created_at",
        "source_refs",
        "assets",
        "battle_context",
    }
)
SOURCE_REFS_ALLOWED = frozenset({"locked_manifest_id", "battle_config_version"})
RUNTIME_ASSET_ALLOWED = frozenset(
    {
        "stable_internal_id",
        "asset_kind",
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
        "text",
    }
)
BATTLE_AVAILABILITY_ALLOWED = frozenset(
    {"surfaces", "uses_per_battle", "requires_delivery", "delivery_state"}
)
BATTLE_CONTEXT_ALLOWED = frozenset(
    {"grid", "paths", "core_target", "optional_targets", "sample_delivery"}
)
GRID_ALLOWED = frozenset(
    {"projection", "width_cells", "height_cells", "cell_size"}
)
PATH_ALLOWED = frozenset(
    {"stable_internal_id", "display_name", "waypoints", "entry_label", "exit_label"}
)
POINT_ALLOWED = frozenset({"x", "y"})
TARGET_ALLOWED = frozenset(
    {"stable_internal_id", "display_name", "position", "durability"}
)
SAMPLE_DELIVERY_ALLOWED = frozenset(
    {"delivery_delay_ms", "delivery_progress_messages"}
)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


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


def require_enum(
    value: Any, allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    if value not in allowed:
        errors.append(f"{path}={value!r} must be one of {sorted(allowed)}")


def check_pattern(
    value: Any, pattern: re.Pattern[str], path: str, errors: list[str]
) -> None:
    if not isinstance(value, str) or not pattern.match(value):
        errors.append(f"{path}={value!r} does not match {pattern.pattern}")


# ---------------------------------------------------------------------------
# Recursive safety scans (defense in depth)
# ---------------------------------------------------------------------------


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject forbidden field names anywhere in the document."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(
                    f"forbidden field '{child_path}' is not allowed in a "
                    f"runtime package (must not carry provider/trace/raw "
                    f"payloads)"
                )
            if key == FORBIDDEN_SOURCE_LAYER_FIELD:
                errors.append(
                    f"forbidden field '{child_path}' (source_layer is "
                    f"raw->published provenance and must not leak to runtime)"
                )
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_forbidden_fields(child, child_path, errors)


def scan_forbidden_url_strings(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject any string value containing http(s)/:// markers."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            scan_forbidden_url_strings(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_forbidden_url_strings(child, child_path, errors)
    elif isinstance(value, str):
        lowered = value.lower()
        for marker in FORBIDDEN_URL_MARKERS:
            if marker in lowered:
                errors.append(
                    f"{path}={value!r} must not contain '{marker}' "
                    f"(no provider/external URLs in a runtime package)"
                )
                break


def scan_forbidden_media_layers(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject raw_media / processed_media values anywhere.

    These media-layer values are internal-only; only published_media may be
    referenced by a runtime package (and even then only via /assets/ URLs).
    """
    if isinstance(value, dict):
        # A field named "media_layer" with a forbidden value is the primary
        # vector, but we also scan any string value equal to a forbidden
        # layer name to catch aliases or future fields.
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key == "media_layer" and child in FORBIDDEN_MEDIA_LAYER_VALUES:
                errors.append(
                    f"{child_path}={child!r} is not allowed in a runtime "
                    f"package (only published_media may be runtime_public)"
                )
            scan_forbidden_media_layers(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_forbidden_media_layers(child, child_path, errors)
    elif isinstance(value, str):
        if value in FORBIDDEN_MEDIA_LAYER_VALUES:
            errors.append(
                f"{path}={value!r} is a forbidden media layer value "
                f"(raw_media/processed_media must not appear in a runtime "
                f"package)"
            )


def scan_source_layer(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject any field named ``source_layer``.

    ``scan_forbidden_fields`` already covers this, but the task spec asks for
    a dedicated scan so the error message is unambiguous and so a future
    schema change cannot silently re-enable it.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key == FORBIDDEN_SOURCE_LAYER_FIELD:
                errors.append(
                    f"forbidden field '{child_path}' (source_layer is "
                    f"raw->published provenance and must not leak to runtime)"
                )
            scan_source_layer(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_source_layer(child, child_path, errors)


# ---------------------------------------------------------------------------
# Media URL and visual recipe checks
# ---------------------------------------------------------------------------


def check_media_url(url: Any, path: str, errors: list[str]) -> None:
    """Runtime package media URLs must be local /assets/ paths only."""
    if not isinstance(url, str):
        errors.append(f"{path} must be a string URL")
        return
    if not url.startswith("/assets/"):
        errors.append(
            f"{path}={url!r} must start with '/assets/' "
            f"(local cached published asset only)"
        )
    lowered = url.lower()
    for marker in FORBIDDEN_URL_MARKERS:
        if marker in lowered:
            errors.append(
                f"{path}={url!r} must not contain '{marker}' "
                f"(no provider/external URLs)"
            )
            break


# ---------------------------------------------------------------------------
# Pure-Python structural validation (mirrors the JSON Schema contract)
# ---------------------------------------------------------------------------


def validate_pure_python(package: dict[str, Any]) -> list[str]:
    """Pure-Python validation mirroring the JSON Schema contract."""
    errors: list[str] = []

    reject_unknown_keys(package, TOP_LEVEL_ALLOWED, "", errors)

    top_required = [
        "schema_version",
        "package_id",
        "session_id",
        "worldbook_id",
        "node_id",
        "battle_display_name",
        "created_at",
        "source_refs",
        "assets",
        "battle_context",
    ]
    for key in top_required:
        if key not in package:
            errors.append(f"missing top-level key: {key}")

    if package.get("schema_version") != "runtime_package.v0.1":
        errors.append(
            f"schema_version must be 'runtime_package.v0.1' "
            f"(got {package.get('schema_version')!r})"
        )

    for key in (
        "package_id",
        "session_id",
        "worldbook_id",
        "node_id",
        "battle_display_name",
    ):
        require_string(package.get(key), key, errors)

    created_at = package.get("created_at")
    if not isinstance(created_at, str) or not DATETIME_RE.match(created_at):
        errors.append(
            f"created_at={created_at!r} must be an ISO-8601 datetime string"
        )

    source_refs = require_object(package.get("source_refs"), "source_refs", errors)
    if source_refs:
        reject_unknown_keys(source_refs, SOURCE_REFS_ALLOWED, "source_refs", errors)
        require_string(
            source_refs.get("locked_manifest_id"),
            "source_refs.locked_manifest_id",
            errors,
        )
        require_string(
            source_refs.get("battle_config_version"),
            "source_refs.battle_config_version",
            errors,
        )

    assets = package.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be an array")
        assets = []
    for index, asset in enumerate(assets):
        validate_runtime_asset_pure(asset, f"assets[{index}]", errors)

    battle_context = require_object(
        package.get("battle_context"), "battle_context", errors
    )
    if battle_context:
        validate_battle_context_pure(battle_context, "battle_context", errors)

    return errors


def validate_runtime_asset_pure(asset: Any, path: str, errors: list[str]) -> None:
    asset = require_object(asset, path, errors)
    if not asset:
        return

    reject_unknown_keys(asset, RUNTIME_ASSET_ALLOWED, path, errors)

    required_fields = [
        "stable_internal_id",
        "asset_kind",
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

    require_string(asset.get("stable_internal_id"), f"{path}.stable_internal_id", errors)
    require_string(asset.get("asset_kind"), f"{path}.asset_kind", errors)
    require_enum(
        asset.get("lifecycle_state"),
        LIFECYCLE_STATES,
        f"{path}.lifecycle_state",
        errors,
    )

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
        require_string(
            gameplay_ref.get("kind"), f"{path}.gameplay_ref.kind", errors
        )
        require_string(
            gameplay_ref.get("path"), f"{path}.gameplay_ref.path", errors
        )
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
                    if (
                        not isinstance(dim_val, int)
                        or dim_val < 1
                        or isinstance(dim_val, bool)
                    ):
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


def validate_visual_recipe_pure(vr: Any, path: str, errors: list[str]) -> None:
    vr = require_object(vr, path, errors)
    if not vr:
        return

    reject_unknown_keys(vr, VISUAL_RECIPE_ALLOWED, path, errors)

    require_string(vr.get("trigger"), f"{path}.trigger", errors)
    require_enum(vr.get("kind"), VISUAL_RECIPE_KINDS, f"{path}.kind", errors)

    if "color" in vr:
        check_pattern(vr["color"], HEX6_RE, f"{path}.color", errors)
    if "secondary_color" in vr:
        check_pattern(vr["secondary_color"], HEX6_RE, f"{path}.secondary_color", errors)
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
            errors.append(f"{path}.duration_ms must be an integer in [0, 10000]")
    if "radius" in vr:
        radius = vr["radius"]
        if not isinstance(radius, (int, float)) or isinstance(radius, bool) or radius < 0:
            errors.append(f"{path}.radius must be a non-negative number")


def validate_battle_context_pure(ctx: Any, path: str, errors: list[str]) -> None:
    reject_unknown_keys(ctx, BATTLE_CONTEXT_ALLOWED, path, errors)

    required_fields = ["grid", "paths", "core_target", "optional_targets", "sample_delivery"]
    for key in required_fields:
        if key not in ctx:
            errors.append(f"missing key: {path}.{key}")

    grid = require_object(ctx.get("grid"), f"{path}.grid", errors)
    if grid:
        reject_unknown_keys(grid, GRID_ALLOWED, f"{path}.grid", errors)
        require_string(grid.get("projection"), f"{path}.grid.projection", errors)
        for dim_key in ("width_cells", "height_cells", "cell_size"):
            dim_val = grid.get(dim_key)
            if (
                not isinstance(dim_val, int)
                or isinstance(dim_val, bool)
                or dim_val < 1
            ):
                errors.append(
                    f"{path}.grid.{dim_key} must be a positive integer"
                )

    paths = ctx.get("paths")
    if not isinstance(paths, list):
        errors.append(f"{path}.paths must be an array")
        paths = []
    for p_index, p in enumerate(paths):
        p_obj = require_object(p, f"{path}.paths[{p_index}]", errors)
        if not p_obj:
            continue
        reject_unknown_keys(p_obj, PATH_ALLOWED, f"{path}.paths[{p_index}]", errors)
        require_string(
            p_obj.get("stable_internal_id"),
            f"{path}.paths[{p_index}].stable_internal_id",
            errors,
        )
        if "display_name" in p_obj:
            require_string(
                p_obj["display_name"],
                f"{path}.paths[{p_index}].display_name",
                errors,
            )
        waypoints = p_obj.get("waypoints")
        if not isinstance(waypoints, list) or not waypoints:
            errors.append(
                f"{path}.paths[{p_index}].waypoints must be a non-empty array"
            )
        else:
            for w_index, wp in enumerate(waypoints):
                wp_obj = require_object(
                    wp, f"{path}.paths[{p_index}].waypoints[{w_index}]", errors
                )
                if not wp_obj:
                    continue
                reject_unknown_keys(
                    wp_obj,
                    POINT_ALLOWED,
                    f"{path}.paths[{p_index}].waypoints[{w_index}]",
                    errors,
                )
                for coord in ("x", "y"):
                    cval = wp_obj.get(coord)
                    if (
                        not isinstance(cval, int)
                        or isinstance(cval, bool)
                    ):
                        errors.append(
                            f"{path}.paths[{p_index}].waypoints[{w_index}].{coord} "
                            f"must be an integer"
                        )
        if "entry_label" in p_obj:
            require_string(
                p_obj["entry_label"],
                f"{path}.paths[{p_index}].entry_label",
                errors,
            )
        if "exit_label" in p_obj:
            require_string(
                p_obj["exit_label"],
                f"{path}.paths[{p_index}].exit_label",
                errors,
            )

    core_target = require_object(
        ctx.get("core_target"), f"{path}.core_target", errors
    )
    if core_target:
        _validate_target(core_target, f"{path}.core_target", errors)

    optional_targets = ctx.get("optional_targets")
    if not isinstance(optional_targets, list):
        errors.append(f"{path}.optional_targets must be an array")
        optional_targets = []
    for t_index, t in enumerate(optional_targets):
        t_obj = require_object(
            t, f"{path}.optional_targets[{t_index}]", errors
        )
        if t_obj:
            _validate_target(t_obj, f"{path}.optional_targets[{t_index}]", errors)

    sample_delivery = require_object(
        ctx.get("sample_delivery"), f"{path}.sample_delivery", errors
    )
    if sample_delivery:
        reject_unknown_keys(
            sample_delivery,
            SAMPLE_DELIVERY_ALLOWED,
            f"{path}.sample_delivery",
            errors,
        )
        delay = sample_delivery.get("delivery_delay_ms")
        if (
            not isinstance(delay, int)
            or isinstance(delay, bool)
            or delay < 0
        ):
            errors.append(
                f"{path}.sample_delivery.delivery_delay_ms must be a non-negative integer"
            )
        msgs = sample_delivery.get("delivery_progress_messages")
        if not isinstance(msgs, list) or not msgs:
            errors.append(
                f"{path}.sample_delivery.delivery_progress_messages must be a non-empty array"
            )
        elif not all(isinstance(m, str) and m for m in msgs):
            errors.append(
                f"{path}.sample_delivery.delivery_progress_messages must contain non-empty strings"
            )


def _validate_target(target: dict[str, Any], path: str, errors: list[str]) -> None:
    reject_unknown_keys(target, TARGET_ALLOWED, path, errors)
    require_string(target.get("stable_internal_id"), f"{path}.stable_internal_id", errors)
    require_string(target.get("display_name"), f"{path}.display_name", errors)
    position = require_object(target.get("position"), f"{path}.position", errors)
    if position:
        reject_unknown_keys(position, POINT_ALLOWED, f"{path}.position", errors)
        for coord in ("x", "y"):
            cval = position.get(coord)
            if not isinstance(cval, int) or isinstance(cval, bool):
                errors.append(
                    f"{path}.position.{coord} must be an integer"
                )
    durability = target.get("durability")
    if (
        not isinstance(durability, int)
        or isinstance(durability, bool)
        or durability < 1
    ):
        errors.append(f"{path}.durability must be a positive integer")


# ---------------------------------------------------------------------------
# Composite validation entry point
# ---------------------------------------------------------------------------


def validate_with_jsonschema(
    package: dict[str, Any], schema: dict[str, Any]
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
    for error in sorted(validator.iter_errors(package), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in error.path) or "<root>"
        errors.append(f"schema violation at {location}: {error.message}")
    return errors


def validate_package(
    package: dict[str, Any], schema: dict[str, Any] | None
) -> list[str]:
    """Full validation: jsonschema + pure-Python + recursive safety scans."""
    errors: list[str] = []

    # Layer 1: jsonschema (if available).
    if schema is not None:
        errors.extend(validate_with_jsonschema(package, schema))

    # Layer 2: pure-Python structural check (always runs).
    errors.extend(validate_pure_python(package))

    # Layer 3: recursive forbidden-field scan (provider/model/raw_prompt/...).
    scan_forbidden_fields(package, "", errors)

    # Layer 4: recursive forbidden URL string scan.
    scan_forbidden_url_strings(package, "", errors)

    # Layer 5: recursive forbidden media-layer value scan.
    scan_forbidden_media_layers(package, "", errors)

    # Layer 6: dedicated source_layer scan.
    scan_source_layer(package, "", errors)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique_errors: list[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            unique_errors.append(err)
    return unique_errors


# ---------------------------------------------------------------------------
# Builder: derive a RuntimePackage from a locked manifest + battle config
# ---------------------------------------------------------------------------


# Internal-only fields that exist on locked_manifest.locked_assets but must
# NOT be carried into a runtime package (they are bookkeeping/provenance, not
# runtime data). The runtime asset keeps only: stable_internal_id, asset_kind,
# lifecycle_state, display, gameplay_ref, media_refs, visual_recipes,
# battle_availability.
_LOCKED_ASSET_INTERNAL_FIELDS = frozenset(
    {"template_id", "worldbook_id", "session_instance_id"}
)

# Internal-only fields on battle_config.sample_asset that must not leak into
# the runtime package's sample_delivery. Only delivery_delay_ms and
# delivery_progress_messages are player-facing.
_SAMPLE_ASSET_INTERNAL_FIELDS = frozenset(
    {
        "stable_internal_id",
        "asset_kind",
        "template_id",
        "lifecycle_state",
        "display_name",
        "uses_per_battle",
        "requires_delivery",
        "delivery_state",
        "effect_summary",
        "visual_recipes",
    }
)


def _copy_runtime_asset(locked_asset: dict[str, Any]) -> dict[str, Any]:
    """Copy a locked_manifest.locked_asset into a runtime asset shape.

    Drops internal bookkeeping fields (template_id, worldbook_id,
    session_instance_id) and keeps only the runtime-needed data. This is a
    defensive copy: unknown keys are stripped, so even if a future manifest
    adds an internal field it will not leak into the runtime package.
    """
    runtime_asset: dict[str, Any] = {}
    for key in (
        "stable_internal_id",
        "asset_kind",
        "lifecycle_state",
        "display",
        "gameplay_ref",
        "media_refs",
        "visual_recipes",
        "battle_availability",
    ):
        if key in locked_asset:
            runtime_asset[key] = locked_asset[key]
    return runtime_asset


def _copy_battle_context(battle_config: dict[str, Any]) -> dict[str, Any]:
    """Extract battle_context from a battle config.

    Pulls grid/paths/core_target/optional_targets directly, and synthesises
    sample_delivery from battle_config.sample_asset (delivery_delay_ms +
    delivery_progress_messages only). Internal sample_asset fields are not
    carried.
    """
    ctx: dict[str, Any] = {
        "grid": battle_config.get("grid"),
        "paths": battle_config.get("paths", []),
        "core_target": battle_config.get("core_target"),
        "optional_targets": battle_config.get("optional_targets", []),
    }
    sample_asset = battle_config.get("sample_asset") or {}
    ctx["sample_delivery"] = {
        "delivery_delay_ms": sample_asset.get("delivery_delay_ms", 0),
        "delivery_progress_messages": list(
            sample_asset.get("delivery_progress_messages", [])
        ),
    }
    return ctx


def build_runtime_package(
    locked_manifest: dict[str, Any],
    battle_config: dict[str, Any],
    *,
    package_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Derive a RuntimePackage v0.1 from a locked manifest + battle config.

    The returned package contains only runtime-safe data:
    - source_refs carry IDs/versions only, never the full manifest.
    - assets are filtered to runtime-needed fields.
    - battle_context is extracted from battle_config.
    - No execution_trace, no full compiled candidate, no raw_media /
      processed_media, no source_layer, no provider/trace fields.

    The caller is expected to run ``validate_package`` on the result before
    writing it to disk; the builder CLI does this automatically.
    """
    manifest_id = locked_manifest.get("manifest_id", "")
    session_id = locked_manifest.get("session_id", "")
    worldbook_id = locked_manifest.get("worldbook_id", "") or battle_config.get(
        "worldbook_id", ""
    )
    battle_config_version = battle_config.get("battle_config_version", "")
    node_id = battle_config.get("node_id", "")
    battle_display_name = battle_config.get("display_name", "")

    locked_assets = locked_manifest.get("locked_assets", [])
    if not isinstance(locked_assets, list):
        locked_assets = []
    runtime_assets = [_copy_runtime_asset(a) for a in locked_assets if isinstance(a, dict)]

    package: dict[str, Any] = {
        "schema_version": "runtime_package.v0.1",
        "package_id": package_id,
        "session_id": session_id,
        "worldbook_id": worldbook_id,
        "node_id": node_id,
        "battle_display_name": battle_display_name,
        "created_at": created_at,
        "source_refs": {
            "locked_manifest_id": manifest_id,
            "battle_config_version": battle_config_version,
        },
        "assets": runtime_assets,
        "battle_context": _copy_battle_context(battle_config),
    }
    return package
