#!/usr/bin/env python3
"""Smoke-check the Generation Scheduler review-only backend pipeline.

The script starts a temporary local backend, walks the guarded scheduler worker
chain over HTTP, and writes a redacted review report. It deliberately uses only
fixture-backed endpoints: no `.env` reads, no provider calls, no world writes
outside the temporary SQLite database, and no runtime activation.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FORBIDDEN_KEYS = {
    "raw_prompt",
    "provider_response",
    "provider_body",
    "api_key",
    "secret",
}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(walk_keys(item))
    return keys


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with NO_PROXY_OPENER.open(request, timeout=30) as response:
            status = response.status
            payload_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload_text = exc.read().decode("utf-8")
    if status != expected_status:
        raise AssertionError(
            f"{method} {path}: expected {expected_status}, got {status}: {payload_text[:500]}"
        )
    return json.loads(payload_text) if payload_text else {}


def wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 45
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate(timeout=2)
            raise RuntimeError(f"uvicorn exited early\nSTDOUT:\n{out}\nSTDERR:\n{err}")
        try:
            body = request_json(base_url, "GET", "/api/health")
            if body.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - startup polling.
            last_error = str(exc)
            time.sleep(0.25)
    raise TimeoutError(f"uvicorn did not become ready: {last_error}")


def payload(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("mode") != "frontend_mock_fixture":
        raise AssertionError(f"unexpected response mode: {body.get('mode')}")
    return as_obj(body.get("payload"))


def scrub_session_path(path: str) -> str:
    parts = path.split("/")
    if len(parts) > 3 and parts[1] == "api" and parts[2] == "sessions":
        parts[3] = "{session_id}"
    return "/".join(parts)


class ApiRecorder:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.steps: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        expected_status: int = 200,
        payload_response: bool = True,
        step_id: str,
    ) -> dict[str, Any]:
        response = request_json(self.base_url, method, path, body, expected_status)
        self.steps.append(
            {
                "step_id": step_id,
                "method": method,
                "endpoint_template": scrub_session_path(path),
                "status_code": expected_status,
                "passed": True,
            }
        )
        return payload(response) if payload_response else response


def assert_zero_safety(summary: dict[str, Any], *, label: str) -> None:
    checks = {
        "provider_call_count_by_this_request": 0,
        "world_mutation_count_by_this_request": 0,
        "activation_allowed_count": 0,
    }
    for key, expected in checks.items():
        if int(summary.get(key) or 0) != expected:
            raise AssertionError(f"{label}: {key} expected {expected}, got {summary.get(key)}")


def create_session(recorder: ApiRecorder, display_name: str, step_id: str) -> str:
    session = recorder.request(
        "POST",
        "/api/sessions",
        body={"display_name": display_name},
        expected_status=201,
        payload_response=False,
        step_id=step_id,
    )
    return str(session["session_id"])


def run_fixture_chain(
    recorder: ApiRecorder,
    session_id: str,
    *,
    artifact_profile: str,
    worker_id: str,
    step_id: str,
) -> dict[str, Any]:
    chain = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/generation-schedule/workers/run-fixture-executor-chain",
        body={
            "worker_id": worker_id,
            "artifact_profile": artifact_profile,
            "note": "generation scheduler review-only pipeline smoke",
        },
        step_id=step_id,
    )
    executor_chain = as_obj(chain.get("executor_chain"))
    if executor_chain.get("status") != "completed_review_only_promotion_blocked":
        raise AssertionError(f"{step_id}: unexpected executor chain status")
    if executor_chain.get("artifact_profile") != artifact_profile:
        raise AssertionError(f"{step_id}: artifact profile mismatch")
    if int(executor_chain.get("provider_call_count") or 0) != 0:
        raise AssertionError(f"{step_id}: provider call count must be 0")
    if int(executor_chain.get("world_mutation_count") or 0) != 0:
        raise AssertionError(f"{step_id}: world mutation count must be 0")
    if int(executor_chain.get("activation_allowed_count") or 0) != 0:
        raise AssertionError(f"{step_id}: activation allowed count must be 0")
    ledger_summary = as_obj(as_obj(chain.get("generation_artifact_ledger")).get("summary"))
    assert_zero_safety(ledger_summary, label=step_id)
    return chain


def get_prefetch_cache(recorder: ApiRecorder, session_id: str, step_id: str) -> dict[str, Any]:
    data = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/generation-schedule/prefetch-cache",
        step_id=step_id,
    )
    summary = as_obj(as_obj(data.get("generation_prefetch_cache")).get("summary"))
    assert_zero_safety(summary, label=step_id)
    return data


def get_activation_gate(recorder: ApiRecorder, session_id: str, step_id: str) -> dict[str, Any]:
    data = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/generation-schedule/activation-gate",
        step_id=step_id,
    )
    summary = as_obj(as_obj(data.get("generation_activation_gate")).get("summary"))
    if int(summary.get("activation_allowed_count") or 0) != 0:
        raise AssertionError(f"{step_id}: activation_allowed_count must be 0")
    if int(summary.get("runtime_ready_count") or 0) != 0:
        raise AssertionError(f"{step_id}: runtime_ready_count must be 0")
    return data


def index_shared_cache(recorder: ApiRecorder, session_id: str, step_id: str) -> dict[str, Any]:
    data = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/generation-schedule/workers/index-shared-prefetch-cache",
        step_id=step_id,
    )
    index_summary = as_obj(data.get("shared_prefetch_cache_index"))
    if int(index_summary.get("provider_call_count") or 0) != 0:
        raise AssertionError(f"{step_id}: provider_call_count must be 0")
    if int(index_summary.get("world_mutation_count") or 0) != 0:
        raise AssertionError(f"{step_id}: world_mutation_count must be 0")
    if int(index_summary.get("activation_allowed_count") or 0) != 0:
        raise AssertionError(f"{step_id}: activation_allowed_count must be 0")
    return data


def assert_no_forbidden_keys(value: Any, *, label: str) -> None:
    present = sorted(set(walk_keys(value)).intersection(FORBIDDEN_KEYS))
    if present:
        raise AssertionError(f"{label}: forbidden keys leaked: {present}")


def seed_promotion_allowed_ledger(
    *,
    db_path: Path,
    session_id: str,
    run_id: str,
    schedule_item_id: str,
) -> None:
    """Seed a promotion-allowed ledger entry inside the temporary smoke DB."""

    ts = "2026-07-07T00:00:00+00:00"
    source_id = "ppromo_pipeline_runtime_readiness_chain"
    payload = {
        "schema_version": "generation_artifact_ledger_entry.v0.1",
        "ledger_id": f"gled_{session_id}_provider_artifact_promotion_report_{source_id}",
        "run_id": run_id,
        "session_id": session_id,
        "schedule_item_id": schedule_item_id,
        "artifact_kind": "provider_artifact_promotion_report",
        "source_id": source_id,
        "status": "promotion_allowed",
        "worker_id": "pipeline-smoke-promotion-seed",
        "note": "temporary smoke DB seed for readiness chain coverage",
        "created_at": ts,
        "updated_at": ts,
        "provider_call_performed_by_this_request": False,
        "world_mutation_performed_by_this_request": False,
        "activation_allowed_now": False,
        "ledger_write_policy": {
            "mode": "fixture_backed_review_only",
            "reads_env": False,
            "calls_provider": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
            "writes_world_state": False,
        },
        "compact": {
            "promotion_allowed": True,
            "promotion_decision": "approved_for_runtime_package_build",
            "required_next_actions": ["runtime_package_build"],
            "promotion_gate": {
                "promotion_allowed": True,
                "blocked_reason": None,
                "required_next_gates": [],
            },
            "promotion_targets": {
                "target_kind": "map_runtime_package",
                "runtime_package_ref_count": 0,
                "world_transaction_ref_count": 0,
                "published_media_ref_count": 0,
            },
            "safety_summary": {
                "provider_call_count_by_report": 0,
                "world_mutation_count_by_report": 0,
                "runtime_mutation_count_by_report": 0,
                "stores_prompt_body": False,
                "stores_provider_body": False,
                "stores_sensitive_value": False,
                "uses_temporary_url": False,
            },
        },
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            "INSERT INTO generation_artifact_ledger "
            "(ledger_id, run_id, session_id, schedule_item_id, artifact_kind, status, "
            "payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(ledger_id) DO UPDATE SET payload = excluded.payload, "
            "status = excluded.status, updated_at = excluded.updated_at",
            (
                payload["ledger_id"],
                payload["run_id"],
                payload["session_id"],
                payload["schedule_item_id"],
                payload["artifact_kind"],
                payload["status"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        conn.commit()


def run_background_handoff_tick(
    recorder: ApiRecorder,
    session_id: str,
    step_id: str,
) -> dict[str, Any]:
    data = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/generation-schedule/workers/"
        "run-review-only-background-handoff-tick",
        body={
            "worker_id": "pipeline-smoke-background-handoff",
            "note": "generation scheduler review-only pipeline smoke",
        },
        step_id=step_id,
    )
    worker_step = as_obj(data.get("worker_step"))
    expected_step = {
        "status": "handoff_tick_exported",
        "worker_mode": "review_only_background_handoff_tick",
        "max_items": 2,
        "dispatched_count": 2,
        "runner_handoff_count": 2,
        "stop_reason": "budget_exhausted",
        "provider_call_count": 0,
        "world_mutation_count": 0,
        "activation_allowed_count": 0,
        "promotion_allowed_count": 0,
        "staging_performed": False,
        "promotion_performed": False,
        "queue_completed_count": 0,
    }
    for key, expected in expected_step.items():
        if worker_step.get(key) != expected:
            raise AssertionError(
                f"{step_id}: worker_step.{key} expected {expected!r}, got {worker_step.get(key)!r}"
            )

    background_handoff = as_obj(data.get("background_handoff_tick"))
    if background_handoff.get("tick_mode") != "review_only_background_handoff_tick":
        raise AssertionError(f"{step_id}: background handoff tick mode mismatch")
    if background_handoff.get("handoff_mode") != "external_runner_required":
        raise AssertionError(f"{step_id}: handoff mode mismatch")
    safety = as_obj(background_handoff.get("safety"))
    expected_false = (
        "api_reads_env",
        "api_calls_provider",
        "api_runs_provider_adapter",
        "api_stages_provider_artifacts",
        "api_promotes_provider_artifacts",
        "api_completes_queue_items",
        "api_writes_world_state",
        "api_activates_runtime",
        "prompt_body_included",
        "provider_response_body_included",
    )
    for key in expected_false:
        if safety.get(key) is not False:
            raise AssertionError(f"{step_id}: background_handoff_tick.safety.{key} must be false")
    if safety.get("live_templates_require_external_explicit_authorization") is not True:
        raise AssertionError(
            f"{step_id}: live templates must require external explicit authorization"
        )

    handoffs = as_list(data.get("runner_handoffs"))
    if len(handoffs) != 2:
        raise AssertionError(f"{step_id}: expected 2 runner handoffs")
    outbox = as_obj(data.get("provider_adapter_runner_handoff_outbox"))
    if outbox.get("schema_version") != "provider_adapter_runner_handoff_outbox.v0.1":
        raise AssertionError(f"{step_id}: outbox schema mismatch")
    if outbox.get("handoff_mode") != "external_runner_required":
        raise AssertionError(f"{step_id}: outbox handoff mode mismatch")
    if outbox.get("review_only") is not True:
        raise AssertionError(f"{step_id}: outbox must be review-only")
    if outbox.get("runner_handoff_count") != len(handoffs):
        raise AssertionError(f"{step_id}: outbox handoff count mismatch")
    import_contract = as_obj(outbox.get("import_contract"))
    if "import-provider-adapter-runner-output" not in str(import_contract.get("endpoint")):
        raise AssertionError(f"{step_id}: outbox import endpoint mismatch")

    for index, handoff in enumerate(handoffs):
        handoff_obj = as_obj(handoff)
        source = as_obj(handoff_obj.get("source"))
        runner_inputs = as_obj(handoff_obj.get("runner_inputs"))
        executor_request = as_obj(runner_inputs.get("executor_request"))
        authorization = as_obj(runner_inputs.get("provider_execution_authorization"))
        import_body = as_obj(as_obj(handoff_obj.get("import_after_runner")).get("body"))
        schedule_item_id = source.get("schedule_item_id")
        authorization_ref = source.get("authorization_ref")
        if handoff_obj.get("schema_version") != "provider_adapter_runner_handoff.v0.1":
            raise AssertionError(f"{step_id}: handoff[{index}] schema mismatch")
        if handoff_obj.get("handoff_mode") != "external_runner_required":
            raise AssertionError(f"{step_id}: handoff[{index}] mode mismatch")
        if handoff_obj.get("review_only") is not True:
            raise AssertionError(f"{step_id}: handoff[{index}] must be review-only")
        if as_obj(executor_request.get("source")).get("schedule_item_id") != schedule_item_id:
            raise AssertionError(f"{step_id}: handoff[{index}] executor schedule mismatch")
        if authorization.get("authorization_ref") != authorization_ref:
            raise AssertionError(f"{step_id}: handoff[{index}] authorization mismatch")
        if import_body.get("schedule_item_id") != schedule_item_id:
            raise AssertionError(f"{step_id}: handoff[{index}] import schedule mismatch")
        if import_body.get("authorization_ref") != authorization_ref:
            raise AssertionError(f"{step_id}: handoff[{index}] import authorization mismatch")
        command_templates = as_obj(handoff_obj.get("command_templates"))
        video_command = str(command_templates.get("video_boundary") or "")
        if "--mode" not in video_command or "video" not in video_command:
            raise AssertionError(f"{step_id}: handoff[{index}] video boundary missing video mode")
        if "--live" in video_command:
            raise AssertionError(f"{step_id}: handoff[{index}] video boundary must not be live")
        if "<authorized-dotenv-path>" in video_command:
            raise AssertionError(f"{step_id}: handoff[{index}] video boundary must not require dotenv")
        if "--live" not in str(command_templates.get("live_llm_text") or ""):
            raise AssertionError(f"{step_id}: handoff[{index}] live text template must stay explicit")
        if "--live" not in str(command_templates.get("live_image") or ""):
            raise AssertionError(f"{step_id}: handoff[{index}] live image template must stay explicit")

    ledger_summary = as_obj(as_obj(data.get("generation_artifact_ledger")).get("summary"))
    assert_zero_safety(ledger_summary, label=step_id)
    if int(ledger_summary.get("item_count") or 0) != 8:
        raise AssertionError(f"{step_id}: expected 8 ledger entries")
    assert_no_forbidden_keys(data, label=step_id)
    return data


def assert_background_handoff_rejects_unsafe_metadata(
    recorder: ApiRecorder,
    session_id: str,
) -> None:
    targeted = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/generation-schedule/workers/"
        "run-review-only-background-handoff-tick",
        body={
            "worker_id": "pipeline-smoke-handoff-targeted",
            "authorization_ref": "auth_should_not_be_reused",
        },
        expected_status=409,
        payload_response=False,
        step_id="background_handoff_tick_rejects_targeted_metadata",
    )
    if "does not accept targeted metadata" not in str(targeted.get("detail")):
        raise AssertionError("targeted handoff tick rejection detail mismatch")
    too_large = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/generation-schedule/workers/"
        "run-review-only-background-handoff-tick",
        body={"worker_id": "pipeline-smoke-handoff-large", "max_items": 9},
        expected_status=409,
        payload_response=False,
        step_id="background_handoff_tick_rejects_large_batch",
    )
    if "max_items must be between 1 and 8" not in str(too_large.get("detail")):
        raise AssertionError("large handoff tick rejection detail mismatch")


def build_pipeline_report(base_url: str, db_path: Path, generated_at: str) -> dict[str, Any]:
    recorder = ApiRecorder(base_url)
    handoff_session_id = create_session(
        recorder,
        "generation-pipeline-handoff",
        "create_handoff_session",
    )
    handoff_tick = run_background_handoff_tick(
        recorder,
        handoff_session_id,
        "run_background_handoff_tick",
    )
    queue_view = recorder.request(
        "GET",
        f"/api/sessions/{handoff_session_id}/generation-schedule/queue",
        step_id="handoff_session_queue_after_tick",
    )
    worker_cache_view = recorder.request(
        "GET",
        f"/api/sessions/{handoff_session_id}/generation-schedule/worker-cache",
        step_id="handoff_session_worker_cache_after_tick",
    )
    ledger_view = recorder.request(
        "GET",
        f"/api/sessions/{handoff_session_id}/generation-schedule/artifact-ledger",
        step_id="handoff_session_artifact_ledger_after_tick",
    )
    handoff_prefetch = get_prefetch_cache(
        recorder,
        handoff_session_id,
        "handoff_prefetch_cache_after_tick",
    )
    handoff_activation = get_activation_gate(
        recorder,
        handoff_session_id,
        "handoff_activation_gate_after_tick",
    )
    assert_background_handoff_rejects_unsafe_metadata(recorder, handoff_session_id)

    fixture_session_id = create_session(
        recorder,
        "generation-pipeline-fixture",
        "create_fixture_session",
    )
    default_chain = run_fixture_chain(
        recorder,
        fixture_session_id,
        artifact_profile="default",
        worker_id="pipeline-smoke-default",
        step_id="run_default_fixture_executor_chain",
    )
    default_prefetch = get_prefetch_cache(
        recorder,
        fixture_session_id,
        "fixture_prefetch_cache_after_default_chain",
    )
    default_activation = get_activation_gate(
        recorder,
        fixture_session_id,
        "fixture_activation_gate_after_default_chain",
    )
    default_index = index_shared_cache(
        recorder,
        fixture_session_id,
        "index_shared_cache_after_blocked_default_chain",
    )

    image_session_id = create_session(
        recorder,
        "generation-pipeline-image-failure",
        "create_image_failure_session",
    )
    image_chain = run_fixture_chain(
        recorder,
        image_session_id,
        artifact_profile="image_failure",
        worker_id="pipeline-smoke-image-failure",
        step_id="run_image_failure_fixture_executor_chain",
    )
    image_prefetch = get_prefetch_cache(
        recorder,
        image_session_id,
        "image_prefetch_cache_after_failure_chain",
    )
    image_activation = get_activation_gate(
        recorder,
        image_session_id,
        "image_activation_gate_after_failure_chain",
    )

    readiness_session_id = create_session(
        recorder,
        "generation-pipeline-runtime-readiness",
        "create_runtime_readiness_session",
    )
    readiness_run_payload = recorder.request(
        "POST",
        f"/api/sessions/{readiness_session_id}/generation-schedule/runs",
        expected_status=201,
        step_id="create_runtime_readiness_generation_run",
    )
    readiness_run = as_obj(readiness_run_payload.get("generation_schedule_run"))
    readiness_schedule_item_id = "sched_next_map_visual_prefetch"
    seed_promotion_allowed_ledger(
        db_path=db_path,
        session_id=readiness_session_id,
        run_id=str(readiness_run.get("run_id") or ""),
        schedule_item_id=readiness_schedule_item_id,
    )
    readiness_before = recorder.request(
        "GET",
        f"/api/sessions/{readiness_session_id}/generation-schedule/daemon-readiness",
        step_id="runtime_readiness_daemon_before_chain",
    )
    before_actions = {
        str(action.get("action"))
        for action in as_list(
            as_obj(readiness_before.get("generation_daemon_readiness")).get(
                "recommended_next_actions"
            )
        )
        if isinstance(action, dict)
    }
    if "run_runtime_activation_readiness_chain" not in before_actions:
        raise AssertionError("runtime readiness chain was not recommended before chain")
    readiness_chain = recorder.request(
        "POST",
        f"/api/sessions/{readiness_session_id}/generation-schedule/workers/"
        "run-runtime-activation-readiness-chain",
        body={
            "worker_id": "pipeline-smoke-runtime-readiness-chain",
            "schedule_item_id": readiness_schedule_item_id,
            "activation_decision": "approved_for_manual_apply",
            "note": "generation scheduler review-only pipeline smoke",
        },
        step_id="run_runtime_activation_readiness_chain",
    )
    readiness_after = recorder.request(
        "GET",
        f"/api/sessions/{readiness_session_id}/generation-schedule/daemon-readiness",
        step_id="runtime_readiness_daemon_after_chain",
    )

    target_session_id = create_session(
        recorder,
        "generation-pipeline-target",
        "create_target_session",
    )
    recorder.request(
        "POST",
        f"/api/sessions/{target_session_id}/generation-schedule/runs",
        expected_status=201,
        step_id="create_target_generation_run",
    )
    shared_cache = recorder.request(
        "GET",
        f"/api/sessions/{target_session_id}/generation-schedule/shared-prefetch-cache",
        step_id="target_shared_prefetch_cache",
    )
    hits = recorder.request(
        "GET",
        f"/api/sessions/{target_session_id}/generation-schedule/shared-prefetch-cache/hits",
        step_id="target_shared_prefetch_cache_hits",
    )
    rejected_reuse = recorder.request(
        "POST",
        f"/api/sessions/{target_session_id}/generation-schedule/workers/"
        "record-shared-prefetch-cache-reuse-candidate",
        body={
            "worker_id": "pipeline-smoke-reuse-recorder",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
        expected_status=409,
        payload_response=False,
        step_id="target_reuse_candidate_rejected_without_hit",
    )

    handoff_worker_step = as_obj(handoff_tick.get("worker_step"))
    handoff_background = as_obj(handoff_tick.get("background_handoff_tick"))
    handoff_outbox = as_obj(handoff_tick.get("provider_adapter_runner_handoff_outbox"))
    handoff_ledger_summary = as_obj(
        as_obj(handoff_tick.get("generation_artifact_ledger")).get("summary")
    )
    handoff_prefetch_summary = as_obj(
        as_obj(handoff_prefetch.get("generation_prefetch_cache")).get("summary")
    )
    handoff_activation_summary = as_obj(
        as_obj(handoff_activation.get("generation_activation_gate")).get("summary")
    )
    queue_summary = as_obj(as_obj(queue_view.get("generation_schedule_queue")).get("summary"))
    worker_cache_summary = as_obj(
        as_obj(worker_cache_view.get("generation_schedule_worker_cache")).get("summary")
    )
    ledger_summary_view = as_obj(
        as_obj(ledger_view.get("generation_artifact_ledger")).get("summary")
    )
    default_ledger_summary = as_obj(
        as_obj(default_chain.get("generation_artifact_ledger")).get("summary")
    )
    image_ledger_summary = as_obj(
        as_obj(image_chain.get("generation_artifact_ledger")).get("summary")
    )
    readiness_worker_step = as_obj(readiness_chain.get("worker_step"))
    readiness_ledger_summary = as_obj(
        as_obj(readiness_chain.get("generation_artifact_ledger")).get("summary")
    )
    readiness_prefetch_summary = as_obj(
        as_obj(readiness_chain.get("generation_prefetch_cache")).get("summary")
    )
    readiness_activation_summary = as_obj(
        as_obj(readiness_chain.get("generation_activation_gate")).get("summary")
    )
    readiness_after_actions = {
        str(action.get("action"))
        for action in as_list(
            as_obj(readiness_after.get("generation_daemon_readiness")).get(
                "recommended_next_actions"
            )
        )
        if isinstance(action, dict)
    }
    default_activation_summary = as_obj(
        as_obj(default_activation.get("generation_activation_gate")).get("summary")
    )
    image_activation_summary = as_obj(
        as_obj(image_activation.get("generation_activation_gate")).get("summary")
    )
    shared_cache_summary = as_obj(
        as_obj(shared_cache.get("generation_shared_prefetch_cache")).get("summary")
    )
    hit_summary = as_obj(
        as_obj(hits.get("generation_shared_prefetch_cache_hits")).get("summary")
    )
    default_index_summary = as_obj(default_index.get("shared_prefetch_cache_index"))

    checks = {
        "background_handoff_tick_exported": handoff_worker_step.get("status")
        == "handoff_tick_exported"
        and handoff_outbox.get("runner_handoff_count") == 2,
        "background_handoff_stops_before_provider_execution": as_obj(
            handoff_background.get("safety")
        ).get("api_runs_provider_adapter")
        is False
        and handoff_worker_step.get("staging_performed") is False
        and handoff_worker_step.get("promotion_performed") is False,
        "handoff_prefetch_has_review_only_envelopes": int(
            handoff_prefetch_summary.get("review_only_envelope_ready_count") or 0
        )
        == 2,
        "handoff_activation_gate_blocks_runtime": int(
            handoff_activation_summary.get("activation_allowed_count") or 0
        )
        == 0
        and int(handoff_activation_summary.get("runtime_ready_count") or 0) == 0,
        "handoff_artifact_ledger_has_no_staging_or_promotion": "provider_artifact_staging"
        not in as_obj(handoff_ledger_summary.get("artifact_kind_counts"))
        and "provider_artifact_promotion_report"
        not in as_obj(handoff_ledger_summary.get("artifact_kind_counts")),
        "default_fixture_chain_promotion_blocked": as_obj(
            default_chain.get("provider_artifact_promotion_report")
        ).get("promotion_allowed")
        is False,
        "image_failure_chain_validation_failed": as_obj(
            image_chain.get("provider_artifact_staging")
        ).get("staging_status")
        == "validation_failed",
        "activation_gate_blocks_default_chain": int(
            default_activation_summary.get("activation_allowed_count") or 0
        )
        == 0,
        "activation_gate_blocks_image_failure_chain": int(
            image_activation_summary.get("activation_allowed_count") or 0
        )
        == 0,
        "runtime_readiness_chain_completed": readiness_worker_step.get("status")
        == "completed_review_only"
        and readiness_worker_step.get("step_count") == 3,
        "runtime_readiness_chain_writes_review_only_ledgers": as_obj(
            readiness_ledger_summary.get("artifact_kind_counts")
        ).get("generation_runtime_build_request")
        == 1
        and as_obj(readiness_ledger_summary.get("artifact_kind_counts")).get(
            "generation_runtime_artifact_build_report"
        )
        == 1
        and as_obj(readiness_ledger_summary.get("artifact_kind_counts")).get(
            "generation_runtime_activation_authorization"
        )
        == 1,
        "runtime_readiness_chain_stops_before_apply": int(
            readiness_activation_summary.get("activation_allowed_count") or 0
        )
        == 0
        and int(readiness_activation_summary.get("runtime_ready_count") or 0) == 0
        and "wait_for_runtime_activation_apply_gate" in readiness_after_actions
        and "run_runtime_activation_readiness_chain" not in readiness_after_actions,
        "blocked_default_chain_not_indexed": int(default_index_summary.get("indexed_count") or 0)
        == 0,
        "shared_cache_empty_without_approved_fixture": int(
            shared_cache_summary.get("record_count") or 0
        )
        == 0,
        "target_hit_view_empty": int(hit_summary.get("hit_count") or 0) == 0,
        "reuse_without_hit_rejected": rejected_reuse.get("detail")
        and "no shared prefetch cache hit" in str(rejected_reuse.get("detail")),
    }
    failed = [key for key, value in checks.items() if not value]
    if failed:
        raise AssertionError(f"generation scheduler pipeline checks failed: {failed}")

    provider_call_count = sum(
        int(summary.get("provider_call_count_by_this_request") or 0)
        for summary in (
            handoff_ledger_summary,
            default_ledger_summary,
            image_ledger_summary,
            readiness_ledger_summary,
        )
    )
    world_mutation_count = sum(
        int(summary.get("world_mutation_count_by_this_request") or 0)
        for summary in (
            handoff_ledger_summary,
            default_ledger_summary,
            image_ledger_summary,
            readiness_ledger_summary,
        )
    )
    activation_allowed_count = sum(
        int(summary.get("activation_allowed_count") or 0)
        for summary in (
            handoff_ledger_summary,
            handoff_activation_summary,
            default_ledger_summary,
            default_activation_summary,
            image_ledger_summary,
            image_activation_summary,
            readiness_ledger_summary,
            readiness_activation_summary,
        )
    )

    return {
        "schema_version": "generation_scheduler_review_only_pipeline_smoke_report.v0.1",
        "report_id": "generation_scheduler_review_only_pipeline_smoke_report_v0_1",
        "generated_at": generated_at,
        "status": "passed",
        "transport": "local_uvicorn_http",
        "step_count": len(recorder.steps),
        "passed_step_count": sum(1 for step in recorder.steps if step["passed"]),
        "endpoint_steps": recorder.steps,
        "sessions": {
            "handoff_session_id_present": bool(handoff_session_id),
            "fixture_session_id_present": bool(fixture_session_id),
            "image_failure_session_id_present": bool(image_session_id),
            "runtime_readiness_session_id_present": bool(readiness_session_id),
            "target_session_id_present": bool(target_session_id),
        },
        "summary": {
            "background_handoff_status": handoff_worker_step.get("status"),
            "background_handoff_dispatched_count": handoff_worker_step.get("dispatched_count"),
            "background_handoff_runner_handoff_count": handoff_worker_step.get("runner_handoff_count"),
            "background_handoff_stop_reason": handoff_worker_step.get("stop_reason"),
            "background_handoff_outbox_schema_version": handoff_outbox.get("schema_version"),
            "background_handoff_outbox_mode": handoff_outbox.get("handoff_mode"),
            "background_handoff_review_only": handoff_outbox.get("review_only"),
            "handoff_queue_status_counts": queue_summary.get("status_counts"),
            "handoff_worker_cache_item_count": worker_cache_summary.get("item_count"),
            "handoff_ledger_item_count": ledger_summary_view.get("item_count"),
            "handoff_prefetch_status_counts": handoff_prefetch_summary.get("cache_status_counts"),
            "handoff_activation_status_counts": handoff_activation_summary.get("gate_status_counts"),
            "handoff_forbidden_key_scan": "passed",
            "default_chain_status": as_obj(default_chain.get("executor_chain")).get("status"),
            "default_chain_artifact_profile": as_obj(default_chain.get("executor_chain")).get("artifact_profile"),
            "default_chain_ledger_item_count": default_ledger_summary.get("item_count"),
            "default_chain_promotion_allowed_count": default_ledger_summary.get("promotion_allowed_count"),
            "default_prefetch_status_counts": as_obj(
                as_obj(default_prefetch.get("generation_prefetch_cache")).get("summary")
            ).get("cache_status_counts"),
            "default_activation_status_counts": default_activation_summary.get("gate_status_counts"),
            "image_chain_status": as_obj(image_chain.get("executor_chain")).get("status"),
            "image_chain_artifact_profile": as_obj(image_chain.get("executor_chain")).get("artifact_profile"),
            "image_chain_staging_status": as_obj(image_chain.get("provider_artifact_staging")).get("staging_status"),
            "image_chain_promotion_decision": as_obj(image_chain.get("provider_artifact_promotion_report")).get("promotion_decision"),
            "image_prefetch_status_counts": as_obj(
                as_obj(image_prefetch.get("generation_prefetch_cache")).get("summary")
            ).get("cache_status_counts"),
            "image_activation_status_counts": image_activation_summary.get("gate_status_counts"),
            "runtime_readiness_chain_status": readiness_worker_step.get("status"),
            "runtime_readiness_chain_step_count": readiness_worker_step.get("step_count"),
            "runtime_readiness_chain_schedule_item_id": readiness_schedule_item_id,
            "runtime_readiness_chain_prefetch_status_counts": readiness_prefetch_summary.get("cache_status_counts"),
            "runtime_readiness_chain_activation_status_counts": readiness_activation_summary.get("gate_status_counts"),
            "runtime_readiness_chain_ledger_kind_counts": readiness_ledger_summary.get("artifact_kind_counts"),
            "runtime_readiness_chain_post_actions": sorted(readiness_after_actions),
            "runtime_readiness_chain_activation_allowed_count": readiness_activation_summary.get(
                "activation_allowed_count"
            ),
            "shared_cache_indexed_count_after_blocked_default_chain": default_index_summary.get("indexed_count"),
            "target_shared_cache_record_count": shared_cache_summary.get("record_count"),
            "target_hit_count": hit_summary.get("hit_count"),
            "reuse_without_hit_rejected_status": 409,
            "positive_shared_cache_reuse_path": "not_exercised_no_approved_promotion_fixture",
        },
        "checks": checks,
        "safety_summary": {
            "reads_env_file": False,
            "external_provider_call_count": provider_call_count,
            "world_state_write_scope": "temporary_test_sqlite",
            "world_mutation_count": world_mutation_count,
            "runtime_activation_allowed_count": activation_allowed_count,
            "queue_completion_count": 0,
            "handoff_outbox_runs_provider_adapter": False,
            "handoff_outbox_stages_provider_artifacts": False,
            "handoff_outbox_promotes_provider_artifacts": False,
            "runtime_package_write_count": 0,
            "world_delta_transaction_write_count": 0,
            "shared_cache_positive_path_not_claimed": True,
        },
        "known_limits": [
            "background handoff tick 只导出外部 runner outbox，不执行真实 runner。",
            "没有 approved promotion fixture，因此本 smoke 不制造 shared cache 正向命中。",
            "runtime readiness chain 只用临时 SQLite seed 触发 prepare/build-report/authorization 三步，并停在 apply gate；正式 runtime package / WorldStateDeltaTransaction apply 仍是后续任务。",
            "promotion_allowed 的正向 shared cache 索引仍由后端单元测试覆盖。",
        ],
    }


def start_server(db_path: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["APP_DB_PATH"] = str(db_path)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    pythonpath = str(BACKEND_ROOT)
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def build_report(generated_at: str | None = None) -> dict[str, Any]:
    generated = (
        generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    with tempfile.TemporaryDirectory(prefix="ai_td_generation_pipeline_") as tmpdir:
        db_path = Path(tmpdir) / "app.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_server(db_path, port)
        try:
            wait_for_server(base_url, process)
            return build_pipeline_report(base_url, db_path, generated)
        finally:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=(
            "examples/review_packs/"
            "generation_scheduler_review_only_pipeline_smoke_report.v0.1.json"
        ),
    )
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    report = build_report(args.generated_at)
    write_json(ROOT / args.output, report)
    print(f"generation scheduler review-only pipeline smoke passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
