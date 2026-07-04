#!/usr/bin/env python3
"""Build a MapRuntimePackage v0.2 preview package from a battle config."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import map_runtime_package_v02 as mrp_v02  # noqa: E402


DEFAULT_BATTLE_CONFIG = ROOT / "game_data/demo/first_battle_config.json"
DEFAULT_VISUAL_MANIFEST = (
    ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
)
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.2.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a MapRuntimePackage v0.2 preview package from a battle config."
    )
    parser.add_argument(
        "--battle-config",
        default=str(DEFAULT_BATTLE_CONFIG),
        help="Battle config JSON path.",
    )
    parser.add_argument(
        "--visual-reference-manifest",
        default=str(DEFAULT_VISUAL_MANIFEST),
        help="Optional map visual reference manifest path.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Optional map_runtime_package v0.2 schema path.",
    )
    parser.add_argument("--package-id", default=None, help="Override package_id.")
    parser.add_argument("--created-at", default=None, help="Override created_at.")
    args = parser.parse_args()

    battle_path = resolve_repo_path(args.battle_config)
    visual_path = resolve_repo_path(args.visual_reference_manifest)
    schema_path = resolve_repo_path(args.schema)
    output_path = resolve_repo_path(args.output)

    try:
        battle_config = load_json(battle_path)
    except FileNotFoundError:
        print(f"battle config file not found: {battle_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"battle config is not valid JSON: {exc}")
        return 1
    if not isinstance(battle_config, dict):
        print("battle config root must be an object")
        return 1

    visual_manifest: dict[str, Any] | None = None
    visual_manifest_ref: str | None = None
    if visual_path.exists():
        try:
            loaded_manifest = load_json(visual_path)
        except json.JSONDecodeError as exc:
            print(f"visual reference manifest is not valid JSON: {exc}")
            return 1
        if isinstance(loaded_manifest, dict):
            visual_manifest = loaded_manifest
            visual_manifest_ref = as_repo_relative(visual_path)

    package = mrp_v02.build_map_runtime_package_v02(
        battle_config,
        battle_config_path=as_repo_relative(battle_path),
        visual_reference_manifest=visual_manifest,
        visual_reference_manifest_path=visual_manifest_ref,
        package_id=args.package_id,
        created_at=args.created_at,
    )

    schema: dict[str, Any] | None = None
    if schema_path.exists():
        loaded_schema = load_json(schema_path)
        if isinstance(loaded_schema, dict):
            schema = loaded_schema
    errors = mrp_v02.validate_package_v02(package, schema)
    if errors:
        print("INVALID MapRuntimePackage v0.2 (builder produced invalid package; not writing)")
        for error in errors:
            print(f"- {error}")
        return 1

    write_json(output_path, package)
    print(f"OK: wrote {output_path}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- resource_nodes: {len(package.get('resource_nodes', []))}")
    print(f"- hazard_zones: {len(package.get('hazard_zones', []))}")
    print(f"- defense_anchors: {len(package.get('defense_anchors', []))}")
    print(f"- blocked_areas: {len(package.get('blocked_areas', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
