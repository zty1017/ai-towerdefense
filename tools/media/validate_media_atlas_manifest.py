#!/usr/bin/env python3
"""Validate a MediaAtlasManifest v0.1 file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_KEYS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                errors.append(f"forbidden key: {child_path}")
            scan_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, f"{path}[{index}]", errors)


def validate_atlas(atlas: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if atlas.get("schema_version") != "media_atlas_manifest.v0.1":
        errors.append("schema_version must be media_atlas_manifest.v0.1")
    if atlas.get("atlas_mode") not in {"virtual_single_frame", "spritesheet"}:
        errors.append("atlas_mode must be virtual_single_frame or spritesheet")
    items = atlas.get("items")
    if not isinstance(items, list):
        errors.append("items must be an array")
        items = []
    seen: set[str] = set()
    frame_count = 0
    asset_ids: set[str] = set()
    roles: dict[str, int] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be object")
            continue
        animation_id = item.get("animation_id")
        if not isinstance(animation_id, str) or not animation_id:
            errors.append(f"items[{index}].animation_id must be non-empty")
        elif animation_id in seen:
            errors.append(f"duplicate animation_id: {animation_id}")
        else:
            seen.add(animation_id)
        asset_id = item.get("asset_id")
        if isinstance(asset_id, str) and asset_id:
            asset_ids.add(asset_id)
        else:
            errors.append(f"items[{index}].asset_id must be non-empty")
        role = item.get("media_role")
        if isinstance(role, str) and role:
            roles[role] = roles.get(role, 0) + 1
        else:
            errors.append(f"items[{index}].media_role must be non-empty")
        playback = item.get("playback")
        if not isinstance(playback, dict):
            errors.append(f"items[{index}].playback must be object")
            playback = {}
        frames = item.get("frames")
        if not isinstance(frames, list) or not frames:
            errors.append(f"items[{index}].frames must be non-empty")
            frames = []
        if playback.get("frame_count") != len(frames):
            errors.append(f"items[{index}].playback.frame_count must match frames length")
        for frame_index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                errors.append(f"items[{index}].frames[{frame_index}] must be object")
                continue
            frame_count += 1
            url = frame.get("url")
            if not isinstance(url, str) or not url.startswith("/assets/"):
                errors.append(f"items[{index}].frames[{frame_index}].url must start with /assets/")
            local_path = frame.get("local_path")
            if not isinstance(local_path, str) or not local_path:
                errors.append(f"items[{index}].frames[{frame_index}].local_path must be non-empty")
            elif not (ROOT / local_path).exists():
                errors.append(f"missing frame local_path: {local_path}")
            for key in ("width", "height", "duration_ms"):
                value = frame.get(key)
                if not isinstance(value, int) or value <= 0:
                    errors.append(f"items[{index}].frames[{frame_index}].{key} must be positive integer")
            sha = frame.get("sha256")
            if not isinstance(sha, str) or not SHA256_RE.match(sha):
                errors.append(f"items[{index}].frames[{frame_index}].sha256 must be lowercase sha256")
            anchor = frame.get("anchor")
            if not isinstance(anchor, dict):
                errors.append(f"items[{index}].frames[{frame_index}].anchor must be object")
    summary = atlas.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be object")
    else:
        if summary.get("animation_count") != len(items):
            errors.append("summary.animation_count mismatch")
        if summary.get("frame_count") != frame_count:
            errors.append("summary.frame_count mismatch")
        if summary.get("asset_count") != len(asset_ids):
            errors.append("summary.asset_count mismatch")
        if summary.get("roles") != dict(sorted(roles.items())):
            errors.append("summary.roles mismatch")
    scan_forbidden(atlas, "", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MediaAtlasManifest v0.1.")
    parser.add_argument("atlas", help="Atlas manifest path.")
    args = parser.parse_args()
    path = Path(args.atlas)
    atlas = load_json(path)
    if not isinstance(atlas, dict):
        print("INVALID MediaAtlasManifest")
        print("- root must be object")
        return 1
    errors = validate_atlas(atlas)
    if errors:
        print("INVALID MediaAtlasManifest")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {path}")
    print(f"- atlas_id: {atlas.get('atlas_id')}")
    print(f"- animations: {atlas.get('summary', {}).get('animation_count')}")
    print(f"- frames: {atlas.get('summary', {}).get('frame_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
