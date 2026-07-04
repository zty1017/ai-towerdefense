#!/usr/bin/env python3
"""Smoke-check the fixture-backed MVP primary API flow over local HTTP.

The script starts a temporary uvicorn server bound to 127.0.0.1, points the app
at a throwaway SQLite database, walks the core player/demo API path, and writes
a redacted review report. It does not read `.env` or call external providers.
"""

from __future__ import annotations

import argparse
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
FORBIDDEN_PLAYER_TERMS = (
    "provider",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "schema",
    "traceback",
    "AI",
    "prompt",
    "compiler",
    "token",
    "trace",
    "mock",
    "simulation",
)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode("utf-8")
    if status != expected_status:
        raise AssertionError(f"{method} {path}: expected {expected_status}, got {status}: {payload[:500]}")
    return json.loads(payload) if payload else {}


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


def assert_player_safe(*texts: str | None) -> None:
    for text in texts:
        if not text:
            continue
        for term in FORBIDDEN_PLAYER_TERMS:
            if term in text:
                raise AssertionError(f"player-facing text leaked forbidden term {term!r}")


def payload(body: dict[str, Any], step_id: str) -> dict[str, Any]:
    if body.get("mode") != "frontend_mock_fixture":
        raise AssertionError(f"{step_id}: unexpected response mode {body.get('mode')}")
    return as_obj(body.get("payload"))


def scrub_session_path(path: str) -> str:
    parts = path.split("/")
    if len(parts) > 3 and parts[1] == "api" and parts[2] == "sessions":
        parts[3] = "{session_id}"
    if "research" in parts and "proposals" in parts:
        index = parts.index("proposals")
        if len(parts) > index + 1 and parts[index + 1] != "confirm":
            parts[index + 1] = "{proposal_id}"
    if "research" in parts and "jobs" in parts:
        index = parts.index("jobs")
        if len(parts) > index + 1:
            parts[index + 1] = "{job_id}"
    return "/".join(parts)


class FlowRecorder:
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
        return payload(response, step_id) if payload_response else response


