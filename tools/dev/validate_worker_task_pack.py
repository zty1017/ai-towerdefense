#!/usr/bin/env python3
"""Validate WorkerTaskPack v0.1 files using only the Python standard library."""

from __future__ import annotations

import argparse
import json
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


def _as_string_list(data: dict[str, Any], field: str) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not contain duplicates")
    return value


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


def _validate_commands(data: dict[str, Any]) -> None:
    commands = _as_string_list(data, "acceptance_commands")
    for command in commands:
        lowered = command.lower()
        for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
            if fragment in lowered:
                raise ValueError(f"acceptance_commands contains forbidden command fragment: {fragment}")


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
