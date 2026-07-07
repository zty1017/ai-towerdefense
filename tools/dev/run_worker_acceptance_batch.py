#!/usr/bin/env python3
"""Run or dry-run WorkerTaskPack acceptance profiles across a selected batch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso  # noqa: E402
from tools.dev.run_worker_acceptance_profile import (  # noqa: E402
    empty_report,
    load_task_pack,
    profile_metadata,
    run_profile_commands,
)
from tools.dev.worker_acceptance_batch_contract import (  # noqa: E402
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_PASSED,
    WORKER_ACCEPTANCE_BATCH_DEFAULT_OUTPUT,
    WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION,
    batch_status_from_summary,
    summarize_batch_packs,
)


DEFAULT_TASK_PACK_DIR = Path("examples/worker_task_packs")
DEFAULT_OUTPUT = WORKER_ACCEPTANCE_BATCH_DEFAULT_OUTPUT


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def resolve_task_pack_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def load_task_id(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and isinstance(data.get("task_id"), str):
        return data["task_id"]
    return ""


def discover_task_packs(args: argparse.Namespace) -> list[Path]:
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be >= 1")

    explicit = [resolve_task_pack_path(path) for path in args.task_pack]
    if explicit:
        candidates = explicit
    else:
        if not (args.all or args.task_id_prefix or args.path_contains):
            raise ValueError(
                "refusing to select every task pack implicitly; pass --all, --task-id-prefix, "
                "--path-contains, or explicit --task-pack"
            )
        task_pack_dir = resolve_task_pack_path(args.task_pack_dir)
        candidates = sorted(task_pack_dir.glob("*.json"))

    filtered: list[Path] = []
    for path in candidates:
        display = display_path(path)
        task_id = load_task_id(path) if path.exists() else ""
        if args.task_id_prefix and not any(task_id.startswith(prefix) for prefix in args.task_id_prefix):
            continue
        if args.path_contains and not any(fragment in display for fragment in args.path_contains):
            continue
        filtered.append(path)

    if args.limit is not None:
        filtered = filtered[: args.limit]
    if not filtered:
        raise ValueError("no task packs selected")
    return filtered


def summarize_profile_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "status": report.get("status"),
        "selected_profile": report.get("selected_profile"),
        "command_count": summary.get("command_count"),
        "configured_command_count": summary.get("configured_command_count"),
        "pass": summary.get("pass"),
        "fail": summary.get("fail"),
        "dry_run": summary.get("dry_run"),
    }


def profile_report_for_error(
    *,
    task_pack: Path,
    selected_profile: str | None,
    message: str,
    error: str,
    fail_fast: bool,
) -> dict[str, Any]:
    return empty_report(
        task_pack=task_pack,
        selected_profile=selected_profile,
        default_profile=None,
        available_profiles=[],
        status=STATUS_FAILED,
        fail_fast=fail_fast,
        results=[
            {
                "name": "task_pack_batch_selection",
                "command": display_path(task_pack),
                "status": STATUS_FAILED,
                "error": error,
                "message": message,
            }
        ],
    )


def run_one_pack(
    *,
    task_pack: Path,
    selected_profile: str | None,
    dry_run: bool,
    fail_fast: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    try:
        data = load_task_pack(task_pack)
        task_id = str(data.get("task_id") or "")
        default_profile, profiles = profile_metadata(data)
    except Exception as exc:  # noqa: BLE001 - keep batch running if allowed.
        profile_report = profile_report_for_error(
            task_pack=task_pack,
            selected_profile=selected_profile,
            message=str(exc),
            error="task_pack_validation_failed",
            fail_fast=fail_fast,
        )
        return {
            "task_pack": display_path(task_pack),
            "task_id": "",
            "status": STATUS_FAILED,
            "profile_report": profile_report,
            "summary": summarize_profile_report(profile_report),
        }

    available_profiles = sorted(str(profile_id) for profile_id in profiles)
    actual_profile = selected_profile or default_profile
    if actual_profile not in profiles:
        message = f"profile {actual_profile!r} not found; available profiles: {available_profiles}"
        profile_report = profile_report_for_error(
            task_pack=task_pack,
            selected_profile=actual_profile,
            message=message,
            error="profile_not_found",
            fail_fast=fail_fast,
        )
        return {
            "task_pack": display_path(task_pack),
            "task_id": task_id,
            "status": STATUS_FAILED,
            "profile_report": profile_report,
            "summary": summarize_profile_report(profile_report),
        }

    command_strings = list(profiles[actual_profile]["commands"])
    print(f"== {display_path(task_pack)} [{actual_profile}] ==")
    results = run_profile_commands(
        command_strings=command_strings,
        dry_run=dry_run,
        fail_fast=fail_fast,
        timeout_seconds=timeout_seconds,
    )
    failed = [item for item in results if item.get("status") == STATUS_FAILED]
    status = STATUS_FAILED if failed else STATUS_DRY_RUN if dry_run else STATUS_PASSED
    profile_report = empty_report(
        task_pack=task_pack,
        selected_profile=actual_profile,
        default_profile=default_profile,
        available_profiles=available_profiles,
        status=status,
        fail_fast=fail_fast,
        results=results,
    )
    profile_report["summary"]["configured_command_count"] = len(command_strings)
    return {
        "task_pack": display_path(task_pack),
        "task_id": task_id,
        "status": status,
        "profile_report": profile_report,
        "summary": summarize_profile_report(profile_report),
    }


def build_batch_report(args: argparse.Namespace) -> dict[str, Any]:
    selected_paths = discover_task_packs(args)
    pack_results: list[dict[str, Any]] = []
    for path in selected_paths:
        result = run_one_pack(
            task_pack=path,
            selected_profile=args.profile,
            dry_run=args.dry_run,
            fail_fast=args.fail_fast,
            timeout_seconds=args.timeout,
        )
        pack_results.append(result)
        if args.fail_fast and result["status"] == STATUS_FAILED:
            break

    summary = summarize_batch_packs(
        pack_results,
        selected_pack_count=len(selected_paths),
    )
    status = batch_status_from_summary(summary, dry_run=bool(args.dry_run))
    return {
        "schema_version": WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "status": status,
        "selection": {
            "task_pack_dir": display_path(resolve_task_pack_path(args.task_pack_dir)),
            "explicit_task_pack_count": len(args.task_pack),
            "all": bool(args.all),
            "task_id_prefix": list(args.task_id_prefix),
            "path_contains": list(args.path_contains),
            "limit": args.limit,
            "profile": args.profile,
            "dry_run": bool(args.dry_run),
            "fail_fast": bool(args.fail_fast),
        },
        "summary": summary,
        "packs": pack_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-pack-dir", type=Path, default=DEFAULT_TASK_PACK_DIR)
    parser.add_argument("--task-pack", type=Path, action="append", default=[])
    parser.add_argument("--task-id-prefix", action="append", default=[])
    parser.add_argument("--path-contains", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="Select all task packs in --task-pack-dir.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--profile", help="Profile id to run for every selected pack.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--timeout", type=int, default=180, help="Per-command timeout seconds.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_batch_report(args)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        report = {
            "schema_version": WORKER_ACCEPTANCE_BATCH_REPORT_SCHEMA_VERSION,
            "generated_at": now_iso(),
            "status": STATUS_FAILED,
            "selection": {
                "task_pack_dir": str(args.task_pack_dir),
                "explicit_task_pack_count": len(args.task_pack),
                "all": bool(args.all),
                "task_id_prefix": list(args.task_id_prefix),
                "path_contains": list(args.path_contains),
                "limit": args.limit,
                "profile": args.profile,
                "dry_run": bool(args.dry_run),
                "fail_fast": bool(args.fail_fast),
            },
            "summary": {
                "selected_pack_count": 0,
                "executed_pack_count": 0,
                "passed_pack_count": 0,
                "failed_pack_count": 1,
                "dry_run_pack_count": 0,
                "configured_command_count": 0,
                "command_result_count": 0,
            },
            "packs": [],
            "error": str(exc),
        }
        write_json(args.output, report)
        print(f"worker acceptance batch failed: {exc}", file=sys.stderr)
        print(f"worker acceptance batch report: {args.output}")
        return 1

    write_json(args.output, report)
    print(
        "worker acceptance batch "
        f"{report['status']}: {report['summary']['executed_pack_count']} pack(s), "
        f"{report['summary']['command_result_count']} command result(s)"
    )
    print(f"worker acceptance batch report: {args.output}")
    return 0 if report["status"] in {STATUS_PASSED, STATUS_DRY_RUN} else 1


if __name__ == "__main__":
    raise SystemExit(main())
