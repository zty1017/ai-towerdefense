#!/usr/bin/env python3
"""Validate MapComponentMediaManifest v0.1.

The validator checks the manifest as local reviewed presentation evidence only.
It rejects provider/prompt/raw trace fields, external URLs, stale sha values,
missing local SVGs, and a backend URL prefix that is not statically mounted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_media_manifest.v0.1.schema.json"
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
    "local_reviewed_component_only",
    "frontend_default_presentation_allowed",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
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


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(manifest, schema))
    scan_forbidden_key_fragments(manifest, "", errors)
    scan_external_urls(manifest, "", errors)

    if manifest.get("schema_version") != "map_component_media_manifest.v0.1":
        errors.append("schema_version must be 'map_component_media_manifest.v0.1'")

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

        item_policy = set(map(str, as_list(item.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"items[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )

        local_path_value = item.get("local_path")
        if not isinstance(local_path_value, str) or not local_path_value.startswith(
            "game_data/media/map_components/processed/"
        ):
            errors.append(f"items[{index}].local_path must be under game_data/media/map_components/processed")
            continue
        local_path = ROOT / local_path_value
        if local_path.suffix != ".svg":
            errors.append(f"items[{index}].local_path must point to an SVG")
        if not local_path.exists():
            errors.append(f"items[{index}].local_path does not exist: {local_path_value}")
        else:
            expected_sha = sha256_file(local_path)
            if item.get("sha256") != expected_sha:
                errors.append(f"items[{index}].sha256 does not match local file")
            svg_head = local_path.read_text(encoding="utf-8")[:512].lower()
            if "<svg" not in svg_head:
                errors.append(f"items[{index}].local_path is not an SVG document")
            if "<text" in local_path.read_text(encoding="utf-8").lower():
                errors.append(f"items[{index}].svg must not contain visible text")

        expected_url = f"/assets/map_components/processed/{Path(local_path_value).name}"
        if item.get("url") != expected_url:
            errors.append(f"items[{index}].url must be {expected_url}")
        for dim_key in ("width", "height"):
            if not isinstance(item.get(dim_key), int) or item.get(dim_key) <= 0:
                errors.append(f"items[{index}].{dim_key} must be a positive integer")

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
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("roles")) != dict(sorted(roles.items())):
        errors.append("summary.roles must match item component_role counts")

    errors.extend(validate_backend_static_mount(manifest))
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentMediaManifest v0.1.")
    parser.add_argument("manifest", help="Manifest JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional schema path.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    schema_path = Path(args.schema)
    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print("INVALID MapComponentMediaManifest")
        print(f"- manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentMediaManifest")
        print(f"- manifest is not valid JSON: {exc}")
        return 1
    if not isinstance(manifest, dict):
        print("INVALID MapComponentMediaManifest")
        print("- manifest root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_manifest(manifest, schema)
    if errors:
        print("INVALID MapComponentMediaManifest")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(manifest.get("summary"))
    print(f"OK: {manifest_path}")
    print(f"- component_count: {summary.get('component_count')}")
    print(f"- material_component_count: {summary.get('material_component_count')}")
    print(f"- prefab_component_count: {summary.get('prefab_component_count')}")
    print("- static_mount: /assets/map_components -> game_data/media/map_components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
