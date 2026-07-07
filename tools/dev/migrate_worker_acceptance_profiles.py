#!/usr/bin/env python3
"""Add safe acceptance_profile blocks to runner-compatible WorkerTaskPacks.

Default mode is report-only. Repository files are modified only with --write,
and only for packs whose existing acceptance_commands can already be parsed by
run_worker_acceptance_profile.py without shell-only syntax.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.audit_worker_acceptance_profiles import (  # noqa: E402
    analyze_pack,
    display_path,
    is_full_export,
    require_tmp_output,
)
from tools.dev.command_runner import now_iso  # noqa: E402
from tools.dev.report_io import load_json_object, write_json  # noqa: E402
from tools.dev.validate_worker_task_pack import validate  # noqa: E402


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_migration_report.v0.1"
DEFAULT_TASK_PACK_DIR = Path("examples/worker_task_packs")
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_migration_report.v0.1.json")


def resolve_task_pack(path: Path) -> Path:
    resolved = path if path.is_absolute() else ROOT / path
    return resolved.resolve(strict=False)


def insert_after_key(data: dict[str, Any], key: str, inserted_key: str, value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    inserted = False
    for current_key, current_value in data.items():
        result[current_key] = current_value
        if current_key == key:
            result[inserted_key] = value
            inserted = True
    if not inserted:
        result[inserted_key] = value
    return result


def build_acceptance_profile(commands: list[str]) -> dict[str, Any]:
    daily_fast_commands = [command for command in commands if not is_full_export(command)]
    if not daily_fast_commands:
        raise ValueError("cannot build daily_fast profile with no non-full-evidence commands")

    profiles: dict[str, Any] = {
        "daily_fast": {
            "description": (
                "日常快速 profile，复用原 acceptance_commands 中不运行完整 evidence "
                "export 的命令，供本地交付前快速验收。"
            ),
            "commands": daily_fast_commands,
            "required_for": ["daily_small_changes", "pre_handoff_sanity"],
        }
    }
    if any(is_full_export(command) for command in commands):
        profiles["full_evidence"] = {
            "description": (
                "最终评审 profile，完整复用原 acceptance_commands，包含 full "
                "demo evidence export。"
            ),
            "commands": commands,
            "required_for": ["final_review", "merge_readiness_without_recording"],
        }

    return {
        "default_profile": "daily_fast",
        "profiles": profiles,
    }


def should_include(path: Path, selected: set[Path], include_prefixes: list[str]) -> bool:
    rel = display_path(path)
    if selected:
        return path.resolve(strict=False) in selected
    if include_prefixes:
        name = path.name
        return any(name.startswith(prefix) or rel.startswith(prefix) for prefix in include_prefixes)
    return True


def candidate_paths(
    *,
    task_pack_dir: Path,
    task_packs: list[Path],
    include_prefixes: list[str],
) -> list[Path]:
    root_dir = task_pack_dir if task_pack_dir.is_absolute() else ROOT / task_pack_dir
    all_paths = sorted(root_dir.glob("*.json"))
    selected = {resolve_task_pack(path) for path in task_packs}
    if selected:
        missing = sorted(str(path) for path in selected if not path.exists())
        if missing:
            raise FileNotFoundError(f"task pack(s) not found: {missing}")
    return [
        path
        for path in all_paths
        if should_include(path.resolve(strict=False), selected, include_prefixes)
    ]


def migrate_one(path: Path, *, write: bool) -> dict[str, Any]:
    analysis = analyze_pack(path)
    result: dict[str, Any] = {
        "path": analysis["path"],
        "task_id": analysis["task_id"],
        "status": "skipped",
        "write_applied": False,
        "reason": None,
        "profile_ids": [],
    }

    if analysis["validation_status"] != "passed":
        result["reason"] = "validation_failed"
        result["validation_error"] = analysis["validation_error"]
        return result
    if analysis["has_acceptance_profile"]:
        result["reason"] = "acceptance_profile_already_present"
        result["profile_ids"] = analysis["profile_ids"]
        return result
    if analysis["top_level_command_counts"]["runner_incompatible_count"] > 0:
        result["reason"] = "runner_incompatible_acceptance_commands"
        result["incompatible_commands"] = [
            {
                "index": item["index"],
                "command": item["command"],
                "reason": item["incompatibility_reason"],
            }
            for item in analysis["top_level_commands"]
            if not item["runner_compatible"]
        ]
        return result

    data = load_json_object(path)
    commands = data["acceptance_commands"]
    profile = build_acceptance_profile(commands)
    proposed = insert_after_key(data, "acceptance_commands", "acceptance_profile", profile)
    validate(proposed)

    result["status"] = "migrated" if write else "would_migrate"
    result["reason"] = "runner_compatible_acceptance_commands"
    result["profile_ids"] = sorted(profile["profiles"])
    result["default_profile"] = profile["default_profile"]
    result["daily_fast_command_count"] = len(profile["profiles"]["daily_fast"]["commands"])
    result["full_evidence_command_count"] = len(
        profile["profiles"].get("full_evidence", {}).get("commands", [])
    )

    if write:
        write_json(path, proposed, sort_keys=False)
        result["write_applied"] = True
    return result


def build_report(
    *,
    paths: list[Path],
    write: bool,
    limit: int | None,
) -> dict[str, Any]:
    selected_paths = paths[:limit] if limit is not None else paths
    results = [migrate_one(path, write=write) for path in selected_paths]
    summary = {
        "target_count": len(selected_paths),
        "would_migrate_count": sum(1 for item in results if item["status"] == "would_migrate"),
        "migrated_count": sum(1 for item in results if item["status"] == "migrated"),
        "skipped_count": sum(1 for item in results if item["status"] == "skipped"),
        "runner_incompatible_skip_count": sum(
            1 for item in results if item.get("reason") == "runner_incompatible_acceptance_commands"
        ),
        "already_profile_skip_count": sum(
            1 for item in results if item.get("reason") == "acceptance_profile_already_present"
        ),
        "validation_failed_skip_count": sum(
            1 for item in results if item.get("reason") == "validation_failed"
        ),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "write_enabled": write,
        "summary": summary,
        "results": results,
        "safety_summary": {
            "provider_call_count": 0,
            "env_file_read": False,
            "acceptance_commands_executed": False,
            "repo_files_modified": bool(write and summary["migrated_count"] > 0),
            "only_runner_compatible_packs_written": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-pack-dir",
        type=Path,
        default=DEFAULT_TASK_PACK_DIR,
        help="Directory containing WorkerTaskPack JSON files.",
    )
    parser.add_argument(
        "--task-pack",
        type=Path,
        action="append",
        default=[],
        help="Specific task pack to migrate. May be repeated.",
    )
    parser.add_argument(
        "--include-prefix",
        action="append",
        default=[],
        help="Only include task pack filenames or paths with this prefix.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum selected packs to inspect/migrate after filtering.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write acceptance_profile blocks to eligible task packs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Write migration report to this /tmp path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        print("--limit must be non-negative", file=sys.stderr)
        return 2
    try:
        output_path = require_tmp_output(args.output)
        paths = candidate_paths(
            task_pack_dir=args.task_pack_dir,
            task_packs=args.task_pack,
            include_prefixes=args.include_prefix,
        )
        report = build_report(paths=paths, write=bool(args.write), limit=args.limit)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failure.
        print(f"worker acceptance profile migration failed: {exc}", file=sys.stderr)
        return 2
    write_json(output_path, report, sort_keys=False)
    summary = report["summary"]
    action = "migrated" if args.write else "would migrate"
    print(f"worker acceptance profile migration report: {output_path}")
    print(
        f"{action} {summary['migrated_count'] or summary['would_migrate_count']} "
        f"of {summary['target_count']} selected pack(s); skipped {summary['skipped_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
