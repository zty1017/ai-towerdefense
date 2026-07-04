#!/usr/bin/env python3
"""Validate a ProceduralMapRenderPlan v0.1 JSON file."""

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

import procedural_map_render_plan as pmrp  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/procedural_map_render_plan.v0.1.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a ProceduralMapRenderPlan v0.1 JSON file."
    )
    parser.add_argument("package", help="Procedural map render plan JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional schema path.")
    args = parser.parse_args()

    package_path = Path(args.package)
    schema_path = Path(args.schema)
    try:
        package = load_json(package_path)
    except FileNotFoundError:
        print("INVALID ProceduralMapRenderPlan")
        print(f"- package file not found: {package_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID ProceduralMapRenderPlan")
        print(f"- package is not valid JSON: {exc}")
        return 1
    if not isinstance(package, dict):
        print("INVALID ProceduralMapRenderPlan")
        print("- package root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = pmrp.validate_render_plan(package, schema)
    if errors:
        print("INVALID ProceduralMapRenderPlan")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {package_path}")
    print(f"- plan_id: {package.get('plan_id')}")
    print(f"- layers: {len(package.get('layers', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
