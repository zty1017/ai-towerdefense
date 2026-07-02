#!/usr/bin/env python3
"""Validate CoreArtifactAlignmentReport v0.1."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/core_artifact_alignment_report.v0.1.schema.json"
CORE_ARTIFACT_KEYS = {
    "context_package",
    "fact_entry",
    "compiled_game_object_package",
    "world_delta",
    "world_delta_transaction",
}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def repo_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _validate_summary(report: dict[str, Any], errors: list[str]) -> None:
    targets = [target for target in as_list(report.get("target_reports")) if isinstance(target, dict)]
    summary = as_obj(report.get("summary"))
    status_counts = Counter(str(target.get("alignment_state")) for target in targets)
    expected_counts = dict(sorted(status_counts.items()))
    if summary.get("target_count") != len(targets):
        errors.append("summary.target_count must match target_reports length")
    if summary.get("status_counts") != expected_counts:
        errors.append("summary.status_counts must match target alignment_state counts")

    count_fields = {
        "native_snapshot_ready_count": status_counts.get("native_snapshot_ready", 0),
        "refs_only_count": status_counts.get("refs_only", 0),
        "missing_core_alignment_count": status_counts.get("missing_core_alignment", 0),
        "validation_failed_count": status_counts.get("validation_failed", 0),
        "review_only_not_applicable_count": status_counts.get(
            "review_only_not_applicable", 0
        ),
    }
    for field, expected in count_fields.items():
        if summary.get(field) != expected:
            errors.append(f"summary.{field} must be {expected}")

    if status_counts.get("validation_failed", 0):
        expected_status = "failed"
    elif status_counts.get("missing_core_alignment", 0) or status_counts.get("refs_only", 0):
        expected_status = "needs_migration"
    else:
        expected_status = "passed"
    if summary.get("overall_status") != expected_status:
        errors.append(f"summary.overall_status must be {expected_status!r}")


def _validate_targets(report: dict[str, Any], errors: list[str]) -> None:
    seen: set[str] = set()
    for index, target in enumerate(as_list(report.get("target_reports"))):
        if not isinstance(target, dict):
            continue
        label = f"target_reports[{index}]"
        target_id = target.get("target_id")
        if isinstance(target_id, str):
            if target_id in seen:
                errors.append(f"duplicate target_id: {target_id}")
            seen.add(target_id)
        source_path = target.get("source_path")
        if isinstance(source_path, str) and source_path and not repo_path(source_path).exists():
            errors.append(f"{label}.source_path does not exist: {source_path}")
        if target.get("runtime_activation_allowed") is not False:
            errors.append(f"{label}.runtime_activation_allowed must remain false")
        if target.get("world_mutation_allowed") is not False:
            errors.append(f"{label}.world_mutation_allowed must remain false")

        present = set(as_list(target.get("present_artifacts")))
        refs = as_obj(target.get("refs"))
        for key, ref in refs.items():
            if key in CORE_ARTIFACT_KEYS and key not in present:
                errors.append(f"{label}.refs.{key} must be listed in present_artifacts")
            if isinstance(ref, str) and ref and not repo_path(ref).exists():
                errors.append(f"{label}.refs.{key} references missing file: {ref}")

        validation_failed = False
        for result_index, result in enumerate(as_list(target.get("validation_results"))):
            if not isinstance(result, dict):
                continue
            result_label = f"{label}.validation_results[{result_index}]"
            result_errors = as_list(result.get("errors"))
            if isinstance(result.get("error_count"), int) and result.get("error_count") < len(
                result_errors
            ):
                errors.append(f"{result_label}.error_count must be >= summarized errors length")
            if result.get("status") == "passed" and result.get("error_count") != 0:
                errors.append(f"{result_label} passed result must have error_count 0")
            if result.get("status") == "failed":
                validation_failed = True
                if result.get("error_count") == 0:
                    errors.append(f"{result_label} failed result must include at least one error")
        if target.get("alignment_state") == "native_snapshot_ready" and validation_failed:
            errors.append(f"{label} cannot be native_snapshot_ready with failed validation")
        if target.get("alignment_state") == "validation_failed" and not validation_failed:
            errors.append(f"{label} validation_failed target must include a failed validation")
        if target.get("alignment_state") == "missing_core_alignment" and present:
            errors.append(f"{label} missing_core_alignment target should not list present core artifacts")


def _validate_migration_tasks(report: dict[str, Any], errors: list[str]) -> None:
    target_ids = {
        str(target.get("target_id"))
        for target in as_list(report.get("target_reports"))
        if isinstance(target, dict)
    }
    task_ids: set[str] = set()
    for index, task in enumerate(as_list(report.get("migration_tasks"))):
        if not isinstance(task, dict):
            continue
        label = f"migration_tasks[{index}]"
        task_id = task.get("task_id")
        if isinstance(task_id, str):
            if task_id in task_ids:
                errors.append(f"duplicate migration task_id: {task_id}")
            task_ids.add(task_id)
        source_target_id = task.get("source_target_id")
        if source_target_id not in target_ids:
            errors.append(f"{label}.source_target_id does not match a target_id")


def validate_report(report: dict[str, Any], source_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report root must be an object"]
    errors.extend(validate_json_schema(report, SCHEMA_PATH))
    authority = as_obj(report.get("authority"))
    if authority.get("report_only") is not True:
        errors.append("authority.report_only must be true")
    if authority.get("runtime_activation_allowed") is not False:
        errors.append("authority.runtime_activation_allowed must be false")
    if authority.get("world_mutation_allowed") is not False:
        errors.append("authority.world_mutation_allowed must be false")
    _validate_summary(report, errors)
    _validate_targets(report, errors)
    _validate_migration_tasks(report, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate CoreArtifactAlignmentReport v0.1 JSON files."
    )
    parser.add_argument("reports", nargs="+", help="Report JSON path(s).")
    args = parser.parse_args()

    failed = False
    for raw_path in args.reports:
        path = Path(raw_path)
        try:
            report = load_json(path)
        except FileNotFoundError:
            print(f"INVALID {raw_path}")
            print("- file not found")
            failed = True
            continue
        except json.JSONDecodeError as exc:
            print(f"INVALID {raw_path}")
            print(f"- not valid JSON: {exc}")
            failed = True
            continue
        errors = validate_report(report, source_path=path)
        if errors:
            print(f"INVALID {raw_path}")
            for error in errors:
                print(f"- {error}")
            failed = True
            continue
        summary = as_obj(report.get("summary"))
        print(f"CoreArtifactAlignmentReport validation passed: {raw_path}")
        print(f"- overall_status: {summary.get('overall_status')}")
        print(f"- target_count: {summary.get('target_count')}")
        print(f"- migration_tasks: {len(as_list(report.get('migration_tasks')))}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
