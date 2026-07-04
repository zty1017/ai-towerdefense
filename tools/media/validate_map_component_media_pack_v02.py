#!/usr/bin/env python3
"""Validate preview MapComponentMediaManifest v0.2.

The validator keeps the v0.2 manifest as review-only media evidence. It
accepts SVG, PNG, WebP, and atlas animation references, but rejects provider
payloads, prompt traces, external URLs, stale hashes, unsafe SVGs, and atlas
references that cannot be resolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from validate_media_atlas_manifest import validate_atlas


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_media_manifest.v0.2.schema.json"
BACKEND_MAIN = ROOT / "backend/app/main.py"
MAP_COMPONENT_MEDIA_ROOT = ROOT / "game_data/media/map_components"
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
    "temporary_url",
)
EXTERNAL_URL_MARKERS = ("http://", "https://", "://")
REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_component_only",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
    "preview_artifact_only",
}
SINGLE_IMAGE_KINDS = {"svg", "png", "webp"}
MEDIA_KIND_TO_SUFFIX = {
    "svg": ".svg",
    "png": ".png",
    "webp": ".webp",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_relative_path_inside(value: str, base: Path) -> bool:
    path = Path(value)
    if path.is_absolute():
        return False
    if ".." in path.parts:
        return False
    try:
        resolved = (ROOT / path).resolve()
        resolved.relative_to(base.resolve())
    except ValueError:
        return False
    return True


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
        if any(marker in lowered for marker in EXTERNAL_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def validate_with_jsonschema(value: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
    if not schema:
        return []
    try:
        import jsonschema  # type: ignore
    except Exception:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator", None)
    if validator_cls is None:
        return []
    validator = validator_cls(schema)
    return [
        f"schema: {'.'.join(map(str, e.path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(value), key=str)
    ]


def validate_backend_static_mount(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    prefix = manifest.get("public_url_prefix")
    if prefix != "/assets/map_components":
        errors.append("public_url_prefix must be /assets/map_components")
        return errors
    try:
        source = BACKEND_MAIN.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"backend static mount source not found: {BACKEND_MAIN}")
        return errors
    if '"map_components"' not in source:
        errors.append("backend/app/main.py must register a map_components static namespace")
    if "game_data/media/map_components" not in source:
        errors.append("backend/app/main.py map_components mount must point to game_data/media/map_components")
    if 'f"/assets/{namespace}"' not in source and '"/assets/map_components"' not in source:
        errors.append("backend/app/main.py must mount the /assets/map_components URL prefix")
    return errors


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def webp_header_ok(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def validate_svg_file(path: Path, item_path: str, errors: list[str]) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{item_path}.local_path is not UTF-8 SVG")
        return
    lowered = source.lower()
    if "<svg" not in lowered[:512]:
        errors.append(f"{item_path}.local_path is not an SVG document")
    if "<text" in lowered:
        errors.append(f"{item_path}.svg must not contain visible text")
    if "<script" in lowered or "javascript:" in lowered:
        errors.append(f"{item_path}.svg must not contain script")
    remote_href = re.search(r"(?:href|xlink:href)\s*=\s*['\"](?:https?:)?//", lowered)
    remote_css_url = re.search(r"url\(\s*['\"]?(?:https?:)?//", lowered)
    if remote_href or remote_css_url:
        errors.append(f"{item_path}.svg must not contain remote hrefs")


def validate_single_image(item: dict[str, Any], index: int, errors: list[str]) -> None:
    item_path = f"items[{index}]"
    media_kind = item.get("media_kind")
    file_type = item.get("file_type")
    if media_kind not in SINGLE_IMAGE_KINDS:
        errors.append(f"{item_path}.media_kind must be svg, png, or webp for single image refs")
        return
    if file_type != media_kind:
        errors.append(f"{item_path}.file_type must match media_kind")

    local_path_value = item.get("local_path")
    if not isinstance(local_path_value, str) or not local_path_value.startswith(
        "game_data/media/map_components/"
    ):
        errors.append(f"{item_path}.local_path must be under game_data/media/map_components")
        return
    if not is_relative_path_inside(local_path_value, MAP_COMPONENT_MEDIA_ROOT):
        errors.append(f"{item_path}.local_path must stay inside game_data/media/map_components")
        return
    expected_suffix = MEDIA_KIND_TO_SUFFIX[str(media_kind)]
    local_path = ROOT / local_path_value
    if local_path.suffix.lower() != expected_suffix:
        errors.append(f"{item_path}.local_path suffix must be {expected_suffix}")
    if not local_path.exists():
        errors.append(f"{item_path}.local_path does not exist: {local_path_value}")
        return

    expected_url = f"/assets/map_components/{Path(local_path_value).relative_to('game_data/media/map_components').as_posix()}"
    if item.get("url") != expected_url:
        errors.append(f"{item_path}.url must be {expected_url}")
    if not isinstance(item.get("url"), str) or not str(item.get("url")).startswith(
        "/assets/map_components/"
    ):
        errors.append(f"{item_path}.url must be a local /assets/map_components path")

    expected_sha = sha256_file(local_path)
    if item.get("sha256") != expected_sha:
        errors.append(f"{item_path}.sha256 does not match local file")
    for dim_key in ("width", "height"):
        if not isinstance(item.get(dim_key), int) or item.get(dim_key) <= 0:
            errors.append(f"{item_path}.{dim_key} must be a positive integer")

    data = local_path.read_bytes()
    if media_kind == "svg":
        validate_svg_file(local_path, item_path, errors)
    elif media_kind == "png":
        dims = png_dimensions(data)
        if dims is None:
            errors.append(f"{item_path}.local_path is not a PNG file")
        elif item.get("width") != dims[0] or item.get("height") != dims[1]:
            errors.append(f"{item_path}.width/height must match PNG IHDR")
    elif media_kind == "webp" and not webp_header_ok(data):
        errors.append(f"{item_path}.local_path is not a RIFF/WEBP file")


def validate_spritesheet_summary(summary: dict[str, Any], item_path: str, errors: list[str]) -> None:
    local_path_value = summary.get("local_path")
    if not isinstance(local_path_value, str) or not local_path_value.startswith(
        "game_data/media/map_components/"
    ):
        errors.append(f"{item_path}.spritesheet_summary.local_path must be under game_data/media/map_components")
        return
    if not is_relative_path_inside(local_path_value, MAP_COMPONENT_MEDIA_ROOT):
        errors.append(
            f"{item_path}.spritesheet_summary.local_path must stay inside game_data/media/map_components"
        )
        return
    local_path = ROOT / local_path_value
    file_type = summary.get("file_type")
    if file_type not in {"png", "webp"}:
        errors.append(f"{item_path}.spritesheet_summary.file_type must be png or webp")
    elif local_path.suffix.lower() != f".{file_type}":
        errors.append(f"{item_path}.spritesheet_summary.local_path suffix must match file_type")
    if not local_path.exists():
        errors.append(f"{item_path}.spritesheet_summary.local_path does not exist: {local_path_value}")
        return
    expected_url = f"/assets/map_components/{Path(local_path_value).relative_to('game_data/media/map_components').as_posix()}"
    if summary.get("url") != expected_url:
        errors.append(f"{item_path}.spritesheet_summary.url must be {expected_url}")
    if sha256_file(local_path) != summary.get("sha256"):
        errors.append(f"{item_path}.spritesheet_summary.sha256 does not match local file")
    for dim_key in ("width", "height"):
        if not isinstance(summary.get(dim_key), int) or summary.get(dim_key) <= 0:
            errors.append(f"{item_path}.spritesheet_summary.{dim_key} must be a positive integer")
    data = local_path.read_bytes()
    if file_type == "png":
        dims = png_dimensions(data)
        if dims is None:
            errors.append(f"{item_path}.spritesheet_summary.local_path is not a PNG file")
        elif summary.get("width") != dims[0] or summary.get("height") != dims[1]:
            errors.append(f"{item_path}.spritesheet_summary.width/height must match PNG IHDR")
    elif file_type == "webp" and not webp_header_ok(data):
        errors.append(f"{item_path}.spritesheet_summary.local_path is not a RIFF/WEBP file")


def validate_atlas_item(item: dict[str, Any], index: int, errors: list[str]) -> None:
    item_path = f"items[{index}]"
    atlas_manifest_value = item.get("atlas_manifest_path")
    animation_id = item.get("animation_id")
    if not isinstance(atlas_manifest_value, str) or not atlas_manifest_value:
        errors.append(f"{item_path}.atlas_manifest_path must be non-empty")
        return
    if not isinstance(animation_id, str) or not animation_id:
        errors.append(f"{item_path}.animation_id must be non-empty")
        return
    atlas_path = ROOT / atlas_manifest_value
    if not is_relative_path_inside(atlas_manifest_value, MAP_COMPONENT_MEDIA_ROOT):
        errors.append(f"{item_path}.atlas_manifest_path must stay inside game_data/media/map_components")
        return
    if not atlas_path.exists():
        errors.append(f"{item_path}.atlas_manifest_path does not exist: {atlas_manifest_value}")
        return
    atlas = load_json(atlas_path)
    if not isinstance(atlas, dict):
        errors.append(f"{item_path}.atlas_manifest_path root must be an object")
        return
    for atlas_error in validate_atlas(atlas):
        errors.append(f"{item_path}.atlas_manifest_path invalid: {atlas_error}")
    atlas_items = [entry for entry in as_list(atlas.get("items")) if isinstance(entry, dict)]
    if animation_id not in {entry.get("animation_id") for entry in atlas_items}:
        errors.append(f"{item_path}.animation_id not found in atlas manifest")
    spritesheet_summary = item.get("spritesheet_summary")
    if spritesheet_summary is not None:
        if not isinstance(spritesheet_summary, dict):
            errors.append(f"{item_path}.spritesheet_summary must be object when present")
        else:
            validate_spritesheet_summary(spritesheet_summary, item_path, errors)


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(manifest, schema))
    scan_forbidden_key_fragments(manifest, "", errors)
    scan_external_urls(manifest, "", errors)

    if manifest.get("schema_version") != "map_component_media_manifest.v0.2":
        errors.append("schema_version must be 'map_component_media_manifest.v0.2'")
    if manifest.get("source_manifest_schema_version") != "map_component_media_manifest.v0.1":
        errors.append("source_manifest_schema_version must be map_component_media_manifest.v0.1")
    if manifest.get("media_layer") != "reviewed_map_component_media_preview_v0_2":
        errors.append("media_layer must be reviewed_map_component_media_preview_v0_2")

    usage_policy = set(map(str, as_list(manifest.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    items = [item for item in as_list(manifest.get("items")) if isinstance(item, dict)]
    stable_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    source_pairs: set[tuple[str, str, str]] = set()
    for index, item in enumerate(items):
        stable_id = item.get("stable_internal_id")
        if not isinstance(stable_id, str) or not re.fullmatch(r"[a-z0-9_]+", stable_id):
            errors.append(f"items[{index}].stable_internal_id must be a stable lowercase id")
        elif stable_id in stable_ids:
            duplicate_ids.add(stable_id)
        else:
            stable_ids.add(stable_id)

        if item.get("media_layer") != "reviewed_map_component_media_preview_v0_2":
            errors.append(f"items[{index}].media_layer must be reviewed_map_component_media_preview_v0_2")
        item_policy = set(map(str, as_list(item.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"items[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )

        media_kind = item.get("media_kind")
        if media_kind in SINGLE_IMAGE_KINDS:
            validate_single_image(item, index, errors)
        elif media_kind == "atlas_animation":
            validate_atlas_item(item, index, errors)
        else:
            errors.append(f"items[{index}].media_kind is invalid")

        source_key = (
            str(item.get("style_pack_id")),
            str(item.get("node_id")),
            str(item.get("source_owner_id")),
        )
        if source_key in source_pairs:
            errors.append(f"duplicate source component binding for {source_key}")
        source_pairs.add(source_key)

    for stable_id in sorted(duplicate_ids):
        errors.append(f"duplicate stable_internal_id: {stable_id}")

    summary = as_obj(manifest.get("summary"))
    roles = Counter(str(item.get("component_role")) for item in items)
    media_kind_counts = Counter(str(item.get("media_kind")) for item in items)
    expected = {
        "style_pack_count": len({item.get("style_pack_id") for item in items}),
        "node_count": len({item.get("node_id") for item in items}),
        "component_count": len(items),
        "material_component_count": len(
            [item for item in items if item.get("source_binding") == "material.component_ref"]
        ),
        "prefab_component_count": len(
            [item for item in items if item.get("source_binding") == "prefab.visual_ref"]
        ),
        "atlas_animation_count": media_kind_counts.get("atlas_animation", 0),
        "single_image_count": len(
            [item for item in items if item.get("media_kind") in SINGLE_IMAGE_KINDS]
        ),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("roles")) != dict(sorted(roles.items())):
        errors.append("summary.roles must match item component_role counts")
    if as_obj(summary.get("media_kind_counts")) != dict(sorted(media_kind_counts.items())):
        errors.append("summary.media_kind_counts must match item media_kind counts")

    errors.extend(validate_backend_static_mount(manifest))
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate preview MapComponentMediaManifest v0.2.")
    parser.add_argument("manifest", help="Manifest JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional schema path.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    schema_path = Path(args.schema)
    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print("INVALID MapComponentMediaManifest v0.2")
        print(f"- manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentMediaManifest v0.2")
        print(f"- manifest is not valid JSON: {exc}")
        return 1
    if not isinstance(manifest, dict):
        print("INVALID MapComponentMediaManifest v0.2")
        print("- manifest root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_manifest(manifest, schema)
    if errors:
        print("INVALID MapComponentMediaManifest v0.2")
        for error in errors:
            print(f"- {error}")
        return 1
    summary = as_obj(manifest.get("summary"))
    print(f"OK: {manifest_path}")
    print(f"- component_count: {summary.get('component_count')}")
    print(f"- single_image_count: {summary.get('single_image_count')}")
    print(f"- atlas_animation_count: {summary.get('atlas_animation_count')}")
    print(f"- media_kind_counts: {summary.get('media_kind_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
