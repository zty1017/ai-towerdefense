#!/usr/bin/env python3
"""Build a ProceduralMapRenderPlan and semantic visual report.

The builder consumes a MapRuntimePackage and a MapStylePack. It does not read
.env and does not call AI or media providers.
"""

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
import map_runtime_package_v02 as mrp_v02  # noqa: E402
import procedural_map_render_plan as pmrp  # noqa: E402
from validation_common import load_json, write_json  # noqa: E402


DEFAULT_RUNTIME_PACKAGE = ROOT / "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"
DEFAULT_STYLE_PACK = ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"
DEFAULT_RUNTIME_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.1.schema.json"
DEFAULT_RUNTIME_V02_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.2.schema.json"
DEFAULT_STYLE_SCHEMA = ROOT / "shared/schemas/map_style_pack.v0.1.schema.json"
DEFAULT_PLAN_SCHEMA = ROOT / "shared/schemas/procedural_map_render_plan.v0.1.schema.json"
DEFAULT_REPORT_SCHEMA = ROOT / "shared/schemas/semantic_visual_consistency_report.v0.1.schema.json"


def as_repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _resolve(path: str) -> Path:
    result = Path(path)
    return result if result.is_absolute() else ROOT / result


def _load_schema(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    loaded = load_json(path)
    return loaded if isinstance(loaded, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a ProceduralMapRenderPlan and semantic visual report."
    )
    parser.add_argument("--runtime-package", default=str(DEFAULT_RUNTIME_PACKAGE))
    parser.add_argument("--style-pack", default=str(DEFAULT_STYLE_PACK))
    parser.add_argument("--output", required=True, help="Render plan output path.")
    parser.add_argument(
        "--report-output",
        required=True,
        help="Semantic visual consistency report output path.",
    )
    parser.add_argument("--runtime-schema", default=str(DEFAULT_RUNTIME_SCHEMA))
    parser.add_argument("--style-schema", default=str(DEFAULT_STYLE_SCHEMA))
    parser.add_argument("--plan-schema", default=str(DEFAULT_PLAN_SCHEMA))
    parser.add_argument("--report-schema", default=str(DEFAULT_REPORT_SCHEMA))
    parser.add_argument("--plan-id", default=None)
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--created-at", default=None)
    parser.add_argument("--canvas-width", type=int, default=1280)
    parser.add_argument("--canvas-height", type=int, default=720)
    args = parser.parse_args()

    runtime_path = _resolve(args.runtime_package)
    style_path = _resolve(args.style_pack)
    output_path = _resolve(args.output)
    report_path = _resolve(args.report_output)

    try:
        runtime_package = load_json(runtime_path)
        style_pack = load_json(style_path)
    except FileNotFoundError as exc:
        print(f"input file not found: {exc.filename}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"input file is not valid JSON: {exc}")
        return 1
    if not isinstance(runtime_package, dict) or not isinstance(style_pack, dict):
        print("runtime package and style pack roots must be objects")
        return 1

    runtime_schema_path = _resolve(args.runtime_schema)
    if (
        runtime_package.get("schema_version") == "map_runtime_package.v0.2"
        and runtime_schema_path.resolve() == DEFAULT_RUNTIME_SCHEMA.resolve()
    ):
        runtime_schema_path = DEFAULT_RUNTIME_V02_SCHEMA
    if runtime_package.get("schema_version") == "map_runtime_package.v0.2":
        runtime_errors = mrp_v02.validate_package_v02(
            runtime_package, _load_schema(runtime_schema_path)
        )
    else:
        runtime_errors = mrp.validate_package(
            runtime_package, _load_schema(runtime_schema_path)
        )
    style_errors = pmrp.validate_style_pack(style_pack, _load_schema(_resolve(args.style_schema)))
    if runtime_errors or style_errors:
        print("INVALID inputs; not writing render plan")
        for error in runtime_errors:
            print(f"- runtime: {error}")
        for error in style_errors:
            print(f"- style: {error}")
        return 1

    plan = pmrp.build_render_plan(
        runtime_package,
        style_pack,
        map_runtime_package_path=as_repo_relative(runtime_path),
        map_style_pack_path=as_repo_relative(style_path),
        plan_id=args.plan_id,
        created_at=args.created_at,
        canvas_width=args.canvas_width,
        canvas_height=args.canvas_height,
    )
    report = pmrp.build_consistency_report(
        runtime_package,
        style_pack,
        plan,
        map_runtime_package_path=as_repo_relative(runtime_path),
        map_style_pack_path=as_repo_relative(style_path),
        procedural_map_render_plan_path=as_repo_relative(output_path),
        report_id=args.report_id,
        created_at=args.created_at,
    )

    plan_errors = pmrp.validate_render_plan(plan, _load_schema(_resolve(args.plan_schema)))
    report_errors = pmrp.validate_consistency_report(
        report,
        _load_schema(_resolve(args.report_schema)),
        render_plan=plan,
        runtime_package=runtime_package,
    )
    if plan_errors or report_errors:
        print("INVALID builder output; not writing")
        for error in plan_errors:
            print(f"- plan: {error}")
        for error in report_errors:
            print(f"- report: {error}")
        return 1

    write_json(output_path, plan)
    write_json(report_path, report)
    print(f"OK: wrote {output_path}")
    print(f"OK: wrote {report_path}")
    print(f"- plan_id: {plan.get('plan_id')}")
    print(f"- semantic_visual_status: {report.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
