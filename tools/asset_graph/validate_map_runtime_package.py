#!/usr/bin/env python3
"""Validate a MapRuntimePackage v0.1 JSON file."""

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

import map_runtime_package as mrp  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.1.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a MapRuntimePackage v0.1 JSON file."
    )
    parser.add_argument("package", help="Map runtime package JSON path.")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Optional map_runtime_package schema path.",
    )
    args = parser.parse_args()

    package_path = Path(args.package)
    schema_path = Path(args.schema)

    try:
        package = load_json(package_path)
    except FileNotFoundError:
        print("INVALID MapRuntimePackage")
        print(f"- package file not found: {package_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapRuntimePackage")
        print(f"- package is not valid JSON: {exc}")
        return 1
    if not isinstance(package, dict):
        print("INVALID MapRuntimePackage")
        print("- package root must be an object")
        return 1

    schema: dict[str, Any] | None = None
    if schema_path.exists():
        loaded_schema = load_json(schema_path)
        if isinstance(loaded_schema, dict):
            schema = loaded_schema

    errors = mrp.validate_package(package, schema)
    if errors:
        print("INVALID MapRuntimePackage")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {package_path}")
    print(f"- schema_version: {package.get('schema_version')}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- build_slots: {len(package.get('build_slots', []))}")
    warnings = mrp.placement_review_warnings(package)
    print(f"- placement_geometry_warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
