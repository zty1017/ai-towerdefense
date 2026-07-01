#!/usr/bin/env python3
"""Validate the developer-compiled frontend battle runtime art kit."""

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
REQUIRED_ENEMIES = {"shadow_tide_runner", "shadow_tide_shade", "shadow_tide_cluster"}
REQUIRED_EFFECTS = {
    "lantern_projectile",
    "warm_hit_burst",
    "slow_status_ring",
    "enemy_death_puff",
    "leak_marker",
}
ALLOWED_EFFECT_PRIMITIVES = {
    "ring_pulse",
    "beam",
    "chain_arc",
    "sprite_flash",
    "particle_burst",
    "aura_field",
    "screen_shake",
    "floating_text",
}


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


def validate_kit(kit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if kit.get("schema_version") != "frontend_battle_mock_art_kit.v0.1":
        errors.append("kit schema_version must be frontend_battle_mock_art_kit.v0.1")
    art_assets = kit.get("art_assets")
    if not isinstance(art_assets, list) or not art_assets:
        errors.append("kit.art_assets must be non-empty")
        art_assets = []
    seen: set[str] = set()
    enemies: set[str] = set()
    for index, asset in enumerate(art_assets):
        if not isinstance(asset, dict):
            errors.append(f"art_assets[{index}] must be object")
            continue
        asset_id = asset.get("stable_internal_id")
        if not isinstance(asset_id, str) or not asset_id:
            errors.append(f"art_assets[{index}].stable_internal_id must be non-empty string")
        elif asset_id in seen:
            errors.append(f"duplicate art asset id: {asset_id}")
        else:
            seen.add(asset_id)
        if asset.get("asset_kind") == "enemy_archetype" and isinstance(asset.get("source_game_id"), str):
            enemies.add(asset["source_game_id"])
        roles = asset.get("media_roles")
        if not isinstance(roles, list) or "icon" not in roles:
            errors.append(f"art asset {asset_id} must include icon media role")
    missing_enemies = sorted(REQUIRED_ENEMIES - enemies)
    if missing_enemies:
        errors.append(f"missing required enemy art: {', '.join(missing_enemies)}")
    effects = set()
    for index, effect in enumerate(kit.get("procedural_effects", [])):
        if not isinstance(effect, dict):
            errors.append(f"procedural_effects[{index}] must be object")
            continue
        effects.add(effect.get("effect_id"))
        primitive = effect.get("primitive")
        if primitive not in ALLOWED_EFFECT_PRIMITIVES:
            errors.append(
                f"procedural effect {effect.get('effect_id')} uses unsupported primitive: {primitive}"
            )
    missing_effects = sorted(REQUIRED_EFFECTS - effects)
    if missing_effects:
        errors.append(f"missing required procedural effects: {', '.join(missing_effects)}")
    scan_forbidden(kit, "", errors)
    return errors


def validate_manifest(manifest: dict[str, Any], kit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != "frontend_runtime_art_media_manifest.v0.1":
        errors.append("manifest schema_version must be frontend_runtime_art_media_manifest.v0.1")
    if manifest.get("source_pack_id") != kit.get("kit_id"):
        errors.append("manifest.source_pack_id must match kit.kit_id")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        errors.append("manifest.items must be non-empty")
        items = []
    roles_by_asset: dict[str, set[str]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be object")
            continue
        asset_id = item.get("asset_id")
        role = item.get("media_role")
        if isinstance(asset_id, str) and isinstance(role, str):
            roles_by_asset.setdefault(asset_id, set()).add(role)
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("/assets/frontend_runtime_mock/"):
            errors.append(f"items[{index}].url must start with /assets/frontend_runtime_mock/")
        local_path = item.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            errors.append(f"items[{index}].local_path must be non-empty string")
        elif not (ROOT / local_path).exists():
            errors.append(f"items[{index}].local_path does not exist: {local_path}")
        for dim_key in ("width", "height"):
            dim = item.get(dim_key)
            if not isinstance(dim, int) or dim <= 0:
                errors.append(f"items[{index}].{dim_key} must be positive integer")
        sha = item.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            errors.append(f"items[{index}].sha256 must be 64 chars")
    for asset in kit.get("art_assets", []):
        if not isinstance(asset, dict):
            continue
        asset_id = asset.get("stable_internal_id")
        expected_roles = set(asset.get("media_roles", []))
        actual_roles = roles_by_asset.get(str(asset_id), set())
        missing = sorted(expected_roles - actual_roles)
        if missing:
            errors.append(f"asset {asset_id} missing media roles: {', '.join(missing)}")
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
    parser.add_argument("--kit", default=str(ROOT / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json"))
    parser.add_argument(
        "--manifest",
        default=str(ROOT / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json"),
    )
    parser.add_argument(
        "--allow-missing-manifest",
        action="store_true",
        help="Validate only the art kit when media has not been generated yet.",
    )
    args = parser.parse_args()
    kit = load_json(Path(args.kit))
    if not isinstance(kit, dict):
        print("kit root must be object")
        return 1
    errors = validate_kit(kit)
    manifest_path = Path(args.manifest)
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        if not isinstance(manifest, dict):
            errors.append("manifest root must be object")
        else:
            errors.extend(validate_manifest(manifest, kit))
    elif not args.allow_missing_manifest:
        errors.append(f"manifest missing: {manifest_path}")
    if errors:
        print("INVALID FrontendRuntimeArtPack")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK FrontendRuntimeArtPack")
    print(f"- kit: {args.kit}")
    if manifest_path.exists():
        print(f"- manifest: {args.manifest}")
    else:
        print("- manifest: missing but allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
