#!/usr/bin/env python3
"""Validate LayeredMapVisualPackage v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/layered_map_visual_package.v0.1.schema.json"
BACKEND_MAIN = ROOT / "backend/app/main.py"
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
    "raw_prompt",
    "full_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
)
FORBIDDEN_URL_MARKERS = ("http://", "https://", "://")
REQUIRED_ROLES = {
    "terrain_base",
    "terrain_detail",
    "road_shadow",
    "road_edge",
    "road_surface",
    "build_slots",
    "objectives",
    "spawn",
    "semantic_props",
    "non_blocking_decorations",
    "lighting",
    "fog_weather",
    "color_grade",
    "composited",
}
REQUIRED_USAGE_POLICY = {
    "runtime_semantics_from_map_runtime_package",
    "visual_package_is_presentation_only",
    "no_pixel_to_semantic_inference",
    "player_default_presentation_allowed",
    "local_reviewed_artifact_only",
    "no_raw_generation_payload",
    "no_external_temporary_url",
    "painted_backdrop_must_not_bake_build_slots",
    "painted_backdrop_must_not_bake_path_routes",
}
REQUIRED_MEDIA_ROLES = {
    "terrain_tile",
    "terrain_detail_tile",
    "road_tile",
    "road_edge_tile",
    "road_detail_atlas",
    "slot_tile",
    "shadow_overlay_tile",
    "fog_overlay_tile",
    "light_overlay_tile",
}
OPTIONAL_MEDIA_ROLES = {
    "reviewed_painted_backdrop",
    "objective_foundation",
    "spawn_marker",
    "non_blocking_decoration",
}
COMPONENT_MEDIA_ROLES = {
    "objective_foundation",
    "spawn_marker",
    "non_blocking_decoration",
}
SUPPORTED_MEDIA_ROLES = REQUIRED_MEDIA_ROLES | OPTIONAL_MEDIA_ROLES


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed")
            scan_forbidden_key_fragments(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_key_fragments(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_external_urls(child, f"{path}.{key}" if path else key, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in FORBIDDEN_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def validate_backend_static_mount() -> list[str]:
    errors: list[str] = []
    try:
        source = BACKEND_MAIN.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"backend static mount source not found: {BACKEND_MAIN}"]
    if '"layered_maps"' not in source:
        errors.append("backend/app/main.py must register a layered_maps static namespace")
    if "game_data/media/layered_maps" not in source:
        errors.append("backend/app/main.py layered_maps mount must point to game_data/media/layered_maps")
    if 'f"/assets/{namespace}"' not in source and '"/assets/layered_maps"' not in source:
        errors.append("backend/app/main.py must mount the /assets/layered_maps URL prefix")
    return errors


def validate_manifest(manifest: dict[str, Any], schema_path: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_json_schema(manifest, schema_path))
    scan_forbidden_key_fragments(manifest, "", errors)
    scan_external_urls(manifest, "", errors)

    if manifest.get("schema_version") != "layered_map_visual_package.v0.1":
        errors.append("schema_version must be layered_map_visual_package.v0.1")

    usage_policy = set(map(str, as_list(manifest.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    runtime_source = as_obj(manifest.get("runtime_semantics_source"))
    if runtime_source.get("kind") != "MapRuntimePackage":
        errors.append("runtime_semantics_source.kind must be MapRuntimePackage")
    if runtime_source.get("authority") != "runtime_semantic_truth":
        errors.append("runtime_semantics_source.authority must be runtime_semantic_truth")

    media_items = [item for item in as_list(manifest.get("media_assets")) if isinstance(item, dict)]
    media_roles = {str(item.get("role")) for item in media_items}
    missing_media_roles = sorted(REQUIRED_MEDIA_ROLES - media_roles)
    if missing_media_roles:
        errors.append(f"media_assets missing required texture roles: {', '.join(missing_media_roles)}")
    for index, item in enumerate(media_items):
        role = item.get("role")
        local_path_value = item.get("local_path")
        if not isinstance(local_path_value, str) or not local_path_value.startswith(
            "game_data/media/layered_maps/"
        ):
            errors.append(f"media_assets[{index}].local_path must be under game_data/media/layered_maps")
            continue
        local_path = ROOT / local_path_value
        if local_path.suffix != ".png":
            errors.append(f"media_assets[{index}].local_path must point to a PNG")
        if not local_path.exists():
            errors.append(f"media_assets[{index}].local_path does not exist: {local_path_value}")
            continue
        expected_sha = sha256_file(local_path)
        if item.get("sha256") != expected_sha:
            errors.append(f"media_assets[{index}].sha256 does not match local file")
        try:
            width, height = png_dimensions(local_path)
        except ValueError as exc:
            errors.append(f"media_assets[{index}].local_path is not a valid PNG: {exc}")
            continue
        if item.get("width") != width or item.get("height") != height:
            errors.append(f"media_assets[{index}].width/height must match PNG header")
        expected_url = "/assets/layered_maps/" + local_path.relative_to(
            ROOT / "game_data/media/layered_maps"
        ).as_posix()
        if item.get("url") != expected_url:
            errors.append(f"media_assets[{index}].url must be {expected_url}")
        if role == "reviewed_painted_backdrop":
            expected_media_kind = "map_backdrop_png"
        elif role == "road_detail_atlas":
            expected_media_kind = "texture_atlas_png"
        elif role in COMPONENT_MEDIA_ROLES:
            expected_media_kind = "component_sprite_png"
        else:
            expected_media_kind = "texture_tile_png"
        if role == "reviewed_painted_backdrop":
            expected_usage = "presentation_backdrop_only"
        elif role in COMPONENT_MEDIA_ROLES:
            expected_usage = "presentation_component_only"
        else:
            expected_usage = "presentation_texture_only"
        if item.get("media_kind") != expected_media_kind:
            errors.append(f"media_assets[{index}].media_kind must be {expected_media_kind}")
        if item.get("usage") != expected_usage:
            errors.append(f"media_assets[{index}].usage must be {expected_usage}")
        if role not in SUPPORTED_MEDIA_ROLES:
            errors.append(f"media_assets[{index}].role is not supported: {role}")
        source_kind = item.get("source_kind")
        if source_kind and source_kind not in {
            "procedural_texture",
            "local_ai_exploration_texture",
            "local_ai_exploration_backdrop",
            "compiled_reviewed_texture",
            "compiled_reviewed_backdrop",
            "compiled_reviewed_component",
        }:
            errors.append(f"media_assets[{index}].source_kind is not supported: {source_kind}")
        source_local_path = item.get("source_local_path")
        if source_kind in {"local_ai_exploration_texture", "local_ai_exploration_backdrop"}:
            if not isinstance(source_local_path, str) or not source_local_path.startswith(
                "game_data/media/layered_maps/_exploration/"
            ):
                errors.append(
                    f"media_assets[{index}].source_local_path must point to local exploration media"
                )
            elif not (ROOT / source_local_path).exists():
                errors.append(f"media_assets[{index}].source_local_path does not exist: {source_local_path}")
        if source_kind in {
            "compiled_reviewed_texture",
            "compiled_reviewed_backdrop",
            "compiled_reviewed_component",
        }:
            is_reviewed_staging = (
                isinstance(source_local_path, str)
                and source_local_path.startswith("game_data/media/layered_maps/")
                and "/reviewed_visual_staging/" in source_local_path
            )
            if not is_reviewed_staging:
                errors.append(
                    f"media_assets[{index}].source_local_path must point to map reviewed visual staging"
                )
            elif not (ROOT / source_local_path).exists():
                errors.append(f"media_assets[{index}].source_local_path does not exist: {source_local_path}")

    layer_items = [item for item in as_list(manifest.get("layers")) if isinstance(item, dict)]
    roles = {str(item.get("role")) for item in layer_items}
    missing_roles = sorted(REQUIRED_ROLES - roles)
    if missing_roles:
        errors.append(f"layers missing required roles: {', '.join(missing_roles)}")
    if len([item for item in layer_items if item.get("role") == "composited"]) != 1:
        errors.append("layers must contain exactly one composited layer")

    for index, item in enumerate(layer_items):
        role = item.get("role")
        local_path_value = item.get("local_path")
        if not isinstance(local_path_value, str) or not local_path_value.startswith(
            "game_data/media/layered_maps/"
        ):
            errors.append(f"layers[{index}].local_path must be under game_data/media/layered_maps")
            continue
        local_path = ROOT / local_path_value
        if local_path.suffix != ".svg":
            errors.append(f"layers[{index}].local_path must point to an SVG")
        if not local_path.exists():
            errors.append(f"layers[{index}].local_path does not exist: {local_path_value}")
            continue
        expected_sha = sha256_file(local_path)
        if item.get("sha256") != expected_sha:
            errors.append(f"layers[{index}].sha256 does not match local file")
        text = local_path.read_text(encoding="utf-8").lower()
        if "<svg" not in text[:512]:
            errors.append(f"layers[{index}].local_path is not an SVG document")
        if "<text" in text:
            errors.append(f"layers[{index}].svg must not contain visible text")
        text_without_svg_namespace = text.replace("http://www.w3.org/2000/svg", "")
        if "http://" in text_without_svg_namespace or "https://" in text_without_svg_namespace:
            errors.append(f"layers[{index}].svg must not contain external URLs")
        expected_url = "/assets/layered_maps/" + local_path.relative_to(
            ROOT / "game_data/media/layered_maps"
        ).as_posix()
        if item.get("url") != expected_url:
            errors.append(f"layers[{index}].url must be {expected_url}")
        quality = as_obj(item.get("quality"))
        if item.get("player_default") and quality.get("player_visible_quality") != "passed":
            errors.append(f"layers[{index}] player_default layer must have passed player_visible_quality")
        if role == "composited" and item.get("source") != "derived_composite":
            errors.append("composited layer source must be derived_composite")

    alignment_report = as_obj(manifest.get("alignment_report"))
    if alignment_report.get("gate_status") != "passed":
        errors.append("alignment_report.gate_status must be passed")
    if alignment_report.get("runtime_truth_preserved") is not True:
        errors.append("alignment_report.runtime_truth_preserved must be true")
    if as_obj(manifest.get("validation_report")).get("player_default_safe") is not True:
        errors.append("validation_report.player_default_safe must be true")
    if as_obj(manifest.get("validation_report")).get("external_generation_call_count") != 0:
        errors.append("validation_report.external_generation_call_count must be 0 for this offline fixture")
    errors.extend(validate_backend_static_mount())
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate LayeredMapVisualPackage v0.1.")
    parser.add_argument("manifest", help="LayeredMapVisualPackage JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional JSON schema path.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print("INVALID LayeredMapVisualPackage")
        print(f"- manifest not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID LayeredMapVisualPackage")
        print(f"- manifest is not valid JSON: {exc}")
        return 1
    if not isinstance(manifest, dict):
        print("INVALID LayeredMapVisualPackage")
        print("- manifest root must be an object")
        return 1

    errors = validate_manifest(manifest, Path(args.schema))
    if errors:
        print("INVALID LayeredMapVisualPackage")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {manifest_path}")
    print(f"- package_id: {manifest.get('package_id')}")
    print(f"- layers: {len(manifest.get('layers', []))}")
    print(f"- node_id: {manifest.get('node_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
