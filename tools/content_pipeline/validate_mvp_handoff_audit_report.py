#!/usr/bin/env python3
"""Validate MVP Handoff Audit Report v0.1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, scan_forbidden_terms, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/mvp_handoff_audit_report.v0.1.schema.json"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_json_schema(report, SCHEMA_PATH))
    scan_forbidden_terms(report, "", errors, context="MvpHandoffAuditReport")

    command_results = as_list(report.get("command_results"))
    failed_commands = [
        command.get("name")
        for command in command_results
        if isinstance(command, dict) and command.get("status") != "passed"
    ]
    failed_checks = [
        check.get("check_id")
        for check in as_list(report.get("coverage_checks"))
        if isinstance(check, dict) and check.get("status") == "failed"
    ]
    if report.get("overall_status") == "passed" and failed_commands:
        errors.append(f"overall_status is passed but commands failed: {failed_commands}")
    if report.get("overall_status") == "passed" and failed_checks:
        errors.append(f"overall_status is passed but coverage checks failed: {failed_checks}")

    artifact_summary = as_obj(report.get("artifact_summary"))
    frontend = as_obj(artifact_summary.get("frontend_mock_pack"))
    if frontend:
        if frontend.get("asset_count") != frontend.get("playable_count"):
            errors.append("frontend mock pack must expose only playable assets")
        if int(frontend.get("stage_count") or 0) < 3:
            errors.append("frontend mock pack must include at least 3 staged outlines")
    multistage = as_obj(artifact_summary.get("multistage_stage_candidate_pack"))
    if multistage and int(multistage.get("stage_count") or 0) < 3:
        errors.append("multistage stage candidate pack must include at least 3 stages")
    catalog = as_obj(artifact_summary.get("compilable_object_catalog"))
    if catalog and int(catalog.get("total_objects") or 0) < 100:
        errors.append("compilable object catalog should contain at least 100 objects for current MVP evidence")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MVP Handoff Audit Report v0.1.")
    parser.add_argument("report")
    args = parser.parse_args()

    try:
        report = load_json(Path(args.report))
    except FileNotFoundError:
        print("INVALID MvpHandoffAuditReport")
        print(f"- report file not found: {args.report}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MvpHandoffAuditReport")
        print(f"- report is not valid JSON: {exc}")
        return 1

    if not isinstance(report, dict):
        print("INVALID MvpHandoffAuditReport")
        print("- report root must be an object")
        return 1

    errors = validate_report(report)
    if errors:
        print("INVALID MvpHandoffAuditReport")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK MvpHandoffAuditReport")
    print(f"- report: {args.report}")
    print(f"- commands: {len(report.get('command_results', []))}")
    print(f"- coverage_checks: {len(report.get('coverage_checks', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
