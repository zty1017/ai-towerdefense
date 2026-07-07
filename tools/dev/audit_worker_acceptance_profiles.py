#!/usr/bin/env python3
"""Audit WorkerTaskPack acceptance_profile migration readiness.

This tool is intentionally read-only. It validates task packs, classifies their
existing acceptance commands, and reports which packs are good candidates for an
acceptance_profile migration without executing any acceptance command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.audit_common import (  # noqa: E402
    display_path,
    load_json_object,
    normalize_command,
    require_tmp_output,
    string_list,
    write_json,
)
from tools.dev.command_runner import now_iso
from tools.dev.run_worker_acceptance_profile import parse_command
from tools.dev.validate_worker_task_pack import validate


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_audit_report.v0.1"
DEFAULT_TASK_PACK_DIR = Path("examples/worker_task_packs")
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_audit_report.v0.1.json")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return load_json_object(path)
    except ValueError as exc:
        raise ValueError("WorkerTaskPack root must be an object") from exc


def is_summary_only(command: str) -> bool:
    normalized = normalize_command(command)
    return (
        "--validation-profile summary-only" in normalized
        or "--validation-profile=summary-only" in normalized
    )


def is_full_export(command: str) -> bool:
    normalized = normalize_command(command)
    return (
        "tools/demo/export_evidence.py" in normalized
        and "--output-dir" in normalized
        and not is_summary_only(normalized)
    )


def is_fast_gate(command: str) -> bool:
    return "tools/dev/run_fast_quality_gate.py" in normalize_command(command)


def runner_compatibility(command: str) -> dict[str, Any]:
    try:
        parsed = parse_command(command)
    except Exception as exc:  # noqa: BLE001 - audit should keep scanning all packs.
        return {
            "runner_compatible": False,
            "reason": f"{exc.__class__.__name__}:{exc}",
        }
    return {
        "runner_compatible": True,
        "reason": None,
        "argv": parsed.argv,
        "env": parsed.env,
    }


def analyze_commands(commands: list[str]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    for index, command in enumerate(commands, start=1):
        compatibility = runner_compatibility(command)
        details.append(
            {
                "index": index,
                "command": command,
                "is_full_export": is_full_export(command),
                "is_summary_only": is_summary_only(command),
                "is_fast_gate": is_fast_gate(command),
                "runner_compatible": bool(compatibility["runner_compatible"]),
                "incompatibility_reason": compatibility["reason"],
            }
        )
    counts = {
        "command_count": len(commands),
        "full_export_count": sum(1 for item in details if item["is_full_export"]),
        "summary_only_count": sum(1 for item in details if item["is_summary_only"]),
        "fast_gate_count": sum(1 for item in details if item["is_fast_gate"]),
        "runner_compatible_count": sum(1 for item in details if item["runner_compatible"]),
        "runner_incompatible_count": sum(1 for item in details if not item["runner_compatible"]),
    }
    return counts, details


def profile_commands(data: dict[str, Any]) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    acceptance_profile = data.get("acceptance_profile")
    if not isinstance(acceptance_profile, dict):
        return None, [], []

    default_profile = acceptance_profile.get("default_profile")
    profiles = acceptance_profile.get("profiles")
    if not isinstance(profiles, dict):
        return str(default_profile) if default_profile is not None else None, [], []

    profile_ids = sorted(str(profile_id) for profile_id in profiles)
    analyzed_profiles: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        profile = profiles.get(profile_id)
        commands = string_list(profile.get("commands") if isinstance(profile, dict) else None)
        counts, details = analyze_commands(commands)
        analyzed_profiles.append(
            {
                "profile_id": profile_id,
                "command_counts": counts,
                "commands": details,
                "runner_compatible": counts["runner_incompatible_count"] == 0,
            }
        )
    return (
        str(default_profile) if isinstance(default_profile, str) else None,
        profile_ids,
        analyzed_profiles,
    )


def recommendations_for_pack(
    *,
    validation_status: str,
    has_acceptance_profile: bool,
    top_level_counts: dict[str, int],
    profile_counts: dict[str, int],
) -> list[str]:
    recommendations: list[str] = []
    has_shell_like = (
        top_level_counts["runner_incompatible_count"] > 0
        or profile_counts["runner_incompatible_count"] > 0
    )

    if validation_status != "passed":
        recommendations.append("fix_validation_errors_before_migration")
    elif not has_acceptance_profile:
        if top_level_counts["full_export_count"] > 0:
            recommendations.append(
                "add_acceptance_profile_with_daily_fast_summary_only_and_full_evidence"
            )
        else:
            recommendations.append("add_acceptance_profile_from_existing_acceptance_commands")
        if top_level_counts["fast_gate_count"] > 0:
            recommendations.append("preserve_fast_gate_in_daily_fast_profile")
        if top_level_counts["summary_only_count"] > 0:
            recommendations.append("preserve_summary_only_export_in_daily_fast_profile")
        if top_level_counts["runner_incompatible_count"] == 0:
            recommendations.append("top_level_commands_are_runner_compatible")
    else:
        if profile_counts["runner_incompatible_count"] == 0:
            recommendations.append("acceptance_profile_present_and_runner_compatible")
        else:
            recommendations.append("acceptance_profile_present_with_manual_command_review")

    if has_shell_like:
        recommendations.append("manual_review_shell_only_commands_before_runner_migration")
    return recommendations


def analyze_pack(path: Path) -> dict[str, Any]:
    validation_status = "failed"
    validation_error: str | None = None
    data: dict[str, Any] = {}
    try:
        data = load_json(path)
        validate(data)
        validation_status = "passed"
    except Exception as exc:  # noqa: BLE001 - audit report should include invalid packs.
        validation_error = str(exc)

    top_level_commands = string_list(data.get("acceptance_commands"))
    top_level_counts, top_level_details = analyze_commands(top_level_commands)
    default_profile, profile_ids, analyzed_profiles = profile_commands(data)

    profile_total_counts = {
        "command_count": sum(
            item["command_counts"]["command_count"] for item in analyzed_profiles
        ),
        "runner_compatible_count": sum(
            item["command_counts"]["runner_compatible_count"] for item in analyzed_profiles
        ),
        "runner_incompatible_count": sum(
            item["command_counts"]["runner_incompatible_count"] for item in analyzed_profiles
        ),
        "runner_compatible_profile_count": sum(
            1 for item in analyzed_profiles if item["runner_compatible"]
        ),
        "runner_incompatible_profile_count": sum(
            1 for item in analyzed_profiles if not item["runner_compatible"]
        ),
    }
    has_acceptance_profile = isinstance(data.get("acceptance_profile"), dict)
    recommendations = recommendations_for_pack(
        validation_status=validation_status,
        has_acceptance_profile=has_acceptance_profile,
        top_level_counts=top_level_counts,
        profile_counts=profile_total_counts,
    )

    return {
        "path": display_path(path),
        "task_id": data.get("task_id") if isinstance(data.get("task_id"), str) else None,
        "title": data.get("title") if isinstance(data.get("title"), str) else None,
        "has_acceptance_profile": has_acceptance_profile,
        "default_profile": default_profile,
        "profile_ids": profile_ids,
        "validation_status": validation_status,
        "validation_error": validation_error,
        "top_level_command_counts": top_level_counts,
        "top_level_commands": top_level_details,
        "profile_runner_counts": profile_total_counts,
        "profiles": analyzed_profiles,
        "recommendations": recommendations,
        "migration_candidate": (
            validation_status == "passed" and not has_acceptance_profile
        ),
        "manual_review_required": (
            validation_status != "passed"
            or top_level_counts["runner_incompatible_count"] > 0
            or profile_total_counts["runner_incompatible_count"] > 0
        ),
    }


def sample(
    items: list[dict[str, Any]],
    max_samples: int,
    predicate: Any,
    mapper: Any,
) -> list[dict[str, Any]]:
    if max_samples <= 0:
        return []
    results: list[dict[str, Any]] = []
    for item in items:
        if predicate(item):
            results.append(mapper(item))
        if len(results) >= max_samples:
            break
    return results


def first_full_export_command(pack: dict[str, Any]) -> str | None:
    for command in pack["top_level_commands"]:
        if command["is_full_export"]:
            return command["command"]
    return None


def first_manual_command(pack: dict[str, Any]) -> dict[str, Any] | None:
    for command in pack["top_level_commands"]:
        if not command["runner_compatible"]:
            return {
                "scope": "acceptance_commands",
                "index": command["index"],
                "command": command["command"],
                "reason": command["incompatibility_reason"],
            }
    for profile in pack["profiles"]:
        for command in profile["commands"]:
            if not command["runner_compatible"]:
                return {
                    "scope": f"acceptance_profile.{profile['profile_id']}",
                    "index": command["index"],
                    "command": command["command"],
                    "reason": command["incompatibility_reason"],
                }
    if pack["validation_status"] != "passed":
        return {
            "scope": "validation",
            "index": None,
            "command": None,
            "reason": pack["validation_error"],
        }
    return None


def build_report(task_pack_dir: Path, max_samples: int) -> dict[str, Any]:
    task_pack_dir = task_pack_dir if task_pack_dir.is_absolute() else ROOT / task_pack_dir
    paths = sorted(task_pack_dir.glob("*.json"))
    packs = [analyze_pack(path) for path in paths]

    summary = {
        "total_count": len(packs),
        "valid_count": sum(1 for item in packs if item["validation_status"] == "passed"),
        "invalid_count": sum(1 for item in packs if item["validation_status"] != "passed"),
        "with_profile_count": sum(1 for item in packs if item["has_acceptance_profile"]),
        "without_profile_count": sum(1 for item in packs if not item["has_acceptance_profile"]),
        "top_level_full_export_count": sum(
            item["top_level_command_counts"]["full_export_count"] for item in packs
        ),
        "top_level_fast_gate_count": sum(
            item["top_level_command_counts"]["fast_gate_count"] for item in packs
        ),
        "top_level_summary_only_count": sum(
            item["top_level_command_counts"]["summary_only_count"] for item in packs
        ),
        "shell_like_command_pack_count": sum(
            1
            for item in packs
            if item["top_level_command_counts"]["runner_incompatible_count"] > 0
            or item["profile_runner_counts"]["runner_incompatible_count"] > 0
        ),
        "runner_compatible_profile_count": sum(
            item["profile_runner_counts"]["runner_compatible_profile_count"]
            for item in packs
        ),
        "migration_candidate_count": sum(1 for item in packs if item["migration_candidate"]),
        "manual_review_required_count": sum(
            1 for item in packs if item["manual_review_required"]
        ),
    }

    without_profile_samples = sample(
        packs,
        max_samples,
        lambda item: not item["has_acceptance_profile"],
        lambda item: {
            "path": item["path"],
            "task_id": item["task_id"],
            "validation_status": item["validation_status"],
            "recommendations": item["recommendations"],
        },
    )
    full_export_samples = sample(
        packs,
        max_samples,
        lambda item: item["top_level_command_counts"]["full_export_count"] > 0,
        lambda item: {
            "path": item["path"],
            "task_id": item["task_id"],
            "command": first_full_export_command(item),
        },
    )
    manual_review_samples = sample(
        packs,
        max_samples,
        lambda item: item["manual_review_required"],
        lambda item: {
            "path": item["path"],
            "task_id": item["task_id"],
            "issue": first_manual_command(item),
            "recommendations": item["recommendations"],
        },
    )
    migration_candidate_samples = sample(
        packs,
        max_samples,
        lambda item: item["migration_candidate"],
        lambda item: {
            "path": item["path"],
            "task_id": item["task_id"],
            "top_level_command_counts": item["top_level_command_counts"],
            "recommendations": item["recommendations"],
        },
    )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "task_pack_dir": display_path(task_pack_dir),
        "summary": summary,
        "without_profile_samples": without_profile_samples,
        "full_export_samples": full_export_samples,
        "manual_review_samples": manual_review_samples,
        "migration_candidate_samples": migration_candidate_samples,
        "samples": {
            "without_profile_samples": without_profile_samples,
            "full_export_samples": full_export_samples,
            "manual_review_samples": manual_review_samples,
            "migration_candidate_samples": migration_candidate_samples,
        },
        "packs": packs,
        "boundary": {
            "read_only": True,
            "acceptance_commands_executed": False,
            "uses_worker_task_pack_validator": True,
            "uses_acceptance_profile_command_parser": True,
        },
        "safety_summary": {
            "provider_call_count": 0,
            "env_file_read": False,
            "repo_files_modified": False,
            "acceptance_commands_executed": False,
            "report_only": True,
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
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Write the audit report to this path.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=20,
        help="Maximum entries per sample list.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    max_samples = max(0, int(args.max_samples))
    report = build_report(args.task_pack_dir, max_samples)
    try:
        output_path = require_tmp_output(args.output)
    except ValueError as exc:
        print(f"worker acceptance profile audit failed: {exc}", file=sys.stderr)
        return 2
    write_json(output_path, report)
    summary = report["summary"]
    print(f"worker acceptance profile audit report: {output_path}")
    print(
        "audited {total_count} packs: {with_profile_count} with profile, "
        "{without_profile_count} without profile, {migration_candidate_count} "
        "migration candidates, {manual_review_required_count} manual review required".format(
            **summary
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
