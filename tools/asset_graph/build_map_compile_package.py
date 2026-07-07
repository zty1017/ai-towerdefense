#!/usr/bin/env python3
"""Build a MapCompilePackage v0.2 from a MapRuntimePackage and visual manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import map_compile_package as mcp  # noqa: E402
from validation_common import load_json, write_json  # noqa: E402


DEFAULT_RUNTIME_PACKAGE = ROOT / "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"
DEFAULT_VISUAL_MANIFEST = ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/map_compile_packages/mvp_first_battle.map_compile_package.json"


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a MapCompilePackage v0.2 JSON file."
    )
    parser.add_argument(
        "--runtime-package",
        default=str(DEFAULT_RUNTIME_PACKAGE),
        help="MapRuntimePackage JSON path.",
    )
    parser.add_argument(
        "--visual-manifest",
        default=str(DEFAULT_VISUAL_MANIFEST),
        help="Map visual reference manifest path.",
    )
    parser.add_argument(
        "--battle-config",
        default="game_data/demo/first_battle_config.json",
        help="Battle config path recorded in source_refs.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output MapCompilePackage path.",
    )
    parser.add_argument(
        "--created-at",
        default="2026-07-02T00:00:00Z",
        help="Deterministic created_at timestamp for fixture builds.",
    )
    args = parser.parse_args()

    runtime_path = Path(args.runtime_package)
    visual_manifest_path = Path(args.visual_manifest)
    output_path = Path(args.output)
    runtime_package = load_json(runtime_path)
    visual_manifest = load_json(visual_manifest_path)
    if not isinstance(runtime_package, dict):
        raise SystemExit("runtime package root must be an object")
    if not isinstance(visual_manifest, dict):
        raise SystemExit("visual manifest root must be an object")

    package = mcp.build_map_compile_package(
        runtime_package,
        map_runtime_package_path=rel(runtime_path),
        battle_config_path=args.battle_config,
        visual_reference_manifest=visual_manifest,
        visual_reference_manifest_path=rel(visual_manifest_path),
        created_at=args.created_at,
    )
    write_json(output_path, package)
    print(f"OK: wrote {output_path}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- quality_gates: {len(package.get('quality_gates', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
