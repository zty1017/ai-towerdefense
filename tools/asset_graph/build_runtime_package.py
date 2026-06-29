#!/usr/bin/env python3
"""Build a RuntimePackage v0.1 from a locked manifest + battle config.

Usage:
    python3 tools/asset_graph/build_runtime_package.py \
        --locked-manifest examples/locked_manifests/mvp_light_snare.locked_manifest.json \
        --battle-config game_data/demo/first_battle_config.json \
        --out /tmp/ai_td_runtime_package/mvp_demo.runtime_package.json

The builder:
- Reads a locked manifest + battle config.
- Derives a RuntimePackage v0.1 (see shared/schemas/runtime_package.v0.1.schema.json).
- Filters out internal fields (template_id, worldbook_id, session_instance_id,
  source_layer, raw_media, processed_media, provider/trace fields).
- sample_delivery is extracted from battle_config.sample_asset
  (delivery_delay_ms + delivery_progress_messages only).
- battle_context is extracted from battle_config (grid/paths/core_target/
  optional_targets).
- assets are extracted from locked_manifest.locked_assets, keeping only
  display/gameplay_ref/media_refs/visual_recipes/battle_availability.
- After building, runs the full validator on the result. If validation fails,
  the package is NOT written and the CLI exits 1.
- Writes the validated package to --out.

The builder never reads .env and never prints API keys or secrets.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_package as rp  # noqa: E402

DEFAULT_SCHEMA = ROOT / "shared/schemas/runtime_package.v0.1.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_package_id(manifest: dict[str, Any]) -> str:
    """Derive a deterministic-enough package_id from the manifest id + a token.

    Uses the manifest's manifest_id as a prefix so the package is traceable to
    its source without embedding the full manifest. A short random suffix
    keeps packages unique across builds.
    """
    manifest_id = manifest.get("manifest_id", "manifest_unknown")
    # Strip a leading "manifest_" prefix to avoid double-naming.
    base = manifest_id
    if base.startswith("manifest_"):
        base = base[len("manifest_"):]
    return f"package_{base}_{secrets.token_hex(4)}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a RuntimePackage v0.1 from a locked manifest + battle config."
    )
    parser.add_argument(
        "--locked-manifest",
        required=True,
        help="Path to a locked_manifest.v0.1 JSON file.",
    )
    parser.add_argument(
        "--battle-config",
        required=True,
        help="Path to a battle config JSON file (e.g. first_battle_config.json).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the resulting runtime package JSON.",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Path to the runtime_package v0.1 JSON Schema (optional).",
    )
    parser.add_argument(
        "--package-id",
        default=None,
        help="Override the generated package_id (otherwise derived from manifest).",
    )
    parser.add_argument(
        "--created-at",
        default=None,
        help="Override the created_at timestamp (otherwise current UTC).",
    )
    args = parser.parse_args()

    manifest_path = Path(args.locked_manifest)
    battle_path = Path(args.battle_config)
    out_path = Path(args.out)
    schema_path = Path(args.schema)

    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print(f"locked manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"locked manifest is not valid JSON: {exc}")
        return 1

    try:
        battle_config = load_json(battle_path)
    except FileNotFoundError:
        print(f"battle config file not found: {battle_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"battle config is not valid JSON: {exc}")
        return 1

    if not isinstance(manifest, dict):
        print("locked manifest root must be an object")
        return 1
    if not isinstance(battle_config, dict):
        print("battle config root must be an object")
        return 1

    package_id = args.package_id or _derive_package_id(manifest)
    created_at = args.created_at or _now_iso()

    package = rp.build_runtime_package(
        manifest,
        battle_config,
        package_id=package_id,
        created_at=created_at,
    )

    # Validate before writing. If validation fails, do not write the file.
    schema: dict[str, Any] | None = None
    if schema_path.exists():
        try:
            loaded = load_json(schema_path)
            if isinstance(loaded, dict):
                schema = loaded
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    errors = rp.validate_package(package, schema)
    if errors:
        print("INVALID RuntimePackage (builder produced invalid package; not writing)")
        for error in errors:
            print(f"- {error}")
        return 1

    write_json(out_path, package)
    print(f"OK: wrote {out_path}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- assets: {len(package.get('assets', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
