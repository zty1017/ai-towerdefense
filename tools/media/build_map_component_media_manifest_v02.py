#!/usr/bin/env python3
"""Build preview MapComponentMediaManifest v0.2 from the v0.1 SVG baseline.

This migration is offline by design: it never calls providers, never reads
.env, and never changes the frontend default map component media contract.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"
DEFAULT_OUTPUT = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.2.json"
USAGE_POLICY_EXTENSION = "preview_artifact_only"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def with_preview_policy(policy: Any) -> list[str]:
    values = [str(item) for item in policy] if isinstance(policy, list) else []
    if USAGE_POLICY_EXTENSION not in values:
        values.append(USAGE_POLICY_EXTENSION)
    return values


def migrate_item(item: dict[str, Any]) -> dict[str, Any]:
    migrated = {
        "stable_internal_id": item.get("stable_internal_id"),
        "asset_id": item.get("asset_id"),
        "asset_type": item.get("asset_type"),
        "media_role": item.get("media_role"),
        "media_layer": "reviewed_map_component_media_preview_v0_2",
        "media_kind": "svg",
        "component_role": item.get("component_role"),
        "style_pack_id": item.get("style_pack_id"),
        "node_id": item.get("node_id"),
        "source_owner_id": item.get("source_owner_id"),
        "source_binding": item.get("source_binding"),
        "url": item.get("url"),
        "local_path": item.get("local_path"),
        "width": item.get("width"),
        "height": item.get("height"),
        "sha256": item.get("sha256"),
        "file_type": "svg",
        "usage_policy": with_preview_policy(item.get("usage_policy")),
        "source_kind": item.get("source_kind") or "deterministic_developer_fixture_svg",
    }
    return {key: value for key, value in migrated.items() if value is not None}


def build_manifest(source_path: Path, output_path: Path, *, created_at: str) -> dict[str, Any]:
    source = load_json(source_path)
    if not isinstance(source, dict):
        raise ValueError("source manifest root must be an object")
    if source.get("schema_version") != "map_component_media_manifest.v0.1":
        raise ValueError("source manifest must be map_component_media_manifest.v0.1")

    source_items = source.get("items")
    if not isinstance(source_items, list):
        raise ValueError("source manifest items must be an array")
    items = [migrate_item(item) for item in source_items if isinstance(item, dict)]

    roles = Counter(str(item.get("component_role")) for item in items)
    media_kind_counts = Counter(str(item.get("media_kind")) for item in items)
    summary = {
        "style_pack_count": len({item.get("style_pack_id") for item in items}),
        "node_count": len({item.get("node_id") for item in items}),
        "component_count": len(items),
        "material_component_count": len(
            [item for item in items if item.get("source_binding") == "material.component_ref"]
        ),
        "prefab_component_count": len(
            [item for item in items if item.get("source_binding") == "prefab.visual_ref"]
        ),
        "roles": dict(sorted(roles.items())),
        "media_kind_counts": dict(sorted(media_kind_counts.items())),
        "atlas_animation_count": media_kind_counts.get("atlas_animation", 0),
        "single_image_count": len(
            [item for item in items if item.get("media_kind") in {"svg", "png", "webp"}]
        ),
    }

    manifest = {
        "schema_version": "map_component_media_manifest.v0.2",
        "media_pack_id": "map_component_media_pack_v0_2_preview",
        "created_at": created_at,
        "source_manifest_path": rel(source_path),
        "source_manifest_schema_version": str(source.get("schema_version")),
        "source_style_pack_paths": source.get("source_style_pack_paths", []),
        "public_url_prefix": "/assets/map_components",
        "media_layer": "reviewed_map_component_media_preview_v0_2",
        "usage_policy": with_preview_policy(source.get("usage_policy")),
        "items": items,
        "summary": summary,
        "validation": {
            "validator": "tools/media/validate_map_component_media_pack_v02.py",
            "commands": [
                "python3 tools/media/validate_map_component_media_pack_v02.py game_data/media/map_components/map_component_media_manifest.v0.2.json"
            ],
        },
    }
    write_json(output_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build preview MapComponentMediaManifest v0.2 from the v0.1 baseline."
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Source v0.1 manifest path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output v0.2 manifest path.")
    parser.add_argument("--created-at", default=now_iso())
    args = parser.parse_args()

    source_path = resolve_path(args.source)
    output_path = resolve_path(args.output)
    manifest = build_manifest(source_path, output_path, created_at=args.created_at)
    summary = manifest["summary"]
    print(f"OK: wrote {output_path}")
    print(f"- component_count: {summary['component_count']}")
    print(f"- single_image_count: {summary['single_image_count']}")
    print(f"- atlas_animation_count: {summary['atlas_animation_count']}")
    print(f"- media_kind_counts: {summary['media_kind_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
