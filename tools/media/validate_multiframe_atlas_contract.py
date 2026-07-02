#!/usr/bin/env python3
"""Validate project-level expectations for multi-frame media atlases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_media_atlas_manifest import validate_atlas


ANIMATED_ROLES = {"tower_sprite", "unit_sprite", "defense_sprite", "objective_sprite"}
STATIC_ROLES = {"icon", "portrait", "ui_card"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_contract(atlas: dict[str, Any]) -> list[str]:
    errors = validate_atlas(atlas)
    if atlas.get("atlas_mode") != "spritesheet":
        errors.append("atlas_mode must be spritesheet for multi-frame runtime atlases")

    animated_count = 0
    frame_urls: set[str] = set()
    for index, item in enumerate(atlas.get("items") or []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("media_role") or "")
        playback = item.get("playback") if isinstance(item.get("playback"), dict) else {}
        frames = item.get("frames") if isinstance(item.get("frames"), list) else []
        if not isinstance(item.get("spritesheet"), dict):
            errors.append(f"items[{index}].spritesheet must be a physical spritesheet object")
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            url = str(frame.get("url") or "")
            if url in frame_urls:
                errors.append(f"duplicate frame url: {url}")
            frame_urls.add(url)
        if role in STATIC_ROLES and len(frames) != 1:
            errors.append(f"static role must keep one frame: items[{index}] {role}")
        if role in ANIMATED_ROLES or role.endswith("_sprite"):
            if len(frames) < 2:
                errors.append(f"animated role must have at least two frames: items[{index}] {role}")
            if playback.get("loop") is not True:
                errors.append(f"animated role must loop: items[{index}] {role}")
            if int(playback.get("fps") or 0) < 4:
                errors.append(f"animated role fps must be >= 4: items[{index}] {role}")
            animated_count += 1

    if animated_count <= 0:
        errors.append("atlas must contain at least one animated sprite role")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate multi-frame atlas contract.")
    parser.add_argument("atlas", help="MediaAtlasManifest path.")
    args = parser.parse_args()
    atlas = load_json(Path(args.atlas))
    if not isinstance(atlas, dict):
        print("INVALID multi-frame atlas")
        print("- root must be object")
        return 1
    errors = validate_contract(atlas)
    if errors:
        print("INVALID multi-frame atlas")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {args.atlas}")
    print(f"- animations: {atlas.get('summary', {}).get('animation_count')}")
    print(f"- frames: {atlas.get('summary', {}).get('frame_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
