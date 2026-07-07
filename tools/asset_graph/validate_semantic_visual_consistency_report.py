#!/usr/bin/env python3
"""Validate a SemanticVisualConsistencyReport v0.1 JSON file."""

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
from validation_common import load_json  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/semantic_visual_consistency_report.v0.1.schema.json"


def _optional_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    loaded = load_json(Path(path))
    return loaded if isinstance(loaded, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a SemanticVisualConsistencyReport v0.1 JSON file."
    )
    parser.add_argument("report", help="Semantic visual consistency report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional schema path.")
    parser.add_argument("--render-plan", default=None, help="Optional render plan to cross-check.")
    parser.add_argument("--runtime-package", default=None, help="Optional runtime package to cross-check.")
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID SemanticVisualConsistencyReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID SemanticVisualConsistencyReport")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID SemanticVisualConsistencyReport")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    render_plan = _optional_json(args.render_plan)
    runtime_package = _optional_json(args.runtime_package)
    errors = pmrp.validate_consistency_report(
        report,
        schema,
        render_plan=render_plan,
        runtime_package=runtime_package,
    )
    if errors:
        print("INVALID SemanticVisualConsistencyReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {report_path}")
    print(f"- report_id: {report.get('report_id')}")
    print(f"- status: {report.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
