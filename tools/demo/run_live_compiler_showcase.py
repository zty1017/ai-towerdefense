#!/usr/bin/env python3
"""Run redacted live-provider showcase cases for three runtime object kinds."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
DEV_TOOLS = ROOT / "tools" / "dev"
for path in (ROOT, BACKEND_ROOT, DEV_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from report_io import write_json  # noqa: E402


SCHEMA_VERSION = "live_compiler_showcase_report.v0.1"
REPORT_ID = "live_compiler_showcase_report_v0_1"
CASES = (
    {
        "case_id": "chain_tower",
        "expected_asset_kind": "tower_blueprint",
        "required_effect_kinds": {"damage"},
        "intent": "用铜镜和导光纹做一座命中后向附近两个敌人跳跃的防御塔。",
    },
    {
        "case_id": "slow_trap",
        "expected_asset_kind": "temporary_trap_sample",
        "required_effect_kinds": {"damage", "slow"},
        "intent": "制作一枚地面绊索陷阱，触发时造成小范围震荡伤害，并使踏入范围的敌人持续减速。",
    },
    {
        "case_id": "support_field",
        "expected_asset_kind": "support_item",
        "required_effect_kinds": {"damage", "slow"},
        "intent": "制作一个支援脉冲，在落点释放一次小范围震荡，并形成持续减速的迟滞场。",
    },
)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require_response(response: Any, expected_status: int, step: str) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise RuntimeError(f"{step} returned HTTP {response.status_code}")
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"{step} returned a non-object response")
    return body


def job_failure_summary(job: dict[str, Any]) -> str:
    summaries: list[str] = []
    for raw_path in as_list(job.get("trace_paths")):
        path = Path(str(raw_path))
        if not path.is_file():
            continue
        try:
            trace = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(trace, dict) or trace.get("status") == "passed":
            continue
        failed_runs = [
            run
            for run in as_list(trace.get("node_runs"))
            if isinstance(run, dict) and run.get("status") == "failed"
        ]
        for run in failed_runs:
            errors = " | ".join(str(item) for item in as_list(run.get("errors")))
            summaries.append(
                f"{trace.get('workflow_id')}:{run.get('node_id')}:{errors[:240]}"
            )
    return "; ".join(summaries) or "no failed node summary"


def activated_capability(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = as_obj(body.get("activation_receipt"))
    activated_ids = {
        str(item)
        for item in as_list(as_obj(receipt.get("runtime_effect")).get("activated_object_ids"))
    }
    bundle = as_obj(body.get("activated_runtime_bundle"))
    capabilities = as_list(as_obj(bundle.get("capabilities")).get("battle_objects"))
    capability = next(
        (
            item
            for item in capabilities
            if isinstance(item, dict) and str(item.get("object_id")) in activated_ids
        ),
        None,
    )
    if not isinstance(capability, dict):
        raise RuntimeError("activated capability was not projected into the runtime bundle")
    return receipt, capability


def run_case(client: Any, case: dict[str, Any], max_attempts: int) -> dict[str, Any]:
    failures: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            session = require_response(client.post("/api/sessions"), 201, "create_session")
            session_id = str(session["session_id"])
            proposal_started = time.monotonic()
            proposal = require_response(
                client.post(
                    f"/api/sessions/{session_id}/research/proposals",
                    json={"intent_text": case["intent"], "node_id": "gray_lantern_station"},
                ),
                201,
                "create_proposal",
            )
            proposal_seconds = time.monotonic() - proposal_started
            generation = as_obj(as_obj(proposal.get("compiler_metadata")).get("generation"))
            if generation.get("mode") != "live" or generation.get("provider_call_performed") is not True:
                raise RuntimeError(
                    f"provider candidate unavailable: {generation.get('fallback_reason') or 'unknown'}"
                )
            compiled_object = as_obj(as_obj(proposal.get("compiler_metadata")).get("compiled_object"))
            if compiled_object.get("candidate_kind") != case["expected_asset_kind"]:
                raise RuntimeError("intent classification did not produce the expected runtime kind")
            candidate = as_obj(proposal.get("compiled_candidate"))
            candidate_gameplay = as_obj(candidate.get("gameplay"))
            candidate_effect_types = [
                str(as_obj(item).get("type"))
                for item in as_list(candidate_gameplay.get("effect_blocks"))
            ]

            job_started = time.monotonic()
            job = require_response(
                client.post(
                    f"/api/sessions/{session_id}/research/proposals/{proposal['proposal_id']}/confirm"
                ),
                200,
                "confirm_proposal",
            )
            if job.get("status") != "completed":
                raise RuntimeError(
                    f"research job ended as {job.get('status')} with effects "
                    f"{candidate_effect_types}: {job_failure_summary(job)}"
                )
            activation = require_response(
                client.post(
                    f"/api/sessions/{session_id}/research/jobs/{job['job_id']}/activate"
                ),
                200,
                "activate_job",
            )
            job_seconds = time.monotonic() - job_started
            receipt, capability = activated_capability(activation)
            behavior = as_obj(capability.get("behavior_abi"))
            effects = [as_obj(item) for item in as_list(behavior.get("effect_blocks"))]
            effect_kinds = {str(item.get("kind")) for item in effects}
            if not case["required_effect_kinds"].issubset(effect_kinds):
                raise RuntimeError(
                    f"runtime behavior lacks required effects: {sorted(case['required_effect_kinds'])}"
                )
            if case["case_id"] == "chain_tower":
                damage_effect = next(
                    (item for item in effects if item.get("kind") == "damage"), {}
                )
                if int(damage_effect.get("max_targets") or 1) < 2:
                    raise RuntimeError("runtime tower did not retain multi-target chain behavior")
            validation = as_obj(receipt.get("validation"))
            if as_obj(validation.get("behavior_abi")).get("status") != "passed":
                raise RuntimeError("behavior ABI gate did not pass")
            if as_obj(receipt.get("promotion")).get("status") != "passed":
                raise RuntimeError("provider promotion gate did not pass")

            runtime_refs = as_obj(as_obj(job.get("compiler_metadata")).get("runtime_refs"))
            return {
                "case_id": case["case_id"],
                "status": "passed",
                "attempt_count": attempt,
                "expected_asset_kind": case["expected_asset_kind"],
                "candidate_asset_type": candidate_gameplay.get("asset_type"),
                "candidate_id": candidate.get("id"),
                "display_name": proposal.get("display_name"),
                "generation": {
                    "mode": generation.get("mode"),
                    "profile": generation.get("profile"),
                    "model": generation.get("model"),
                    "provider_call_performed": True,
                    "raw_prompt_stored": generation.get("raw_prompt_stored") is True,
                    "raw_response_stored": generation.get("raw_response_stored") is True,
                },
                "timing_seconds": {
                    "proposal": round(proposal_seconds, 2),
                    "confirm_and_activation": round(job_seconds, 2),
                    "total": round(proposal_seconds + job_seconds, 2),
                },
                "candidate_effect_types": candidate_effect_types,
                "runtime_object_id": capability.get("object_id"),
                "runtime_asset_kind": capability.get("asset_kind"),
                "runtime_effect_kinds": sorted(effect_kinds),
                "behavior_abi": behavior,
                "gates": {
                    "package_schema": as_obj(validation.get("package_schema")).get("status"),
                    "runtime_safety": as_obj(validation.get("runtime_safety")).get("status"),
                    "semantic": as_obj(validation.get("semantic")).get("status"),
                    "behavior_abi": as_obj(validation.get("behavior_abi")).get("status"),
                    "media": as_obj(validation.get("media")).get("status"),
                    "promotion": as_obj(receipt.get("promotion")).get("status"),
                },
                "evidence": {
                    "trace_count": int(runtime_refs.get("trace_count") or 0),
                    "promotion_report_present": bool(runtime_refs.get("promotion_report_path")),
                    "runtime_package_present": bool(runtime_refs.get("runtime_package_path")),
                },
                "runtime_mutation_count": int(
                    as_obj(receipt.get("safety")).get("player_runtime_mutation_count") or 0
                ),
                "previous_attempt_failures": failures,
            }
        except Exception as exc:  # noqa: BLE001 - each provider attempt is isolated.
            failures.append(f"{type(exc).__name__}: {str(exc)[:180]}")
    return {
        "case_id": case["case_id"],
        "status": "failed",
        "attempt_count": max_attempts,
        "expected_asset_kind": case["expected_asset_kind"],
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dotenv", required=True, type=Path)
    parser.add_argument("--profile", default="ark_deepseek_v4_flash")
    parser.add_argument("--media-mode", choices=("off", "auto", "live"), default="off")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument(
        "--case",
        action="append",
        choices=tuple(str(item["case_id"]) for item in CASES),
        help="Run only selected cases; repeat the option for more than one.",
    )
    parser.add_argument(
        "--allow-provider",
        action="store_true",
        help="Required acknowledgement that the three cases call an external provider.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.allow_provider:
        raise SystemExit("ERROR: --allow-provider is required")
    if args.max_attempts < 1 or args.max_attempts > 3:
        raise SystemExit("ERROR: --max-attempts must be in [1, 3]")
    if not args.dotenv.is_file():
        raise SystemExit(f"ERROR: dotenv not found: {args.dotenv}")

    started = time.monotonic()
    generated_at = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="ai_td_live_showcase_") as temp_dir:
        os.environ.update(
            {
                "APP_DB_PATH": str(Path(temp_dir) / "showcase.db"),
                "AI_TD_ENV_FILE": str(args.dotenv.resolve()),
                "AI_TD_LIVE_COMPILATION": "live",
                "AI_TD_LIVE_MEDIA": args.media_mode,
                "AI_TD_LLM_PROFILE": args.profile,
                "AI_TD_RESEARCH_WORKER_MODE": "inline",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        from fastapi.testclient import TestClient
        from app.main import app

        selected = [
            case for case in CASES if not args.case or case["case_id"] in set(args.case)
        ]
        with TestClient(app) as client:
            cases = [run_case(client, case, args.max_attempts) for case in selected]

    passed_count = sum(case.get("status") == "passed" for case in cases)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": REPORT_ID,
        "generated_at": generated_at,
        "status": "passed" if passed_count == len(cases) else "failed",
        "execution_mode": "live_provider_inline_research_worker",
        "media_mode": args.media_mode,
        "case_count": len(cases),
        "passed_count": passed_count,
        "failed_count": len(cases) - passed_count,
        "total_seconds": round(time.monotonic() - started, 2),
        "cases": cases,
        "safety_summary": {
            "runner_reads_dotenv": True,
            "successful_provider_call_count": passed_count,
            "stores_raw_prompt": any(
                as_obj(case.get("generation")).get("raw_prompt_stored") is True
                for case in cases
            ),
            "stores_raw_response": any(
                as_obj(case.get("generation")).get("raw_response_stored") is True
                for case in cases
            ),
            "runtime_mutation_count": sum(
                int(case.get("runtime_mutation_count") or 0) for case in cases
            ),
            "world_state_mutation_count": 0,
        },
    }
    write_json(args.output, report)
    print(
        f"{report['status'].upper()} live compiler showcase: "
        f"{passed_count}/{len(cases)} cases, report={args.output}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