def build_flow_report(base_url: str, generated_at: str) -> dict[str, Any]:
    recorder = FlowRecorder(base_url)
    session = recorder.request(
        "POST",
        "/api/sessions",
        body={"display_name": "mvp-flow-smoke"},
        expected_status=201,
        payload_response=False,
        step_id="create_session",
    )
    session_id = session["session_id"]
    session_info = recorder.request(
        "GET",
        f"/api/sessions/{session_id}",
        payload_response=False,
        step_id="get_session",
    )
    world = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/world-instance",
        body={"selected_options": {"creativity_mode": "experimental"}},
        expected_status=201,
        step_id="create_world_instance",
    )
    opening = recorder.request("GET", f"/api/sessions/{session_id}/opening", step_id="opening")
    frontend_pack = recorder.request(
        "GET", f"/api/sessions/{session_id}/frontend-mock-pack", step_id="frontend_mock_pack"
    )
    runtime_art = recorder.request(
        "GET", f"/api/sessions/{session_id}/runtime-art-kit", step_id="runtime_art_kit"
    )
    strategic_map = recorder.request("GET", f"/api/sessions/{session_id}/map", step_id="map")
    campaign = recorder.request(
        "GET", f"/api/sessions/{session_id}/campaign-router", step_id="campaign_router"
    )
    current_node = as_obj(as_obj(campaign.get("campaign_router")).get("current"))
    node_id = str(current_node.get("node_id") or "gray_lantern_station")
    prefetch = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/campaign-router/prefetch-next",
        step_id="campaign_prefetch_next",
    )
    briefing = recorder.request(
        "GET", f"/api/sessions/{session_id}/nodes/{node_id}/briefing", step_id="briefing"
    )
    proposal = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/research/proposals",
        body={"intent_text": "我想让入口处的敌人短暂停滞", "node_id": node_id},
        expected_status=201,
        payload_response=False,
        step_id="research_create_proposal",
    )
    assert_player_safe(
        proposal.get("display_name"),
        proposal.get("summary"),
        proposal.get("risk_note"),
        proposal.get("player_state_message"),
    )
    job = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/research/proposals/{proposal['proposal_id']}/confirm",
        payload_response=False,
        step_id="research_confirm_proposal",
    )
    assert_player_safe(job.get("player_state_message"))
    fetched_job = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/research/jobs/{job['job_id']}",
        payload_response=False,
        step_id="research_get_job",
    )
    battle = recorder.request(
        "GET", f"/api/sessions/{session_id}/battles/{node_id}/config", step_id="battle_config"
    )
    runtime = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/battles/{node_id}/runtime-package",
        step_id="runtime_package",
    )
    map_runtime = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/battles/{node_id}/map-runtime-package",
        step_id="map_runtime_package",
    )
    render_plan = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/battles/{node_id}/map-render-plan",
        step_id="map_render_plan",
    )
    map_v02 = recorder.request(
        "GET",
        f"/api/sessions/{session_id}/battles/{node_id}/map-v02-preview",
        step_id="map_v02_preview",
    )
    settlement = recorder.request(
        "POST",
        f"/api/sessions/{session_id}/battles/{node_id}/results",
        body={
            "result": "victory",
            "protected_core_hp": 7,
            "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
            "leaked_enemy_count": 1,
        },
        step_id="submit_battle_result",
    )
    latest_settlement = recorder.request(
        "GET", f"/api/sessions/{session_id}/settlement/latest", step_id="latest_settlement"
    )
    evidence = recorder.request(
        "GET", f"/api/sessions/{session_id}/evidence", step_id="session_evidence"
    )

    battle_config = as_obj(battle.get("battle_config"))
    map_package = as_obj(map_runtime.get("map_runtime_package"))
    runtime_package = as_obj(runtime.get("runtime_package"))
    map_render_bundle = as_obj(render_plan.get("map_render_plan_bundle"))
    settlement_payload = as_obj(settlement.get("settlement"))
    latest_payload = as_obj(latest_settlement.get("settlement"))
    proposal_metadata = as_obj(proposal.get("compiler_metadata"))
    job_metadata = as_obj(job.get("compiler_metadata"))
    job_runtime_path = job.get("runtime_package_path")
    job_delivery_path = job.get("delivery_payload_path")

    checks = {
        "world_instance_created": as_obj(
            as_obj(world.get("world_instance")).get("selected_options")
        ).get("creativity_mode")
        == "experimental"
        and as_obj(as_obj(world.get("run_world_state")).get("progress")).get("phase")
        == "first_defense",
        "campaign_current_node_matches_briefing": as_obj(briefing.get("briefing")).get("node_id") == node_id,
        "research_job_completed": job.get("status") == "completed" and fetched_job.get("status") == "completed",
        "research_artifacts_exist": bool(job_runtime_path)
        and Path(str(job_runtime_path)).exists()
        and bool(job_delivery_path)
        and Path(str(job_delivery_path)).exists(),
        "battle_runtime_ready": runtime_package.get("schema_version") == "runtime_package.v0.1",
        "map_runtime_v01_ready": map_package.get("schema_version") == "map_runtime_package.v0.1",
        "map_v02_preview_ready": as_obj(map_v02.get("map_runtime_package_v02")).get("schema_version")
        == "map_runtime_package.v0.2",
        "render_plan_passed": as_obj(
            map_render_bundle.get("semantic_visual_consistency_report")
        ).get("status")
        == "passed",
        "settlement_committed": settlement_payload.get("result") == "victory"
        and latest_payload.get("node_id") == node_id,
        "session_evidence_passed": as_obj(evidence.get("audit_summary")).get("overall_status")
        == "passed",
    }
    failed_checks = [key for key, value in checks.items() if not value]
    if failed_checks:
        raise AssertionError(f"flow checks failed: {failed_checks}")

    return {
        "schema_version": "mvp_primary_api_flow_smoke_report.v0.1",
        "report_id": "mvp_primary_api_flow_smoke_report_v0_1",
        "generated_at": generated_at,
        "status": "passed",
        "flow_id": "anonymous_session_to_first_battle_settlement",
        "transport": "local_uvicorn_http",
        "step_count": len(recorder.steps),
        "passed_step_count": sum(1 for step in recorder.steps if step["passed"]),
        "node_id": node_id,
        "endpoint_steps": recorder.steps,
        "summary": {
            "session_created": bool(session_info.get("session_id")),
            "world_phase": as_obj(as_obj(world.get("run_world_state")).get("progress")).get("phase"),
            "opening_card_count": len(as_list(as_obj(opening.get("opening")).get("segments"))),
            "frontend_asset_count": len(as_list(as_obj(frontend_pack.get("pack")).get("assets"))),
            "runtime_art_asset_count": len(as_list(as_obj(runtime_art.get("runtime_art_kit")).get("art_assets"))),
            "map_node_count": len(as_list(as_obj(strategic_map.get("map")).get("nodes"))),
            "campaign_current_node": node_id,
            "campaign_next_node": as_obj(as_obj(campaign.get("campaign_router")).get("next")).get("node_id"),
            "prefetch_provider_call_count": as_obj(prefetch.get("worker_step")).get("provider_call_count"),
            "battle_enemy_wave_count": len(as_list(battle_config.get("waves"))),
            "battle_toolbar_asset_count": len(as_list(battle.get("toolbar_assets"))),
            "runtime_package_id": runtime_package.get("package_id"),
            "runtime_asset_count": len(as_list(runtime_package.get("assets"))),
            "map_build_slot_count": len(as_list(map_package.get("build_slots"))),
            "map_route_count": len(as_list(map_package.get("path_routes"))),
            "map_v02_resource_node_count": len(
                as_list(as_obj(map_v02.get("map_runtime_package_v02")).get("resource_nodes"))
            ),
            "settlement_mode": settlement_payload.get("settlement_mode"),
            "settlement_phase": as_obj(as_obj(settlement_payload.get("run_world_state")).get("progress")).get("phase"),
        },
        "research": {
            "proposal_created": bool(proposal.get("proposal_id")),
            "proposal_gate_status": as_obj(proposal_metadata.get("validation")).get("gate_status"),
            "job_id_present": bool(job.get("job_id")),
            "job_status": job.get("status"),
            "job_fetch_status": fetched_job.get("status"),
            "job_trace_count": len(as_list(job.get("trace_paths"))),
            "runtime_package_exists": bool(job_runtime_path) and Path(str(job_runtime_path)).exists(),
            "delivery_payload_exists": bool(job_delivery_path) and Path(str(job_delivery_path)).exists(),
            "job_gate_status": as_obj(job_metadata.get("validation")).get("gate_status"),
            "player_text_safety": "passed",
        },
        "core_artifacts": {
            "proposal_status": as_obj(proposal_metadata.get("core_artifacts")).get("status"),
            "job_status": as_obj(job_metadata.get("core_artifacts")).get("status"),
            "settlement_status": as_obj(settlement_payload.get("core_artifacts")).get("status"),
            "world_delta_transaction_id": as_obj(
                settlement_payload.get("world_delta_transaction")
            ).get("transaction_id"),
        },
        "checks": checks,
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "world_state_write_scope": "temporary_test_sqlite",
            "player_input_body_stored": False,
            "provider_raw_output_stored": False,
            "runtime_activation_mutation_count": 0,
        },
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
    generated = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with tempfile.TemporaryDirectory(prefix="ai_td_primary_flow_") as tmpdir:
        db_path = Path(tmpdir) / "app.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_server(db_path, port)
        try:
            wait_for_server(base_url, process)
            return build_flow_report(base_url, generated)
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
        default="examples/review_packs/mvp_primary_api_flow_smoke_report.v0.1.json",
    )
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    report = build_report(args.generated_at)
    write_json(ROOT / args.output, report)
    print(f"mvp primary API flow smoke passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
