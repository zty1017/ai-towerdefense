#!/usr/bin/env python3
"""Run a WorkerTaskPack acceptance_profile without invoking a shell."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso, run_command
from tools.dev.validate_worker_task_pack import validate


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_run_report.v0.1"
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_run_report.v0.1.json")
OUTPUT_TAIL_LIMIT = 1200
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_ONLY_EXACT_TOKENS = {"&&", "||"}
SHELL_ONLY_PIPE_TOKENS = {"|", "|&"}
SHELL_ONLY_TOKEN_CHARS = {"<", ">", ";"}
SHELL_ONLY_SUBSTRINGS = ("`", "$(")


@dataclass(frozen=True)
class ParsedCommand:
    argv: list[str]
    env: dict[str, str]


class UnsupportedCommandSyntax(ValueError):
    """Raised when an acceptance command requires shell parsing."""


def load_task_pack(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("WorkerTaskPack root must be an object")
    validate(data)
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def parse_command(command: str) -> ParsedCommand:
    for marker in SHELL_ONLY_SUBSTRINGS:
        if marker in command:
            raise UnsupportedCommandSyntax(
                f"unsupported shell-only syntax marker {marker!r}"
            )
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise UnsupportedCommandSyntax(f"unable to parse command with shlex: {exc}") from exc
    if not tokens:
        raise UnsupportedCommandSyntax("command is empty")

    for token in tokens:
        if token in SHELL_ONLY_EXACT_TOKENS or token in SHELL_ONLY_PIPE_TOKENS:
            raise UnsupportedCommandSyntax(
                f"unsupported shell-only syntax token {token!r}"
            )
        for marker in SHELL_ONLY_TOKEN_CHARS:
            if marker in token:
                raise UnsupportedCommandSyntax(
                    f"unsupported shell-only syntax token {token!r}"
                )

    env: dict[str, str] = {}
    argv_start = 0
    while argv_start < len(tokens) and ENV_ASSIGNMENT_RE.match(tokens[argv_start]):
        key, value = tokens[argv_start].split("=", 1)
        env[key] = value
        argv_start += 1
    argv = tokens[argv_start:]
    if not argv:
        raise UnsupportedCommandSyntax("command has environment assignments but no executable")
    return ParsedCommand(argv=argv, env=env)


def empty_report(
    *,
    task_pack: Path,
    selected_profile: str | None,
    default_profile: str | None,
    available_profiles: list[str],
    status: str,
    fail_fast: bool,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    actual_results = results or []
    passed = sum(1 for item in actual_results if item.get("status") == "passed")
    failed = sum(1 for item in actual_results if item.get("status") == "failed")
    dry_run = sum(1 for item in actual_results if item.get("status") == "dry_run")
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "task_pack": str(task_pack),
        "selected_profile": selected_profile,
        "default_profile": default_profile,
        "available_profiles": available_profiles,
        "status": status,
        "summary": {
            "command_count": len(actual_results),
            "pass": passed,
            "fail": failed,
            "dry_run": dry_run,
            "fail_fast": bool(fail_fast),
        },
        "results": actual_results,
    }


def profile_metadata(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    acceptance_profile = data.get("acceptance_profile")
    if not isinstance(acceptance_profile, dict):
        raise ValueError(
            "task pack does not define acceptance_profile; old packages need "
            "manual acceptance_commands"
        )
    default_profile = acceptance_profile["default_profile"]
    profiles = acceptance_profile["profiles"]
    return str(default_profile), profiles


def list_profiles(task_pack: Path, default_profile: str, profiles: dict[str, Any]) -> None:
    print(f"profiles for {task_pack} (default: {default_profile})")
    for profile_id in sorted(profiles):
        marker = "*" if profile_id == default_profile else "-"
        profile = profiles[profile_id]
        required_for = ", ".join(profile.get("required_for", []))
        description = profile.get("description", "")
        print(f"{marker} {profile_id}: {description}")
        print(f"  required_for: {required_for}")
        print(f"  command_count: {len(profile.get('commands', []))}")


def build_result_for_unsupported(
    *,
    index: int,
    command: str,
    error: Exception,
) -> dict[str, Any]:
    return {
        "name": f"command_{index}",
        "command": command,
        "argv": [],
        "env": {},
        "elapsed_seconds": 0,
        "return_code": None,
        "status": "failed",
        "error": "unsupported_command_syntax",
        "message": str(error),
    }


def build_result_for_dry_run(
    *,
    index: int,
    command: str,
    parsed: ParsedCommand,
) -> dict[str, Any]:
    return {
        "name": f"command_{index}",
        "command": command,
        "argv": parsed.argv,
        "env": parsed.env,
        "elapsed_seconds": 0,
        "return_code": None,
        "status": "dry_run",
    }


def run_profile_commands(
    *,
    command_strings: list[str],
    dry_run: bool,
    fail_fast: bool,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, command in enumerate(command_strings, start=1):
        try:
            parsed = parse_command(command)
        except UnsupportedCommandSyntax as exc:
            result = build_result_for_unsupported(index=index, command=command, error=exc)
            results.append(result)
            print(f"FAIL command_{index}: {exc}", file=sys.stderr)
            if fail_fast:
                break
            continue

        if dry_run:
            result = build_result_for_dry_run(index=index, command=command, parsed=parsed)
            results.append(result)
            print(f"DRY command_{index}: {command}")
            continue

        result = run_command(
            f"command_{index}",
            parsed.argv,
            root=ROOT,
            timeout_seconds=timeout_seconds,
            output_tail_limit=OUTPUT_TAIL_LIMIT,
            env=parsed.env,
        )
        result["command"] = command
        result["argv"] = parsed.argv
        result["env"] = parsed.env
        results.append(result)
        status_icon = "OK" if result["status"] == "passed" else "FAIL"
        print(f"{status_icon} command_{index} ({result['elapsed_seconds']}s)")
        if fail_fast and result["status"] != "passed":
            break
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_pack", type=Path)
    parser.add_argument(
        "--profile",
        help="Acceptance profile id to run. Defaults to acceptance_profile.default_profile.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit without running commands.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print commands without executing them.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Write a structured runner report to this path.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failed or unsupported command.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-command timeout in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_pack = args.task_pack if args.task_pack.is_absolute() else ROOT / args.task_pack
    try:
        data = load_task_pack(task_pack)
        default_profile, profiles = profile_metadata(data)
    except Exception as exc:  # noqa: BLE001 - CLI should report concise failures.
        report = empty_report(
            task_pack=task_pack,
            selected_profile=args.profile,
            default_profile=None,
            available_profiles=[],
            status="failed",
            fail_fast=args.fail_fast,
            results=[
                {
                    "name": "task_pack_validation",
                    "command": str(task_pack),
                    "status": "failed",
                    "error": "task_pack_validation_failed",
                    "message": str(exc),
                }
            ],
        )
        write_json(args.output, report)
        print(f"worker acceptance profile failed: {exc}", file=sys.stderr)
        print(f"worker acceptance profile report: {args.output}")
        return 1

    available_profiles = sorted(str(profile_id) for profile_id in profiles)
    if args.list_profiles:
        list_profiles(task_pack, default_profile, profiles)
        return 0

    selected_profile = args.profile or default_profile
    if selected_profile not in profiles:
        message = (
            f"acceptance profile {selected_profile!r} not found; available profiles: "
            f"{available_profiles}"
        )
        report = empty_report(
            task_pack=task_pack,
            selected_profile=selected_profile,
            default_profile=default_profile,
            available_profiles=available_profiles,
            status="failed",
            fail_fast=args.fail_fast,
            results=[
                {
                    "name": "profile_selection",
                    "command": selected_profile,
                    "status": "failed",
                    "error": "profile_not_found",
                    "message": message,
                }
            ],
        )
        write_json(args.output, report)
        print(f"worker acceptance profile failed: {message}", file=sys.stderr)
        print(f"worker acceptance profile report: {args.output}")
        return 1

    profile = profiles[selected_profile]
    command_strings = list(profile["commands"])
    results = run_profile_commands(
        command_strings=command_strings,
        dry_run=bool(args.dry_run),
        fail_fast=bool(args.fail_fast),
        timeout_seconds=int(args.timeout),
    )
    failed = [item for item in results if item.get("status") == "failed"]
    status = "failed" if failed else "dry_run" if args.dry_run else "passed"
    report = empty_report(
        task_pack=task_pack,
        selected_profile=selected_profile,
        default_profile=default_profile,
        available_profiles=available_profiles,
        status=status,
        fail_fast=args.fail_fast,
        results=results,
    )
    report["summary"]["configured_command_count"] = len(command_strings)
    write_json(args.output, report)
    print(f"worker acceptance profile report: {args.output}")
    if failed:
        for item in failed:
            print(f"failed: {item['name']} {item.get('message', '')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
