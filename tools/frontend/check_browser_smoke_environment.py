#!/usr/bin/env python3
"""Check whether browser-based frontend smoke tests can run locally.

This preflight only discovers a Chromium-compatible executable. It does not
launch a browser, open sockets, call providers, read .env, or write runtime
artifacts. The heavier screenshot tools still perform the real browser run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.frontend.capture_frontend_flow_visual_smoke import (  # noqa: E402
    browser_candidates,
    find_browser,
)


SCHEMA_VERSION = "browser_smoke_environment_report.v0.1"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def build_report(browser_bin: str | None) -> dict[str, Any]:
    candidates = browser_candidates(browser_bin)
    browser = find_browser(browser_bin)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "available" if browser else "browser_unavailable",
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "candidate_count": len(candidates),
        "candidate_path_count": len([item for item in candidates if item.get("path")]),
        "purpose": "Preflight for frontend browser visual smoke tools.",
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "runtime_activation_allowed": False,
            "stores_provider_body": False,
            "launches_browser": False,
            "opens_socket": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser-bin", help="Path or command name for a Chromium-compatible browser.")
    parser.add_argument("--allow-missing-browser", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.browser_bin)
    write_json(args.output, report)
    print(f"browser smoke environment {report['status']}: {args.output}")
    if report["status"] == "available" or args.allow_missing_browser:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
