#!/usr/bin/env python3
"""Validate StrategicMapMarkerMediaManifest v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/strategic_map_marker_media_manifest.v0.1.schema.json"
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
    "temporary_url",
)
EXTERNAL_URL_MARKERS = ("http://", "https://", "://")
REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_marker_only",
    "frontend_default_presentation_allowed",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:33]
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


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
        f"schema: {'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(value), key=str)
    ]


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
        if any(marker in value.lower() for marker in EXTERNAL_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def validate_backend_static_mount(errors: list[str]) -> None:
    try:
        source = BACKEND_MAIN.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"backend static mount source not found: {BACKEND_MAIN}")
        return
    if '"strategic_map_markers"' not in source:
        errors.append("backend/app/main.py must register strategic_map_markers static namespace")
    if "game_data/media/strategic_map_markers" not in source:
        errors.append(
            "backend/app/main.py strategic_map_markers mount must point to game_data/media/strategic_map_markers"
        )
    if 'f"/assets/{namespace}"' not in source and '"/assets/strategic_map_markers"' not in source:
        errors.append("backend/app/main.py must mount /assets/strategic_map_markers")


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(manifest, schema))
    scan_forbidden_key_fragments(manifest, "", errors)
    scan_external_urls(manifest, "", errors)

    if manifest.get("schema_version") != "strategic_map_marker_media_manifest.v0.1":
        errors.append("schema_version must be 'strategic_map_marker_media_manifest.v0.1'")
    if manifest.get("public_url_prefix") != "/assets/strategic_map_markers":
        errors.append("public_url_prefix must be /assets/strategic_map_markers")

    policy = set(map(str, as_list(manifest.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    atlas = as_obj(manifest.get("atlas"))
    atlas_local_value = atlas.get("local_path")
    atlas_width = int(atlas.get("width") or 0)
    atlas_height = int(atlas.get("height") or 0)
    if not isinstance(atlas_local_value, str) or not atlas_local_value.startswith(
        "game_data/media/strategic_map_markers/processed/"
    ):
        errors.append("atlas.local_path must be under game_data/media/strategic_map_markers/processed")
        atlas_path = None
    else:
        atlas_path = ROOT / atlas_local_value
        if not atlas_path.exists():
            errors.append(f"atlas.local_path does not exist: {atlas_local_value}")
        elif atlas_path.suffix != ".png":
            errors.append("atlas.local_path must point to a PNG")
        else:
            dimensions = png_dimensions(atlas_path)
            if dimensions is None:
                errors.append("atlas.local_path is not a valid PNG")
            else:
                if dimensions != (atlas_width, atlas_height):
                    errors.append(f"atlas dimensions must be {dimensions}, got {(atlas_width, atlas_height)}")
            if atlas.get("sha256") != sha256_file(atlas_path):
                errors.append("atlas.sha256 does not match local file")

    expected_url = (
        f"/assets/strategic_map_markers/processed/{Path(str(atlas_local_value)).name}"
        if isinstance(atlas_local_value, str)
        else None
    )
    if expected_url and atlas.get("url") != expected_url:
        errors.append(f"atlas.url must be {expected_url}")

    items = [item for item in as_list(manifest.get("items")) if isinstance(item, dict)]
    stable_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    kind_counts = Counter()
    for index, item in enumerate(items):
        stable_id = item.get("stable_internal_id")
        if not isinstance(stable_id, str) or not re.fullmatch(r"[a-z0-9_]+", stable_id):
            errors.append(f"items[{index}].stable_internal_id must be a stable lowercase id")
        elif stable_id in stable_ids:
            duplicate_ids.add(stable_id)
        else:
            stable_ids.add(stable_id)

        item_policy = set(map(str, as_list(item.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"items[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )
        if item.get("source_kind") != "deterministic_developer_fixture_png_atlas":
            errors.append(f"items[{index}].source_kind must be deterministic_developer_fixture_png_atlas")
        node_kind = str(item.get("node_kind") or "")
        if not node_kind:
            errors.append(f"items[{index}].node_kind must be non-empty")
        else:
            kind_counts[node_kind] += 1

        frame = as_obj(item.get("atlas_frame"))
        x = int(frame.get("x") or 0)
        y = int(frame.get("y") or 0)
        width = int(frame.get("width") or 0)
        height = int(frame.get("height") or 0)
        if width <= 0 or height <= 0:
            errors.append(f"items[{index}].atlas_frame width/height must be positive")
        if x < 0 or y < 0 or x + width > atlas_width or y + height > atlas_height:
            errors.append(f"items[{index}].atlas_frame must stay inside atlas bounds")
        for key in ("anchor_x", "anchor_y", "display_width", "display_height"):
            value = frame.get(key)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"items[{index}].atlas_frame.{key} must be positive")

    for stable_id in sorted(duplicate_ids):
        errors.append(f"duplicate stable_internal_id: {stable_id}")

    required_kinds = {"main_city", "battle_hotspot", "research_facility", "resource_storage", "generic"}
    missing_kinds = sorted(required_kinds - set(kind_counts))
    if missing_kinds:
        errors.append(f"items missing required node kinds: {', '.join(missing_kinds)}")

    summary = as_obj(manifest.get("summary"))
    if summary.get("marker_count") != len(items):
        errors.append(f"summary.marker_count must be {len(items)}")
    if summary.get("atlas_frame_count") != len(items):
        errors.append(f"summary.atlas_frame_count must be {len(items)}")
    if as_obj(summary.get("node_kinds")) != dict(sorted(kind_counts.items())):
        errors.append("summary.node_kinds must match item node_kind counts")

    validate_backend_static_mount(errors)
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate StrategicMapMarkerMediaManifest v0.1.")
    parser.add_argument("manifest", help="Manifest JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    schema_path = Path(args.schema)
    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print("INVALID StrategicMapMarkerMediaManifest")
        print(f"- manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID StrategicMapMarkerMediaManifest")
        print(f"- manifest is not valid JSON: {exc}")
        return 1
    if not isinstance(manifest, dict):
        print("INVALID StrategicMapMarkerMediaManifest")
        print("- manifest root must be an object")
        return 1
    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_manifest(manifest, schema)
    if errors:
        print("INVALID StrategicMapMarkerMediaManifest")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {manifest_path}")
    print(f"- marker_count: {manifest['summary']['marker_count']}")
    print(f"- atlas: {manifest['atlas']['local_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
