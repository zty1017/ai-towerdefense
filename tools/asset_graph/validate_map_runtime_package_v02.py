#!/usr/bin/env python3
"""Validate a MapRuntimePackage v0.2 preview JSON file."""

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


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.2.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a MapRuntimePackage v0.2 preview JSON file."
    )
    parser.add_argument("package", help="Map runtime package v0.2 JSON path.")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Optional map_runtime_package v0.2 schema path.",
    )
    args = parser.parse_args()

    package_path = Path(args.package)
    schema_path = Path(args.schema)

    try:
        package = load_json(package_path)
    except FileNotFoundError:
        print("INVALID MapRuntimePackage v0.2")
        print(f"- package file not found: {package_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapRuntimePackage v0.2")
        print(f"- package is not valid JSON: {exc}")
        return 1
    if not isinstance(package, dict):
        print("INVALID MapRuntimePackage v0.2")
        print("- package root must be an object")
        return 1

    schema: dict[str, Any] | None = None
    if schema_path.exists():
        loaded_schema = load_json(schema_path)
        if isinstance(loaded_schema, dict):
            schema = loaded_schema

    errors = mrp_v02.validate_package_v02(package, schema)
    if errors:
        print("INVALID MapRuntimePackage v0.2")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {package_path}")
    print(f"- schema_version: {package.get('schema_version')}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- resource_nodes: {len(package.get('resource_nodes', []))}")
    print(f"- hazard_zones: {len(package.get('hazard_zones', []))}")
    print(f"- defense_anchors: {len(package.get('defense_anchors', []))}")
    print(f"- blocked_areas: {len(package.get('blocked_areas', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
