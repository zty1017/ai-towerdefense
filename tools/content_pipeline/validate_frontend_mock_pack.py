#!/usr/bin/env python3
"""Validate a frontend mock pack without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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
REQUIRED_ASSET_TYPES = {
    "tower_blueprint",
    "support_item",
    "temporary_mod",
    "intel_asset",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                errors.append(f"forbidden key in frontend pack: {child_path}")
            scan_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, f"{path}[{index}]", errors)


def validate(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if pack.get("schema_version") != "frontend_mock_pack.v0.1":
        errors.append("schema_version must be frontend_mock_pack.v0.1")
    for key in ("pack_id", "worldbook_id", "compiler_summary", "frontend_contract", "world", "map", "npcs", "materials", "story", "assets"):
        if key not in pack:
            errors.append(f"missing top-level key: {key}")

    assets = pack.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty array")
        assets = []
    asset_types = {
        str(asset.get("asset_type"))
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_type")
    }
    missing_types = sorted(REQUIRED_ASSET_TYPES - asset_types)
    if missing_types:
        errors.append(f"missing required asset types: {', '.join(missing_types)}")

    playable = 0
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f"assets[{index}] must be object")
            continue
        promotion = asset.get("promotion")
        if not isinstance(promotion, dict):
            errors.append(f"assets[{index}].promotion must be object")
            continue
        if promotion.get("playable") is True:
            playable += 1
        state = promotion.get("promotion_state")
        if state not in {"runtime_ready", "fallback_ready"}:
            errors.append(f"assets[{index}] is not deliverable: promotion_state={state!r}")
        if not asset.get("visual_recipes"):
            errors.append(f"assets[{index}] missing visual_recipes")
        media_refs = asset.get("media_refs")
        if not isinstance(media_refs, dict) or not media_refs.get("icon_token"):
            errors.append(f"assets[{index}] missing fallback icon_token")

    summary = pack.get("compiler_summary")
    if isinstance(summary, dict):
        if summary.get("asset_count") != len(assets):
            errors.append("compiler_summary.asset_count mismatch")
        if summary.get("playable_count") != playable:
            errors.append("compiler_summary.playable_count mismatch")
    if playable != len(assets):
        errors.append("all frontend mock assets must be playable")

    if not pack.get("npcs"):
        errors.append("npcs must not be empty")
    if not pack.get("materials"):
        errors.append("materials must not be empty")
    story = pack.get("story")
    if not isinstance(story, dict) or not story.get("questline"):
        errors.append("story.questline must not be empty")

    scan_forbidden(pack, "", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack")
    args = parser.parse_args()
    path = Path(args.pack)
    data = load_json(path)
    if not isinstance(data, dict):
        print("frontend mock pack root must be object")
        return 1
    errors = validate(data)
    if errors:
        print("INVALID FrontendMockPack")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK FrontendMockPack")
    print(f"- pack: {path}")
    print(f"- assets: {len(data.get('assets', []))}")
    print(f"- npcs: {len(data.get('npcs', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
