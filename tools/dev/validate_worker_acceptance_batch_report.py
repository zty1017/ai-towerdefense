#!/usr/bin/env python3
"""Validate WorkerTaskPack batch runner reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.worker_acceptance_batch_contract import (  # noqa: E402
    WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION,
    WORKER_ACCEPTANCE_BATCH_VALID_STATUSES,
    batch_status_from_summary,
    summarize_batch_packs,
)
from tools.dev.worker_acceptance_profile_contract import (  # noqa: E402
    WORKER_ACCEPTANCE_PROFILE_REPORT_SCHEMA_VERSION,
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_report(
    report: dict[str, Any],
    *,
    expect_status: str | None,
    expect_failed_count: int | None,
    min_pack_count: int,
) -> dict[str, Any]:
    require(
        report.get("schema_version") == WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION,
        "schema_version mismatch",
    )
    status = report.get("status")
    require(status in WORKER_ACCEPTANCE_BATCH_VALID_STATUSES, f"invalid status: {status!r}")
    if expect_status is not None:
        require(status == expect_status, f"status must be {expect_status!r}")

    summary = as_obj(report.get("summary"))
    selection = as_obj(report.get("selection"))
    packs = as_list(report.get("packs"))
    selected_count = int(summary.get("selected_pack_count") or 0)
    executed_count = int(summary.get("executed_pack_count") or 0)
    failed_count = int(summary.get("failed_pack_count") or 0)
    passed_count = int(summary.get("passed_pack_count") or 0)
    dry_run_count = int(summary.get("dry_run_pack_count") or 0)
    typed_packs: list[dict[str, Any]] = []
    for index, pack in enumerate(packs):
        require(isinstance(pack, dict), f"packs[{index}] must be an object")
        typed_packs.append(pack)
    expected_summary = summarize_batch_packs(typed_packs, selected_pack_count=selected_count)
    require(selected_count >= min_pack_count, f"selected_pack_count must be >= {min_pack_count}")
    require(executed_count == len(packs), "executed_pack_count must match packs length")
    require(executed_count <= selected_count, "executed_pack_count cannot exceed selected_pack_count")
    require(
        failed_count + passed_count + dry_run_count == executed_count,
        "pack status counts must sum to executed_pack_count",
    )
    require(
        failed_count == expected_summary["failed_pack_count"],
        "failed_pack_count must match packs statuses",
    )
    require(
        passed_count == expected_summary["passed_pack_count"],
        "passed_pack_count must match packs statuses",
    )
    require(
        dry_run_count == expected_summary["dry_run_pack_count"],
        "dry_run_pack_count must match packs statuses",
    )
    require(
        int(summary.get("configured_command_count") or 0)
        == expected_summary["configured_command_count"],
        "configured_command_count must match pack summaries",
    )
    require(
        int(summary.get("command_result_count") or 0) == expected_summary["command_result_count"],
        "command_result_count must match pack summaries",
    )
    expected_status = batch_status_from_summary(
        expected_summary,
        dry_run=selection.get("dry_run") is True,
    )
    require(status == expected_status, f"status must be {expected_status!r}")
    if selection.get("dry_run") is not True:
        require(dry_run_count == 0, "dry_run_pack_count must be 0 when selection.dry_run is not true")
    if expect_failed_count is not None:
        require(failed_count == expect_failed_count, f"failed_pack_count must be {expect_failed_count}")
    for index, pack in enumerate(typed_packs):
        require(
            pack.get("status") in WORKER_ACCEPTANCE_BATCH_VALID_STATUSES,
            f"packs[{index}].status invalid",
        )
        profile_report = as_obj(pack.get("profile_report"))
        require(
            profile_report.get("schema_version")
            == WORKER_ACCEPTANCE_PROFILE_REPORT_SCHEMA_VERSION,
            f"packs[{index}] profile schema mismatch",
        )
        require(profile_report.get("status") == pack.get("status"), f"packs[{index}] status mismatch")
    return {
        "status": status,
        "selected_pack_count": selected_count,
        "executed_pack_count": executed_count,
        "failed_pack_count": failed_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expect-status", choices=sorted(WORKER_ACCEPTANCE_BATCH_VALID_STATUSES))
    parser.add_argument("--expect-failed-count", type=int)
    parser.add_argument("--min-pack-count", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = validate_report(
            load_json(args.report),
            expect_status=args.expect_status,
            expect_failed_count=args.expect_failed_count,
            min_pack_count=args.min_pack_count,
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"worker acceptance batch report validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "worker acceptance batch report validation passed: "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
