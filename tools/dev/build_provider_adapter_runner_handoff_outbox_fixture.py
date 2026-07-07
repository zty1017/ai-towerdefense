#!/usr/bin/env python3
"""Build the provider runner handoff outbox fixture used by acceptance profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.services.generation_scheduler_handoff_builders import (  # noqa: E402
    build_provider_adapter_runner_handoff,
    build_provider_adapter_runner_handoff_outbox,
)


DEFAULT_REQUEST = ROOT / "examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json"
DEFAULT_AUTHORIZATION = (
    ROOT / "examples/provider_authorizations/p1b_provider_execution_authorization.example.json"
)
DEFAULT_OUTPUT = Path("/tmp/provider_runner_handoff_outbox_consumer_fixture.v0.1.json")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_fixture(args: argparse.Namespace) -> dict[str, Any]:
    request = load_json(args.executor_request)
    authorization = load_json(args.authorization)
    source = request.get("source")
    if not isinstance(source, dict):
        raise ValueError("executor request source must be an object")
    authorization_source = authorization.get("source")
    if not isinstance(authorization_source, dict):
        raise ValueError("authorization source must be an object")

    handoff = build_provider_adapter_runner_handoff(
        session_id=source["session_id"],
        run_id=source["run_id"],
        schedule_item_id=source["schedule_item_id"],
        authorization_ref=authorization["authorization_ref"],
        executor_request_id=request["request_id"],
        executor_request=request,
        authorization=authorization,
        provider_profile=authorization_source["provider_profile"],
        created_at=args.created_at,
        note=args.note,
    )
    return build_provider_adapter_runner_handoff_outbox(
        session_id=source["session_id"],
        run_id=source["run_id"],
        worker_id=args.worker_id,
        max_items=1,
        dispatched_count=1,
        stop_reason=args.stop_reason,
        runner_handoffs=[handoff],
        created_at=args.created_at,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--created-at", default="2026-07-07T00:00:00+00:00")
    parser.add_argument("--worker-id", default="outbox-consumer-acceptance")
    parser.add_argument("--stop-reason", default="acceptance_fixture")
    parser.add_argument("--note", default="outbox consumer acceptance fixture")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        outbox = build_fixture(args)
        write_json(args.output, outbox)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"provider runner handoff outbox fixture build failed: {exc}", file=sys.stderr)
        return 1
    print(f"provider runner handoff outbox fixture written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
