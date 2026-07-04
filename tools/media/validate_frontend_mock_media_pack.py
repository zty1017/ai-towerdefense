#!/usr/bin/env python3
"""Validate the frontend mock media manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_KEYS = {
    "provider",
    "provider_profile",
    "model",
    "raw_prompt",
    "full_prompt",
    "temporary_url",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                errors.append(f"forbidden key in frontend media manifest: {child_path}")
            scan_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, f"{path}[{index}]", errors)


def validate(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "frontend_media_manifest.v0.1":
        errors.append("schema_version must be frontend_media_manifest.v0.1")
    for key in ("media_pack_id", "source_pack_id", "public_url_prefix", "media_layer", "items", "summary"):
        if key not in manifest:
            errors.append(f"missing top-level key: {key}")
    if manifest.get("media_layer") != "published_media":
        errors.append("media_layer must be published_media")

    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items must be a non-empty array")
        items = []

    roles_by_asset: dict[str, set[str]] = {}
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be object")
            continue
        stable_id = item.get("stable_internal_id")
        if not isinstance(stable_id, str) or not stable_id:
            errors.append(f"items[{index}].stable_internal_id must be non-empty string")
        elif stable_id in seen_ids:
            errors.append(f"duplicate stable_internal_id: {stable_id}")
        else:
            seen_ids.add(stable_id)
        asset_id = item.get("asset_id")
        role = item.get("media_role")
        if not isinstance(asset_id, str) or not asset_id:
            errors.append(f"items[{index}].asset_id must be non-empty string")
        if not isinstance(role, str) or not role:
            errors.append(f"items[{index}].media_role must be non-empty string")
        if isinstance(asset_id, str) and isinstance(role, str):
            roles_by_asset.setdefault(asset_id, set()).add(role)
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("/assets/"):
            errors.append(f"items[{index}].url must start with /assets/")
        local_path = item.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            errors.append(f"items[{index}].local_path must be non-empty string")
        else:
            path = ROOT / local_path
            if not path.exists():
                errors.append(f"items[{index}].local_path does not exist: {local_path}")
        for dim_key in ("width", "height"):
            dim = item.get(dim_key)
            if not isinstance(dim, int) or dim <= 0:
                errors.append(f"items[{index}].{dim_key} must be positive integer")
        sha = item.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            errors.append(f"items[{index}].sha256 must be 64 hex chars")

    for asset_id, roles in sorted(roles_by_asset.items()):
        if "icon" not in roles:
            errors.append(f"asset {asset_id} missing icon media")

    summary = manifest.get("summary")
    if isinstance(summary, dict):
        if summary.get("media_count") != len(items):
            errors.append("summary.media_count mismatch")
        if summary.get("asset_count") != len(roles_by_asset):
            errors.append("summary.asset_count mismatch")

    scan_forbidden(manifest, "", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    data = load_json(Path(args.manifest))
    if not isinstance(data, dict):
        print("frontend media manifest root must be object")
        return 1
    errors = validate(data)
    if errors:
        print("INVALID FrontendMediaManifest")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK FrontendMediaManifest")
    print(f"- manifest: {args.manifest}")
    print(f"- assets: {data.get('summary', {}).get('asset_count')}")
    print(f"- media: {data.get('summary', {}).get('media_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
