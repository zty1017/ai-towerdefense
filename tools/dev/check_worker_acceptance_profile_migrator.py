#!/usr/bin/env python3
"""Smoke-check WorkerTaskPack acceptance_profile migration in a temp dir."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso  # noqa: E402
from tools.dev.migrate_worker_acceptance_profiles import (  # noqa: E402
    build_report,
    candidate_paths,
    write_json,
)
from tools.dev.validate_worker_task_pack import validate  # noqa: E402


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_migrator_smoke_report.v0.1"
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_migrator_smoke_report.v0.1.json")
ELIGIBLE_SOURCE = ROOT / "examples/worker_task_packs/p1d_map_v02_preview_api.v0.1.json"
INCOMPATIBLE_SOURCE = (
    ROOT / "examples/worker_task_packs/p1d_demo_suite_outbox_import_smoke.v0.1.json"
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be object")
    return data


def require_tmp_output(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    tmp_root = Path("/tmp").resolve(strict=False)
    if resolved != tmp_root and tmp_root not in resolved.parents:
        raise ValueError("--output must be under /tmp")
    return resolved


def prepare_fixture_dir(root: Path) -> tuple[Path, Path]:
    eligible = root / "eligible.v0.1.json"
    incompatible = root / "incompatible.v0.1.json"

    eligible_data = load_json(ELIGIBLE_SOURCE)
    eligible_data.pop("acceptance_profile", None)
    write_json(eligible, eligible_data)
    shutil.copyfile(INCOMPATIBLE_SOURCE, incompatible)
    return eligible, incompatible


def assert_profile_valid(path: Path) -> None:
    data = load_json(path)
    validate(data)
    profile = data.get("acceptance_profile")
    assert isinstance(profile, dict), "eligible fixture was not migrated"
    profiles = profile.get("profiles")
    assert profile.get("default_profile") == "daily_fast"
    assert isinstance(profiles, dict)
    assert set(profiles) == {"daily_fast", "full_evidence"}
    daily_commands = profiles["daily_fast"]["commands"]
    assert daily_commands
    assert not any(
        "tools/demo/export_evidence.py" in command and "--output-dir" in command
        for command in daily_commands
    ), "daily_fast must not include full evidence export"


def assert_incompatible_unchanged(path: Path) -> None:
    data = load_json(path)
    validate(data)
    assert "acceptance_profile" not in data, "incompatible fixture should be skipped"


def run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="worker-profile-migrator-", dir="/tmp") as tmp:
        fixture_dir = Path(tmp)
        eligible, incompatible = prepare_fixture_dir(fixture_dir)
        paths = candidate_paths(
            task_pack_dir=fixture_dir,
            task_packs=[],
            include_prefixes=[],
        )
        assert sorted(path.name for path in paths) == ["eligible.v0.1.json", "incompatible.v0.1.json"]

        dry_report = build_report(paths=paths, write=False, limit=None)
        write_report = build_report(paths=paths, write=True, limit=None)
        assert_profile_valid(eligible)
        assert_incompatible_unchanged(incompatible)

    assert dry_report["summary"]["would_migrate_count"] == 1
    assert dry_report["summary"]["skipped_count"] == 1
    assert write_report["summary"]["migrated_count"] == 1
    assert write_report["summary"]["skipped_count"] == 1
    assert write_report["summary"]["runner_incompatible_skip_count"] == 1
    assert write_report["safety_summary"]["acceptance_commands_executed"] is False
    assert write_report["safety_summary"]["provider_call_count"] == 0

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "status": "passed",
        "dry_run_summary": dry_report["summary"],
        "write_summary": write_report["summary"],
        "safety_summary": write_report["safety_summary"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = require_tmp_output(args.output)
        report = run_smoke()
        write_json(output, report)
    except Exception as exc:  # noqa: BLE001 - smoke should print concise failure.
        print(f"worker acceptance profile migrator smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"worker acceptance profile migrator smoke passed: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
