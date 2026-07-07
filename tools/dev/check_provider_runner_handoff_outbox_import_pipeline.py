#!/usr/bin/env python3
"""Smoke-check provider runner outbox consume -> import -> prefetch-cache.

This starts a temporary backend, obtains a review-only handoff outbox, consumes
the outbox with the local fixture runner, imports the generated receipt/envelope
files back into the temporary backend ledger, and verifies prefetch-cache sees
review-only envelopes. It does not call providers, read .env, stage artifacts,
promote artifacts, write world state, or activate runtime.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
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
CONSUMER_REPORT_NAME = (
    "provider_adapter_runner_handoff_outbox_execution_report.v0.1.json"
)
REPORT_NAME = "provider_runner_handoff_outbox_import_pipeline_report.v0.1.json"
HANDOFF_SCHEDULE_ITEM_IDS = (
    "sched_next_map_visual_prefetch",
    "sched_video_frame_background_compile",
)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def project_python_command() -> tuple[list[str], dict[str, Any]]:
    """Return a Python command with project backend dependencies available."""
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return [str(venv_python)], {
            "mode": "venv",
            "uses_uv": False,
            "python_path": str(venv_python),
        }
    if importlib.util.find_spec("uvicorn") is not None:
        return [sys.executable], {
            "mode": "current-python",
            "uses_uv": False,
            "python_path": sys.executable,
        }
    return ["uv", "run", "--extra", "dev", "python"], {
        "mode": "uv",
        "uses_uv": True,
        "python_path": None,
    }


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
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
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
            f"{method} {path}: expected {expected_status}, got {status}: {payload_text[:700]}"
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


def scrub_session_path(path: str) -> str:
    parts = path.split("/")
    if len(parts) > 3 and parts[1] == "api" and parts[2] == "sessions":
        parts[3] = "{session_id}"
    return "/".join(parts)


def create_session(recorder: ApiRecorder) -> str:
    session = recorder.request(
        "POST",
        "/api/sessions",
        body={"display_name": "Outbox Import Smoke"},
        expected_status=201,
        payload_response=False,
        step_id="create_session",
    )
    return str(session["session_id"])


def outbox_safety() -> dict[str, bool]:
    return {
        "api_reads_env": False,
        "api_calls_provider": False,
        "api_runs_provider_adapter": False,
        "api_stages_provider_artifacts": False,
        "api_promotes_provider_artifacts": False,
        "api_completes_queue_items": False,
        "api_writes_world_state": False,
        "api_activates_runtime": False,
        "prompt_body_included": False,
        "provider_response_body_included": False,
        "live_templates_require_external_explicit_authorization": True,
    }


def build_handoff_outbox(
    *,
    session_id: str,
    run_id: str,
    runner_handoffs: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "provider_adapter_runner_handoff_outbox.v0.1",
        "outbox_id": (
            "provider_adapter_runner_handoff_outbox_"
            f"{run_id}_outbox_import_smoke"
        ),
        "created_at": generated_at,
        "handoff_mode": "external_runner_required",
        "review_only": True,
        "source": {
            "session_id": session_id,
            "run_id": run_id,
            "worker_mode": "review_only_background_handoff_tick",
            "max_items": len(runner_handoffs),
            "dispatched_count": len(runner_handoffs),
            "stop_reason": "manual_export_without_runner_fixture",
        },
        "safety": outbox_safety(),
        "runner_handoff_count": len(runner_handoffs),
        "runner_handoffs": runner_handoffs,
        "import_contract": {
            "endpoint": (
                "/api/sessions/{session_id}/generation-schedule/workers/"
                "import-provider-adapter-runner-output"
            ),
            "method": "POST",
            "required_body_fields": [
                "schedule_item_id",
                "authorization_ref",
                "receipt_path",
                "envelope_path",
            ],
            "post_import_gate": "provider_artifact_staging_or_promotion_review_required",
        },
    }


def prepare_and_export_handoffs(
    *,
    recorder: ApiRecorder,
    session_id: str,
    generated_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/generation-schedule/runs",
        expected_status=201,
        step_id="create_generation_schedule_run",
    )
    run_payload = as_obj(run.get("generation_schedule_run"))
    run_id = str(run_payload.get("run_id") or "")
    if not run_id:
        raise AssertionError("generation schedule run_id is required")

    runner_handoffs: list[dict[str, Any]] = []
    for index, schedule_item_id in enumerate(HANDOFF_SCHEDULE_ITEM_IDS, start=1):
        worker_prefix = f"outbox-import-smoke-{index:02d}"
        dry = recorder.request(
            "POST",
            f"/api/sessions/{session_id}/generation-schedule/workers/dry-run-step",
            body={
                "worker_id": f"{worker_prefix}-dry",
                "schedule_item_id": schedule_item_id,
            },
            step_id=f"dry_run_step_{schedule_item_id}",
        )
        if as_obj(dry.get("worker_step")).get("status") != "processed":
            raise AssertionError(f"{schedule_item_id}: dry-run step did not process")
        guard = recorder.request(
            "POST",
            f"/api/sessions/{session_id}/generation-schedule/workers/"
            "live-executor-guard",
            body={
                "worker_id": f"{worker_prefix}-guard",
                "schedule_item_id": schedule_item_id,
            },
            step_id=f"live_executor_guard_{schedule_item_id}",
        )
        if as_obj(guard.get("worker_step")).get("status") != "blocked":
            raise AssertionError(f"{schedule_item_id}: live executor guard did not block")
        prepared = recorder.request(
            "POST",
            f"/api/sessions/{session_id}/generation-schedule/workers/"
            "prepare-executor-request",
            body={
                "worker_id": f"{worker_prefix}-prepare",
                "schedule_item_id": schedule_item_id,
            },
            step_id=f"prepare_executor_request_{schedule_item_id}",
        )
        if as_obj(prepared.get("worker_step")).get("status") != "prepared":
            raise AssertionError(f"{schedule_item_id}: executor request not prepared")
        authorized = recorder.request(
            "POST",
            f"/api/sessions/{session_id}/generation-schedule/workers/"
            "grant-provider-authorization",
            body={
                "worker_id": f"{worker_prefix}-authorize",
                "schedule_item_id": schedule_item_id,
            },
            step_id=f"grant_provider_authorization_{schedule_item_id}",
        )
        auth_step = as_obj(authorized.get("worker_step"))
        if auth_step.get("status") != "authorized":
            raise AssertionError(f"{schedule_item_id}: provider authorization not granted")
        authorization_ref = str(auth_step.get("authorization_ref") or "")
        handoff_export = recorder.request(
            "POST",
            f"/api/sessions/{session_id}/generation-schedule/workers/"
            "export-provider-adapter-runner-handoff",
            body={
                "worker_id": f"{worker_prefix}-export",
                "schedule_item_id": schedule_item_id,
                "authorization_ref": authorization_ref,
                "note": "manual outbox import smoke handoff export",
            },
            step_id=f"export_runner_handoff_{schedule_item_id}",
        )
        handoff = as_obj(handoff_export.get("provider_adapter_runner_handoff"))
        source = as_obj(handoff.get("source"))
        if source.get("schedule_item_id") != schedule_item_id:
            raise AssertionError(f"{schedule_item_id}: exported handoff schedule mismatch")
        if source.get("authorization_ref") != authorization_ref:
            raise AssertionError(f"{schedule_item_id}: exported handoff auth mismatch")
        runner_handoffs.append(handoff)

    outbox = build_handoff_outbox(
        session_id=session_id,
        run_id=run_id,
        runner_handoffs=runner_handoffs,
        generated_at=generated_at,
    )
    if outbox.get("runner_handoff_count") != len(HANDOFF_SCHEDULE_ITEM_IDS):
        raise AssertionError("manual outbox handoff count mismatch")
    return outbox, runner_handoffs


def run_consumer(
    *,
    outbox_path: Path,
    output_dir: Path,
    generated_at: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    python_command, runner = project_python_command()
    command = [
        *python_command,
        "tools/dev/run_provider_adapter_runner_handoff_outbox.py",
        str(outbox_path),
        "--output-dir",
        str(output_dir),
        "--generated-at",
        generated_at,
        "--command-timeout",
        str(timeout_seconds),
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds * 3,
        check=False,
    )
    command_result = {
        "step_id": "consume_outbox_with_local_runner",
        "command": " ".join(command),
        "runner": runner,
        "return_code": completed.returncode,
        "status": "passed" if completed.returncode == 0 else "failed",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": completed.stdout[-1200:].strip(),
        "stderr_tail": completed.stderr[-1200:].strip(),
    }
    if completed.returncode != 0:
        raise AssertionError(f"outbox consumer failed: {command_result}")
    report = load_json(output_dir / CONSUMER_REPORT_NAME)
    return report, command_result


def run_pipeline(
    *,
    recorder: ApiRecorder,
    session_id: str,
    output_dir: Path,
    generated_at: str,
    command_timeout: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    outbox, runner_handoffs = prepare_and_export_handoffs(
        recorder=recorder,
        session_id=session_id,
        generated_at=generated_at,
    )
    pre_import_prefetch = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/generation-schedule/prefetch-cache",
        step_id="prefetch_cache_before_import",
    )
    pre_import_summary = as_obj(
        as_obj(pre_import_prefetch.get("generation_prefetch_cache")).get("summary")
    )
    if int(pre_import_summary.get("review_only_envelope_ready_count") or 0) != 0:
        raise AssertionError("prefetch cache must not have ready envelopes before import")
    outbox_path = output_dir / "provider_adapter_runner_handoff_outbox.v0.1.json"
    write_json(outbox_path, outbox)
    consumer_report, consumer_command = run_consumer(
        outbox_path=outbox_path,
        output_dir=output_dir / "consumer",
        generated_at=generated_at,
        timeout_seconds=command_timeout,
    )
    if consumer_report.get("status") != "passed":
        raise AssertionError("outbox consumer report did not pass")
    expected_count = len(runner_handoffs)
    if int(consumer_report.get("runner_handoff_count") or 0) != expected_count:
        raise AssertionError("consumer runner handoff count mismatch")
    if int(consumer_report.get("executed_count") or 0) != expected_count:
        raise AssertionError("consumer executed count mismatch")
    if int(consumer_report.get("passed_count") or 0) != expected_count:
        raise AssertionError("consumer passed count mismatch")
    executions = [item for item in as_list(consumer_report.get("executions")) if isinstance(item, dict)]
    if len(executions) != expected_count:
        raise AssertionError("consumer execution list count mismatch")
    import_results: list[dict[str, Any]] = []
    for execution in executions:
        body = as_obj(as_obj(execution.get("import_after_runner")).get("body"))
        body["worker_id"] = "outbox-import-smoke-importer"
        body["note"] = "imported by review-only outbox import smoke"
        imported = recorder.request(
            "POST",
            f"/api/sessions/{session_id}/generation-schedule/workers/"
            "import-provider-adapter-runner-output",
            body=body,
            step_id=f"import_runner_output_{execution.get('schedule_item_id')}",
        )
        import_step = as_obj(imported.get("worker_step"))
        if import_step.get("status") != "imported":
            raise AssertionError(f"{execution.get('schedule_item_id')}: import did not pass")
        if import_step.get("worker_mode") != "provider_adapter_runner_output_import":
            raise AssertionError(f"{execution.get('schedule_item_id')}: import worker mode mismatch")
        if import_step.get("schedule_item_id") != execution.get("schedule_item_id"):
            raise AssertionError(f"{execution.get('schedule_item_id')}: import schedule mismatch")
        if import_step.get("authorization_ref") != execution.get("authorization_ref"):
            raise AssertionError(f"{execution.get('schedule_item_id')}: import authorization mismatch")
        if int(import_step.get("provider_call_count") or 0) != 0:
            raise AssertionError(f"{execution.get('schedule_item_id')}: import provider call count must be 0")
        if int(import_step.get("world_mutation_count") or 0) != 0:
            raise AssertionError(f"{execution.get('schedule_item_id')}: import world mutation count must be 0")
        if int(import_step.get("activation_allowed_count") or 0) != 0:
            raise AssertionError(f"{execution.get('schedule_item_id')}: import activation count must be 0")
        import_results.append(imported)
    if len(import_results) != expected_count:
        raise AssertionError("import result count mismatch")
    prefetch = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/generation-schedule/prefetch-cache",
        step_id="prefetch_cache_after_import",
    )
    activation = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/generation-schedule/activation-gate",
        step_id="activation_gate_after_import",
    )
    cache_summary = as_obj(as_obj(prefetch.get("generation_prefetch_cache")).get("summary"))
    activation_summary = as_obj(
        as_obj(activation.get("generation_activation_gate")).get("summary")
    )
    if int(cache_summary.get("review_only_envelope_ready_count") or 0) != len(import_results):
        raise AssertionError(
            "prefetch cache did not expose imported review-only envelopes"
        )
    if int(activation_summary.get("activation_allowed_count") or 0) != 0:
        raise AssertionError("activation gate must continue blocking runtime activation")
    return outbox, consumer_report, import_results, {
        "pre_import_prefetch": pre_import_prefetch,
        "prefetch_cache": prefetch,
        "activation_gate": activation,
        "consumer_command": consumer_command,
    }


def build_report(generated_at: str, command_timeout: int) -> dict[str, Any]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="ai_td_outbox_import_smoke_") as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "outbox_import_smoke.sqlite3"
        output_dir = temp_path / "outbox_import_outputs"
        env = os.environ.copy()
        env["APP_DB_PATH"] = str(db_path)
        env["NO_PROXY"] = "127.0.0.1,localhost"
        env["no_proxy"] = "127.0.0.1,localhost"
        pythonpath_parts = [str(BACKEND_ROOT), str(ROOT)]
        if env.get("PYTHONPATH"):
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        python_command, backend_runner = project_python_command()
        process = subprocess.Popen(
            [
                *python_command,
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
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            wait_for_server(base_url, process)
            recorder = ApiRecorder(base_url)
            session_id = create_session(recorder)
            outbox, consumer_report, import_results, views = run_pipeline(
                recorder=recorder,
                session_id=session_id,
                output_dir=output_dir,
                generated_at=generated_at,
                command_timeout=command_timeout,
            )
        finally:
            process.terminate()
            try:
                process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)

    pre_import_prefetch_summary = as_obj(
        as_obj(
            as_obj(views.get("pre_import_prefetch")).get("generation_prefetch_cache")
        ).get("summary")
    )
    prefetch_summary = as_obj(
        as_obj(as_obj(views.get("prefetch_cache")).get("generation_prefetch_cache")).get(
            "summary"
        )
    )
    activation_summary = as_obj(
        as_obj(as_obj(views.get("activation_gate")).get("generation_activation_gate")).get(
            "summary"
        )
    )
    consumer_safety = as_obj(consumer_report.get("safety_summary"))
    import_summaries = [
        as_obj(as_obj(item).get("worker_step")) for item in import_results
    ]
    status = "passed"
    zero_safety_fields = {
        "consumer provider calls": consumer_safety.get("provider_call_count"),
        "consumer env reads": consumer_safety.get("reads_env_count"),
        "consumer backend imports": consumer_safety.get("imports_to_backend_count"),
        "consumer staging": consumer_safety.get("staging_count"),
        "consumer promotion": consumer_safety.get("promotion_count"),
        "consumer queue complete": consumer_safety.get("queue_complete_count"),
        "consumer world mutation": consumer_safety.get("world_mutation_allowed_count"),
        "consumer runtime activation": consumer_safety.get(
            "runtime_activation_allowed_count"
        ),
        "activation gate allowed": activation_summary.get("activation_allowed_count"),
    }
    for label, value in zero_safety_fields.items():
        if int(value or 0) != 0:
            raise AssertionError(f"{label} must be 0, got {value}")
    safety_summary = {
        "external_provider_call_count": consumer_safety.get("provider_call_count"),
        "consumer_reads_env_count": consumer_safety.get("reads_env_count"),
        "consumer_imports_to_backend_count": consumer_safety.get(
            "imports_to_backend_count"
        ),
        "api_import_count": len(import_results),
        "staging_count": consumer_safety.get("staging_count"),
        "promotion_count": consumer_safety.get("promotion_count"),
        "world_mutation_count": consumer_safety.get("world_mutation_allowed_count"),
        "runtime_activation_allowed_count": activation_summary.get(
            "activation_allowed_count"
        ),
        "queue_complete_count": consumer_safety.get("queue_complete_count"),
    }
    return {
        "schema_version": "provider_runner_handoff_outbox_import_pipeline_report.v0.1",
        "status": status,
        "generated_at": generated_at,
        "backend_runner": backend_runner,
        "step_count": len(recorder.steps) + 1,
        "passed_step_count": len(recorder.steps) + 1,
        "steps": [*recorder.steps, views["consumer_command"]],
        "summary": {
            "handoff_outbox_schema_version": outbox.get("schema_version"),
            "runner_handoff_count": outbox.get("runner_handoff_count"),
            "consumer_status": consumer_report.get("status"),
            "consumer_executed_count": consumer_report.get("executed_count"),
            "imported_count": len(import_results),
            "pre_import_review_only_envelope_ready_count": (
                pre_import_prefetch_summary.get("review_only_envelope_ready_count")
            ),
            "prefetch_review_only_envelope_ready_count": prefetch_summary.get(
                "review_only_envelope_ready_count"
            ),
            "activation_allowed_count": activation_summary.get(
                "activation_allowed_count"
            ),
            "import_worker_statuses": [
                item.get("status") for item in import_summaries
            ],
        },
        "consumer_report": {
            "schema_version": consumer_report.get("schema_version"),
            "status": consumer_report.get("status"),
            "adapter_mode": consumer_report.get("adapter_mode"),
            "executed_count": consumer_report.get("executed_count"),
            "passed_count": consumer_report.get("passed_count"),
            "safety_summary": consumer_report.get("safety_summary"),
        },
        "import_results": [
            {
                "status": item.get("status"),
                "worker_mode": item.get("worker_mode"),
                "schedule_item_id": item.get("schedule_item_id"),
                "authorization_ref": item.get("authorization_ref"),
                "execution_receipt_id": item.get("execution_receipt_id"),
                "envelope_id": item.get("envelope_id"),
                "provider_call_count": item.get("provider_call_count"),
                "world_mutation_count": item.get("world_mutation_count"),
                "activation_allowed_count": item.get("activation_allowed_count"),
            }
            for item in import_summaries
        ],
        "safety_summary": safety_summary,
        "limits": [
            "This smoke uses fixture provider adapter boundaries only.",
            "It imports receipt/envelope into a temporary local backend ledger.",
            "It does not stage artifacts, promote artifacts, complete queue items, write world state, or activate runtime.",
            "It does not call live providers or read .env.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp") / REPORT_NAME,
    )
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--command-timeout", type=int, default=90)
    args = parser.parse_args()
    generated_at = args.generated_at or now_iso()
    report = build_report(generated_at, args.command_timeout)
    write_json(args.output, report)
    print(f"provider runner outbox import pipeline {report['status']}: {args.output}")
    summary = as_obj(report.get("summary"))
    print(
        "- imported "
        f"{summary.get('imported_count')} / {summary.get('runner_handoff_count')} "
        "runner outputs"
    )
    print(
        "- prefetch review-only envelopes: "
        f"{summary.get('prefetch_review_only_envelope_ready_count')}, "
        f"activation allowed: {summary.get('activation_allowed_count')}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
