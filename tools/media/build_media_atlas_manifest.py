#!/usr/bin/env python3
"""Build a virtual atlas manifest from an existing published media manifest."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREATED_AT = "2026-07-02T00:00:00+08:00"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def animation_state_for_role(role: str) -> str:
    if role.endswith("_sprite") or role in {"unit_sprite", "tower_sprite", "defense_sprite"}:
        return "idle"
    if role in {"icon", "portrait", "ui_card"}:
        return "static"
    return "default"


def build_atlas_manifest(
    media_manifest: dict[str, Any],
    *,
    source_manifest_path: str,
    atlas_id: str,
    created_at: str = DEFAULT_CREATED_AT,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    roles: Counter[str] = Counter()
    asset_ids: set[str] = set()
    source_items = media_manifest.get("items")
    if not isinstance(source_items, list):
        source_items = []
    for item in source_items:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or item.get("source_game_id") or "")
        role = str(item.get("media_role") or "")
        url = str(item.get("url") or "")
        local_path = str(item.get("local_path") or "")
        sha = str(item.get("sha256") or "")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if not asset_id or not role or not url or not local_path or width <= 0 or height <= 0:
            continue
        anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
        anchor_x = float(anchor.get("x", 0.5))
        anchor_y = float(anchor.get("y", 1.0 if role.endswith("_sprite") else 0.5))
        anchor_preset = str(anchor.get("preset") or ("bottom_center" if anchor_y >= 0.95 else "center"))
        animation_id = f"{asset_id}.{role}.{animation_state_for_role(role)}"
        frame_id = f"{animation_id}.frame_000"
        items.append(
            {
                "animation_id": animation_id,
                "asset_id": asset_id,
                "source_game_id": item.get("source_game_id"),
                "asset_name": item.get("asset_name"),
                "asset_type": item.get("asset_type"),
                "media_role": role,
                "playback": {
                    "state": animation_state_for_role(role),
                    "fps": 1,
                    "loop": False,
                    "frame_count": 1,
                },
                "spritesheet": None,
                "frames": [
                    {
                        "frame_id": frame_id,
                        "index": 0,
                        "url": url,
                        "local_path": local_path,
                        "x": 0,
                        "y": 0,
                        "width": width,
                        "height": height,
                        "duration_ms": 1000,
                        "sha256": sha,
                        "anchor": {
                            "preset": anchor_preset,
                            "x": anchor_x,
                            "y": anchor_y,
                        },
                    }
                ],
            }
        )
        roles[role] += 1
        asset_ids.add(asset_id)

    return {
        "schema_version": "media_atlas_manifest.v0.1",
        "atlas_id": atlas_id,
        "created_at": created_at,
        "source_manifest": source_manifest_path,
        "source_media_pack_id": str(media_manifest.get("media_pack_id") or media_manifest.get("source_pack_id") or ""),
        "media_layer": "published_media",
        "atlas_mode": "virtual_single_frame",
        "public_url_prefix": str(media_manifest.get("public_url_prefix") or "/assets"),
        "items": items,
        "summary": {
            "animation_count": len(items),
            "frame_count": len(items),
            "asset_count": len(asset_ids),
            "roles": dict(sorted(roles.items())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a MediaAtlasManifest v0.1.")
    parser.add_argument("--manifest", required=True, help="Input media manifest path.")
    parser.add_argument("--output", required=True, help="Output atlas manifest path.")
    parser.add_argument("--atlas-id", required=True, help="Atlas manifest id.")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    source = load_json(manifest_path)
    if not isinstance(source, dict):
        raise SystemExit("input media manifest root must be an object")
    atlas = build_atlas_manifest(
        source,
        source_manifest_path=rel(manifest_path),
        atlas_id=args.atlas_id,
        created_at=args.created_at,
    )
    write_json(output_path, atlas)
    print(f"OK: wrote {output_path}")
    print(f"- animations: {atlas['summary']['animation_count']}")
    print(f"- frames: {atlas['summary']['frame_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
