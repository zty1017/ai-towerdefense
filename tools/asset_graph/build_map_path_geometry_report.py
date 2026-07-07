#!/usr/bin/env python3
"""Build review-only path geometry evidence from MapRuntimePackage files."""

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

import map_path_geometry as mpg  # noqa: E402
import map_runtime_package as mrp  # noqa: E402
import map_runtime_package_v02 as mrp_v02  # noqa: E402
from validation_common import load_json, write_json  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_path_geometry_report.v0.1.schema.json"
DEFAULT_RUNTIME_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.1.schema.json"
DEFAULT_RUNTIME_V02_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.2.schema.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_path_geometry_report.v0.1.json"
DEFAULT_PACKAGE_GLOBS = [
    "examples/map_runtime_packages/*.json",
    "examples/map_runtime_packages_v02/*.json",
]


def resolve(path: str) -> Path:
    result = Path(path)
    return result if result.is_absolute() else ROOT / result


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_schema(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    loaded = load_json(path)
    return loaded if isinstance(loaded, dict) else None


def default_package_paths() -> list[Path]:
    paths: list[Path] = []
    for pattern in DEFAULT_PACKAGE_GLOBS:
        paths.extend(sorted(ROOT.glob(pattern)))
    return paths


def validate_runtime_package(package: dict[str, Any]) -> list[str]:
    if package.get("schema_version") == "map_runtime_package.v0.2":
        return mrp_v02.validate_package_v02(package, load_schema(DEFAULT_RUNTIME_V02_SCHEMA))
    return mrp.validate_package(package, load_schema(DEFAULT_RUNTIME_SCHEMA))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a review-only MapPathGeometryReport from runtime packages."
    )
    parser.add_argument(
        "--runtime-package",
        action="append",
        dest="runtime_packages",
        help="Runtime package JSON path. Repeat to include multiple maps. Defaults to all examples.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Report output path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Report schema path.")
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    package_paths = (
        [resolve(path) for path in args.runtime_packages]
        if args.runtime_packages
        else default_package_paths()
    )
    if not package_paths:
        print("no runtime packages found")
        return 1

    runtime_packages: list[tuple[str, dict[str, Any]]] = []
    input_errors: list[str] = []
    for package_path in package_paths:
        try:
            package = load_json(package_path)
        except FileNotFoundError:
            input_errors.append(f"{package_path}: file not found")
            continue
        except json.JSONDecodeError as exc:
            input_errors.append(f"{package_path}: invalid JSON: {exc}")
            continue
        if not isinstance(package, dict):
            input_errors.append(f"{package_path}: package root must be an object")
            continue
        errors = validate_runtime_package(package)
        if errors:
            input_errors.extend(f"{package_path}: {error}" for error in errors)
            continue
        runtime_packages.append((rel(package_path), package))
    if input_errors:
        print("INVALID map path geometry inputs")
        for error in input_errors:
            print(f"- {error}")
        return 1

    report = mpg.build_geometry_report(
        runtime_packages,
        report_id=args.report_id,
        created_at=args.created_at,
    )
    report_errors = mpg.validate_geometry_report(report, load_schema(resolve(args.schema)))
    if report_errors:
        print("INVALID MapPathGeometryReport; not writing")
        for error in report_errors:
            print(f"- {error}")
        return 1

    output_path = resolve(args.output)
    write_json(output_path, report)
    print(f"OK: wrote {output_path}")
    print(f"- report_id: {report.get('report_id')}")
    print(f"- status: {report.get('status')}")
    print(f"- maps: {report.get('summary', {}).get('map_count')}")
    print(f"- warnings: {report.get('summary', {}).get('warning_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
