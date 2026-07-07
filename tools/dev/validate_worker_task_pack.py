#!/usr/bin/env python3
"""Validate WorkerTaskPack v0.1 files using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "worker_task_pack.v0.1"
REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "title",
    "task_type",
    "handoff_mode",
    "base_branch",
    "branch",
    "worktree",
    "objective",
    "required_reading",
    "allowed_paths",
    "forbidden_paths",
    "acceptance_commands",
    "reporting_requirements",
    "safety_rules",
    "provider_policy",
}
TASK_TYPES = {"implementation", "fix", "test", "docs", "prototype", "review", "research"}
HANDOFF_MODES = {
    "codebuddy_ide",
    "codebuddy_cli",
    "opencode_headless",
    "codex_headless",
    "human_worker",
    "local_codex_safe_fallback",
}
REQUIRED_READINGS = {
    "docs/CURRENT_ARCHITECTURE_INDEX.md",
    "docs/AI_COMPILATION_SYSTEM_V0_1.md",
    "control/TASK_QUEUE.md",
}
REQUIRED_REPORTING = {
    "modified_files",
    "acceptance_results",
    "protected_files_touched",
    "unresolved_risks",
}
FORBIDDEN_PATH_FRAGMENTS = {
    ".env",
    ".env.local",
    "id_rsa",
    "api_key",
    "secret",
    "token",
}
FORBIDDEN_COMMAND_FRAGMENTS = {
    "git push",
    "git reset --hard",
    "git checkout --",
    "git merge main",
    "git merge develop",
    "cat .env",
    "source .env",
    "printenv",
}
ACCEPTANCE_PROFILE_FIELDS = {"default_profile", "profiles"}
ACCEPTANCE_PROFILE_ENTRY_FIELDS = {"description", "commands", "required_for"}
PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SAFETY_FALSE_FIELDS = {
    "may_read_env",
    "may_print_secrets",
    "may_store_raw_prompt",
    "may_store_provider_response",
    "may_bypass_schema_or_semantic_gates",
    "may_direct_merge_main_or_develop",
    "may_activate_review_only_artifacts",
}
SAFETY_TRUE_FIELDS = {
    "must_preserve_player_immersion",
    "must_report_protected_files_touched",
}


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("WorkerTaskPack root must be an object")
    return data


def _validate_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not contain duplicates")
    return value


def _as_string_list(data: dict[str, Any], field: str) -> list[str]:
    return _validate_string_list(data.get(field), field)


def _contains_forbidden_path(path: str) -> bool:
    lowered = path.lower()
    return any(fragment in lowered for fragment in FORBIDDEN_PATH_FRAGMENTS)


def _validate_paths(data: dict[str, Any]) -> None:
    allowed = _as_string_list(data, "allowed_paths")
    forbidden = _as_string_list(data, "forbidden_paths")
    if any(_contains_forbidden_path(path) for path in allowed):
        raise ValueError("allowed_paths must not include env, secret, token, or api key paths")
    if ".env" not in forbidden:
        raise ValueError("forbidden_paths must explicitly include .env")
    overlap = set(allowed).intersection(forbidden)
    if overlap:
        raise ValueError(f"allowed_paths and forbidden_paths overlap: {sorted(overlap)}")


def _validate_command_list(commands: list[str], field: str) -> None:
    for command in commands:
        lowered = command.lower()
        for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
            if fragment in lowered:
                raise ValueError(f"{field} contains forbidden command fragment: {fragment}")


def _has_summary_only_validation_profile(command: str) -> bool:
    normalized = " ".join(command.lower().split())
    return (
        "--validation-profile summary-only" in normalized
        or "--validation-profile=summary-only" in normalized
    )


def _is_full_evidence_export(command: str) -> bool:
    normalized = " ".join(command.lower().split())
    return (
        "tools/demo/export_evidence.py" in normalized
        and "--output-dir" in normalized
        and not _has_summary_only_validation_profile(normalized)
    )


def _validate_acceptance_profile(data: dict[str, Any]) -> None:
    if "acceptance_profile" not in data:
        return

    acceptance_profile = data["acceptance_profile"]
    if not isinstance(acceptance_profile, dict):
        raise ValueError("acceptance_profile must be an object")
    unexpected = sorted(set(acceptance_profile).difference(ACCEPTANCE_PROFILE_FIELDS))
    if unexpected:
        raise ValueError(f"acceptance_profile contains unexpected fields: {unexpected}")

    default_profile = acceptance_profile.get("default_profile")
    if not isinstance(default_profile, str) or not default_profile.strip():
        raise ValueError("acceptance_profile.default_profile must be a non-empty string")
    profiles = acceptance_profile.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("acceptance_profile.profiles must be a non-empty object")
    if default_profile not in profiles:
        raise ValueError("acceptance_profile.default_profile must exist in profiles")

    for profile_id, profile in profiles.items():
        if not isinstance(profile_id, str) or not PROFILE_ID_RE.fullmatch(profile_id):
            raise ValueError("acceptance_profile profile ids must match ^[A-Za-z0-9._-]+$")
        if not isinstance(profile, dict):
            raise ValueError(f"acceptance_profile.profiles.{profile_id} must be an object")
        missing = sorted(ACCEPTANCE_PROFILE_ENTRY_FIELDS.difference(profile))
        if missing:
            raise ValueError(f"acceptance_profile.profiles.{profile_id} missing fields: {missing}")
        unexpected_profile_fields = sorted(set(profile).difference(ACCEPTANCE_PROFILE_ENTRY_FIELDS))
        if unexpected_profile_fields:
            raise ValueError(
                f"acceptance_profile.profiles.{profile_id} contains unexpected fields: "
                f"{unexpected_profile_fields}"
            )
        if not isinstance(profile.get("description"), str) or not profile["description"].strip():
            raise ValueError(f"acceptance_profile.profiles.{profile_id}.description must be non-empty")

        command_field = f"acceptance_profile.profiles.{profile_id}.commands"
        commands = _validate_string_list(profile.get("commands"), command_field)
        _validate_string_list(
            profile.get("required_for"),
            f"acceptance_profile.profiles.{profile_id}.required_for",
        )
        _validate_command_list(commands, command_field)
        if profile_id == "daily_fast":
            for command in commands:
                if _is_full_evidence_export(command):
                    raise ValueError(
                        "acceptance_profile.profiles.daily_fast.commands must not include "
                        "full tools/demo/export_evidence.py --output-dir; use "
                        "tools/dev/run_fast_quality_gate.py or "
                        "tools/demo/export_evidence.py --validation-profile summary-only instead"
                    )


def _validate_commands(data: dict[str, Any]) -> None:
    commands = _as_string_list(data, "acceptance_commands")
    _validate_command_list(commands, "acceptance_commands")
    _validate_acceptance_profile(data)


def _validate_safety(data: dict[str, Any]) -> None:
    safety = data.get("safety_rules")
    if not isinstance(safety, dict):
        raise ValueError("safety_rules must be an object")
    for field in sorted(SAFETY_FALSE_FIELDS):
        if safety.get(field) is not False:
            raise ValueError(f"safety_rules.{field} must be false")
    for field in sorted(SAFETY_TRUE_FIELDS):
        if safety.get(field) is not True:
            raise ValueError(f"safety_rules.{field} must be true")

    provider = data.get("provider_policy")
    if not isinstance(provider, dict):
        raise ValueError("provider_policy must be an object")
    if provider.get("requires_explicit_user_authorization") is not True:
        raise ValueError("provider_policy.requires_explicit_user_authorization must be true")
    if provider.get("raw_response_storage") != "forbidden":
        raise ValueError("provider_policy.raw_response_storage must be forbidden")
    allowed_profiles = provider.get("allowed_profiles")
    max_calls = provider.get("max_calls")
    calls_allowed = provider.get("provider_calls_allowed")
    if not isinstance(allowed_profiles, list):
        raise ValueError("provider_policy.allowed_profiles must be an array")
    if not isinstance(max_calls, int) or max_calls < 0:
        raise ValueError("provider_policy.max_calls must be a non-negative integer")
    if calls_allowed is True and (max_calls <= 0 or not allowed_profiles):
        raise ValueError("provider calls require max_calls > 0 and allowed_profiles")
    if calls_allowed is False and (max_calls != 0 or allowed_profiles):
        raise ValueError("provider calls disabled requires max_calls=0 and empty allowed_profiles")
    if calls_allowed not in {True, False}:
        raise ValueError("provider_policy.provider_calls_allowed must be boolean")


def validate(data: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS.difference(data))
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if data["task_type"] not in TASK_TYPES:
        raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)}")
    if data["handoff_mode"] not in HANDOFF_MODES:
        raise ValueError(f"handoff_mode must be one of {sorted(HANDOFF_MODES)}")
    if data["base_branch"] != "develop":
        raise ValueError("base_branch must be develop")
    branch = data["branch"]
    if not isinstance(branch, str) or not branch.startswith("task/"):
        raise ValueError("branch must start with task/")
    if branch in {"main", "develop"}:
        raise ValueError("worker branch must not be main or develop")
    if not isinstance(data["worktree"], str) or not data["worktree"].strip():
        raise ValueError("worktree must be a non-empty string")
    if not isinstance(data["objective"], str) or not data["objective"].strip():
        raise ValueError("objective must be a non-empty string")

    readings = set(_as_string_list(data, "required_reading"))
    missing_readings = sorted(REQUIRED_READINGS.difference(readings))
    if missing_readings:
        raise ValueError(f"required_reading missing baseline docs: {missing_readings}")

    reporting = set(_as_string_list(data, "reporting_requirements"))
    missing_reporting = sorted(REQUIRED_REPORTING.difference(reporting))
    if missing_reporting:
        raise ValueError(f"reporting_requirements missing fields: {missing_reporting}")

    _validate_paths(data)
    _validate_commands(data)
    _validate_safety(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_pack", type=Path)
    args = parser.parse_args()
    try:
        data = _load(args.task_pack)
        validate(data)
    except Exception as exc:  # noqa: BLE001 - CLI validator should print concise failures.
        print(f"worker task pack validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"worker task pack validation passed: {args.task_pack}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
