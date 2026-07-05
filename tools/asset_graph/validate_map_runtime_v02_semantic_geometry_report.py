#!/usr/bin/env python3
"""Validate a MapRuntimeV02SemanticGeometryReport v0.1 JSON file."""

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

import build_map_runtime_v02_semantic_geometry_report as semantic_geometry  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_runtime_v02_semantic_geometry_report.v0.1.schema.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a MapRuntimeV02SemanticGeometryReport v0.1 JSON file."
    )
    parser.add_argument("report", help="Semantic geometry report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional schema path.")
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID MapRuntimeV02SemanticGeometryReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapRuntimeV02SemanticGeometryReport")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID MapRuntimeV02SemanticGeometryReport")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = semantic_geometry.validate_report(report, schema)
    if errors:
        print("INVALID MapRuntimeV02SemanticGeometryReport")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = report.get("summary", {})
    print(f"OK: {report_path}")
    print(f"- report_id: {report.get('report_id')}")
    print(f"- status: {report.get('status')}")
    print(f"- maps: {summary.get('map_count')}")
    print(f"- errors: {summary.get('error_count')}")
    print(f"- warnings: {summary.get('warning_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
