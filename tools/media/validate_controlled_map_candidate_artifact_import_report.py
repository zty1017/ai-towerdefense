#!/usr/bin/env python3
"""Validate ControlledMapCandidateArtifactImportReport v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "controlled_map_candidate_artifact_import_report.v0.1"
ALLOWED_TARGET_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates_controlled_v1"
ALLOWED_TMP_DIR = Path("/tmp")
REQUIRED_SAFETY = {
    "provider_called": False,
    "reads_env": False,
    "runtime_published": False,
    "map_runtime_package_modified": False,
    "published_visual_layer_written": False,
    "runtime_package_activation_changed": False,
    "copies_files_only_when_copy_files_true": True,
    "source_paths_limited_to_repo_or_tmp": True,
}
ALLOWED_STATUSES = {
    "awaiting_local_artifact",
    "validated_not_copied",
    "imported_pending_candidate_review",
    "invalid_import_plan_item",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_item(item: dict[str, Any], index: int, errors: list[str]) -> None:
    status = item.get("status")
    if status not in ALLOWED_STATUSES:
        errors.append(f"items[{index}].status must be one of {sorted(ALLOWED_STATUSES)}")
    node_id = item.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        errors.append(f"items[{index}].node_id must be a non-empty string")
    target_value = item.get("target_candidate_path")
    if not isinstance(target_value, str) or not target_value.strip():
        errors.append(f"items[{index}].target_candidate_path must be a non-empty string")
    else:
        target = resolve_path(target_value)
        if not is_relative_to(target, ALLOWED_TARGET_DIR):
            errors.append(f"items[{index}].target_candidate_path must be under controlled candidate dir")
        if target.name != f"{node_id}.controlled_reference_candidate.png":
            errors.append(f"items[{index}].target_candidate_path must match node controlled candidate filename")
    sidecar_value = item.get("target_sidecar_path")
    if not isinstance(sidecar_value, str) or not sidecar_value.endswith(".png.candidate.json"):
        errors.append(f"items[{index}].target_sidecar_path must be a .png.candidate.json path")

    if item.get("provider_called_this_run") is not False:
        errors.append(f"items[{index}].provider_called_this_run must be false")
    if item.get("promotion_allowed_now") is not False:
        errors.append(f"items[{index}].promotion_allowed_now must be false")

    if status == "awaiting_local_artifact":
        if item.get("source_png_path") is not None or item.get("source_png_sha256") is not None:
            errors.append(f"items[{index}] awaiting item must not carry source PNG refs")
        return

    source_value = item.get("source_png_path")
    if not isinstance(source_value, str) or not source_value.strip():
        errors.append(f"items[{index}].source_png_path is required for non-awaiting item")
        return
    source = resolve_path(source_value)
    if not (is_relative_to(source, ROOT) or (source.is_absolute() and is_relative_to(source, ALLOWED_TMP_DIR))):
        errors.append(f"items[{index}].source_png_path must be under repository root or /tmp")
    if source.suffix.lower() != ".png":
        errors.append(f"items[{index}].source_png_path must point to a PNG")
    source_sha = item.get("source_png_sha256")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        errors.append(f"items[{index}].source_png_sha256 must be a sha256 hex string")
    if status == "imported_pending_candidate_review":
        if not source.exists():
            errors.append(f"items[{index}].source_png_path does not exist")
        elif source_sha != sha256_file(source):
            errors.append(f"items[{index}].source_png_sha256 does not match source file")
        target = resolve_path(str(target_value))
        target_sha = item.get("target_candidate_sha256")
        if not target.exists():
            errors.append(f"items[{index}].target_candidate_path does not exist")
        elif target_sha != sha256_file(target):
            errors.append(f"items[{index}].target_candidate_sha256 does not match target file")
        if item.get("review_status") != "candidate_needs_candidate_review_first":
            errors.append(f"items[{index}].review_status must be candidate_needs_candidate_review_first")
        if item.get("generation_status") != "local_artifact_imported_pending_candidate_review":
            errors.append(f"items[{index}].generation_status must be local_artifact_imported_pending_candidate_review")


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != REPORT_VERSION:
        errors.append(f"schema_version must be {REPORT_VERSION}")
    for field in ("report_id", "status", "request_pack_path", "import_plan_path", "target_dir"):
        if not isinstance(report.get(field), str) or not report.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")
    target_dir = resolve_path(str(report.get("target_dir") or ""))
    if not is_relative_to(target_dir, ALLOWED_TARGET_DIR):
        errors.append("target_dir must be controlled candidate dir")
    safety = as_obj(report.get("safety_summary"))
    for key, expected in REQUIRED_SAFETY.items():
        if safety.get(key) is not expected:
            errors.append(f"safety_summary.{key} must be {expected}")

    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    if len(items) != len(as_list(report.get("items"))):
        errors.append("items must contain only objects")
    if not items:
        errors.append("items must be a non-empty array")
    for index, item in enumerate(items):
        validate_item(item, index, errors)

    summary = as_obj(report.get("summary"))
    status_counts = Counter(str(item.get("status")) for item in items)
    if as_obj(summary.get("status_counts")) != dict(sorted(status_counts.items())):
        errors.append("summary.status_counts must match items")
    if summary.get("request_count") != len(items):
        errors.append("summary.request_count must match items length")
    if summary.get("provider_call_count") != 0:
        errors.append("summary.provider_call_count must be 0")
    if summary.get("runtime_mutation_count") != 0:
        errors.append("summary.runtime_mutation_count must be 0")
    if summary.get("published_visual_layer_write_count") != 0:
        errors.append("summary.published_visual_layer_write_count must be 0")
    if summary.get("map_runtime_package_write_count") != 0:
        errors.append("summary.map_runtime_package_write_count must be 0")
    return errors


def parse_expected_status_counts(values: list[str]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--expect-status-count values must use status=count")
        status, raw_count = value.split("=", 1)
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported expected status: {status}")
        try:
            count = int(raw_count)
        except ValueError as exc:
            raise ValueError(f"invalid expected count for {status}: {raw_count}") from exc
        if count < 0:
            raise ValueError(f"expected count for {status} must be >= 0")
        expected[status] = count
    return expected


def validate_expected_status_counts(report: dict[str, Any], expected: dict[str, int]) -> list[str]:
    if not expected:
        return []
    status_counts = as_obj(as_obj(report.get("summary")).get("status_counts"))
    errors: list[str] = []
    for status, count in expected.items():
        if int(status_counts.get(status) or 0) != count:
            errors.append(f"summary.status_counts.{status} must be {count}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--expect-status-count",
        action="append",
        default=[],
        metavar="STATUS=COUNT",
        help="Optional exact status count assertion, for smoke contracts.",
    )
    args = parser.parse_args()
    try:
        report = load_json(resolve_path(str(args.report)))
        if not isinstance(report, dict):
            raise ValueError("report root must be an object")
        expected_counts = parse_expected_status_counts(args.expect_status_count)
        errors = validate(report)
        errors.extend(validate_expected_status_counts(report, expected_counts))
    except Exception as exc:  # noqa: BLE001
        print(f"controlled map artifact import report validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("controlled map artifact import report validation failed", file=sys.stderr)
        return 1
    print(f"controlled map artifact import report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
