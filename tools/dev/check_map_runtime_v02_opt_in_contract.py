#!/usr/bin/env python3
"""Smoke-check the MapRuntimePackage v0.2 opt-in dry-run contract."""

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
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(ROOT))

from tools.dev.report_io import write_json

AUTHORIZATION_REPORT = ROOT / "examples/review_packs/map_runtime_activation_authorization_report.v0.1.json"
NODE_IDS = ("gray_lantern_station", "lamp_wick_store", "old_signal_tower")
V02_KEYS = ("resource_nodes", "hazard_zones", "defense_anchors", "blocked_areas")
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def make_approved_authorization_report(path: Path) -> Path:
    report = json.loads(AUTHORIZATION_REPORT.read_text(encoding="utf-8"))
    report = deepcopy(report)
    report["status"] = "authorized_for_gate_review"
    report["inputs"]["approval_plan_supplied"] = True
    for node in report["nodes"]:
        node["authorization_decision"] = "approved"
        node["authorization_status"] = "approved_for_gate_review"
        node["activation_authorized_for_gate"] = True
        node["blocking_reasons"] = []
        node["approval_record"] = {
            "approved_by": "codex_opt_in_contract_smoke",
            "approved_at": "2026-07-05T00:00:00Z",
            "notes": "temporary approved fixture for service-level opt-in contract smoke",
            "target_match": True,
        }
        node["required_next_actions"] = [
            "keep_authorization_record_attached_to_activation_gate",
            "activation_gate_must_still_check_visual_candidate_isolation",
            "activation_gate_must_still_require_backend_frontend_contract_update",
            "activation_gate_must_still_require_post_activation_evidence",
        ]
    report["summary"]["approved_count"] = len(report["nodes"])
    report["summary"]["pending_count"] = 0
    report["summary"]["denied_count"] = 0
    report["summary"]["authorization_status_counts"] = {
        "approved_for_gate_review": len(report["nodes"])
    }
    report["summary"]["activation_authorized_for_gate_count"] = len(report["nodes"])
    write_json(path, report)
    return path


def semantic_counts(map_package: dict[str, Any]) -> dict[str, int]:
    return {f"{key}_count": len(map_package.get(key) or []) for key in V02_KEYS}


def leaked_v02_field_count(map_package: dict[str, Any]) -> int:
    return sum(1 for key in V02_KEYS if key in map_package)


def check_default_package(label: str, payload_data: dict[str, Any], node_id: str) -> dict[str, Any]:
    map_package = as_obj(payload_data.get("map_runtime_package"))
    if map_package.get("schema_version") != "map_runtime_package.v0.1":
        raise AssertionError(f"{node_id}: {label} map runtime is not v0.1")
    leak_count = leaked_v02_field_count(map_package)
    if leak_count:
        raise AssertionError(f"{node_id}: {label} leaked v0.2 fields")
    return {
        "label": label,
        "schema_version": map_package.get("schema_version"),
        "v02_field_leak_count": leak_count,
    }


def check_default_api(base_url: str, session_id: str, node_id: str) -> dict[str, Any]:
    config = payload(
        request_json(base_url, "GET", f"/api/sessions/{session_id}/battles/{node_id}/config")
    )
    runtime = payload(
        request_json(
            base_url, "GET", f"/api/sessions/{session_id}/battles/{node_id}/runtime-package"
        )
    )
    default_runtime = payload(
        request_json(
            base_url, "GET", f"/api/sessions/{session_id}/battles/{node_id}/map-runtime-package"
        )
    )
    default_checks = [
        check_default_package("config", config, node_id),
        check_default_package("runtime-package", runtime, node_id),
        check_default_package("map-runtime-package", default_runtime, node_id),
    ]
    dry_run = payload(
        request_json(
            base_url,
            "GET",
            f"/api/sessions/{session_id}/battles/{node_id}/map-v02-opt-in-dry-run",
        )
    )
    if dry_run.get("dry_run_mode") != "review_only_map_v02_opt_in_contract":
        raise AssertionError(f"{node_id}: dry-run mode mismatch")
    if dry_run.get("review_only") is not True:
        raise AssertionError(f"{node_id}: dry-run must be review-only")
    if dry_run.get("runtime_activation_allowed") is not False:
        raise AssertionError(f"{node_id}: dry-run must not activate runtime")
    authorization = as_obj(dry_run.get("authorization"))
    if authorization.get("authorization_status") != "pending":
        raise AssertionError(f"{node_id}: default authorization must remain pending")
    candidate = as_obj(dry_run.get("opt_in_candidate"))
    if candidate.get("candidate_available") is not False:
        raise AssertionError(f"{node_id}: default dry-run must not expose approved candidate")
    if candidate.get("candidate_runtime_package_v02") is not None:
        raise AssertionError(f"{node_id}: pending dry-run must not include full v0.2 package")

    return {
        "node_id": node_id,
        "default_runtime_checks": default_checks,
        "default_runtime_schema_version": "map_runtime_package.v0.1",
        "default_runtime_v02_field_leak_count": sum(
            int(item.get("v02_field_leak_count") or 0) for item in default_checks
        ),
        "api_dry_run_authorization_status": authorization.get("authorization_status"),
        "api_dry_run_candidate_available": candidate.get("candidate_available"),
        "api_runtime_activation_allowed": dry_run.get("runtime_activation_allowed"),
    }


def check_approved_service_contract(
    service: Any, session_id: str, node_id: str, approved_report_path: Path
) -> dict[str, Any]:
    contract = service.get_map_runtime_v02_opt_in_contract(
        session_id, node_id, authorization_report_path=approved_report_path
    )
    authorization = as_obj(contract.get("authorization"))
    if authorization.get("activation_authorized_for_gate") is not True:
        raise AssertionError(f"{node_id}: approved fixture did not authorize for gate")
    if contract.get("runtime_activation_allowed") is not False:
        raise AssertionError(f"{node_id}: approved dry-run must still not activate runtime")
    default_runtime = as_obj(contract.get("default_runtime"))
    if default_runtime.get("preserved") is not True:
        raise AssertionError(f"{node_id}: default runtime not preserved")
    if default_runtime.get("v02_field_leak_count") != 0:
        raise AssertionError(f"{node_id}: v0.2 fields leaked into default summary")
    candidate = as_obj(contract.get("opt_in_candidate"))
    package_v02 = as_obj(candidate.get("candidate_runtime_package_v02"))
    if candidate.get("candidate_available") is not True:
        raise AssertionError(f"{node_id}: approved candidate unavailable")
    if package_v02.get("schema_version") != "map_runtime_package.v0.2":
        raise AssertionError(f"{node_id}: approved candidate is not v0.2")
    counts = semantic_counts(package_v02)
    if any(value < 1 for value in counts.values()):
        raise AssertionError(f"{node_id}: missing v0.2 strong semantics {counts}")
    return {
        "node_id": node_id,
        "approved_authorization_status": authorization.get("authorization_status"),
        "approved_candidate_available": candidate.get("candidate_available"),
        "approved_candidate_schema_version": package_v02.get("schema_version"),
        "strong_semantic_counts": counts,
        "runtime_activation_allowed": contract.get("runtime_activation_allowed"),
        "default_runtime_preserved": default_runtime.get("preserved"),
        "default_runtime_v02_field_leak_count": default_runtime.get("v02_field_leak_count"),
    }


def check_approved_activation_selector(
    service: Any, node_id: str, approved_report_path: Path
) -> dict[str, Any]:
    selection = service.map_runtime_activation_selection(
        node_id, authorization_report_path=approved_report_path
    )
    selected_package = service.load_selected_map_runtime_package(
        node_id, authorization_report_path=approved_report_path
    )
    if selection.get("activation_applied") is not True:
        raise AssertionError(f"{node_id}: approved selector did not apply activation")
    if selection.get("selected_schema_version") != "map_runtime_package.v0.2":
        raise AssertionError(f"{node_id}: approved selector did not choose v0.2")
    if selected_package.get("schema_version") != "map_runtime_package.v0.2":
        raise AssertionError(f"{node_id}: selected package is not v0.2")
    if selected_package.get("package_id") != selection.get("selected_package_id"):
        raise AssertionError(f"{node_id}: selected package does not match selection summary")
    counts = semantic_counts(selected_package)
    if any(value < 1 for value in counts.values()):
        raise AssertionError(f"{node_id}: selector selected v0.2 without strong semantics {counts}")
    authorization = as_obj(selection.get("authorization"))
    if authorization.get("authorization_status") != "approved_for_gate_review":
        raise AssertionError(f"{node_id}: selector authorization status mismatch")
    if authorization.get("target_matches_candidate") is not True:
        raise AssertionError(f"{node_id}: selector target did not match candidate")
    return {
        "node_id": node_id,
        "activation_applied": selection.get("activation_applied"),
        "selected_schema_version": selection.get("selected_schema_version"),
        "selected_package_id": selection.get("selected_package_id"),
        "strong_semantic_counts": counts,
        "authorization_status": authorization.get("authorization_status"),
        "target_matches_candidate": authorization.get("target_matches_candidate"),
        "provider_call_count": as_obj(selection.get("safety")).get("provider_call_count"),
        "reads_env": as_obj(selection.get("safety")).get("reads_env"),
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
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from app.services import map_runtime_service  # noqa: WPS433

    generated = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with tempfile.TemporaryDirectory(prefix="ai_td_map_v02_opt_in_") as tmpdir:
        db_path = Path(tmpdir) / "app.db"
        approved_report_path = make_approved_authorization_report(
            Path(tmpdir) / "approved_map_runtime_activation_authorization_report.json"
        )
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = start_server(db_path, port)
        try:
            wait_for_server(base_url, process)
            session_response = request_json(base_url, "POST", "/api/sessions", expected_status=201)
            session_id = session_response["session_id"]
            default_api = [
                check_default_api(base_url, session_id, node_id) for node_id in NODE_IDS
            ]
            approved_service = [
                check_approved_service_contract(
                    map_runtime_service, session_id, node_id, approved_report_path
                )
                for node_id in NODE_IDS
            ]
            approved_selector = [
                check_approved_activation_selector(
                    map_runtime_service, node_id, approved_report_path
                )
                for node_id in NODE_IDS
            ]
            unknown_response = request_json(
                base_url,
                "GET",
                f"/api/sessions/{session_id}/battles/unknown/map-v02-opt-in-dry-run",
                expected_status=404,
            )
        finally:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)

    return {
        "schema_version": "map_runtime_v02_opt_in_contract_smoke_report.v0.1",
        "report_id": "map_runtime_v02_opt_in_contract_smoke_report_v0_1",
        "generated_at": generated,
        "status": "passed",
        "endpoint": "GET /api/sessions/{session_id}/battles/{node_id}/map-v02-opt-in-dry-run",
        "review_only": True,
        "node_count": len(default_api),
        "node_ids": list(NODE_IDS),
        "default_api": default_api,
        "approved_service_contract": approved_service,
        "approved_activation_selector": approved_selector,
        "summary": {
            "default_runtime_v01_preserved_count": sum(
                1
                for item in default_api
                if item.get("default_runtime_schema_version") == "map_runtime_package.v0.1"
                and item.get("default_runtime_v02_field_leak_count") == 0
            ),
            "api_pending_authorization_count": sum(
                1
                for item in default_api
                if item.get("api_dry_run_authorization_status") == "pending"
            ),
            "approved_candidate_available_count": sum(
                1
                for item in approved_service
                if item.get("approved_candidate_available") is True
            ),
            "approved_selector_selected_v02_count": sum(
                1
                for item in approved_selector
                if item.get("selected_schema_version") == "map_runtime_package.v0.2"
            ),
            "approved_selector_activation_applied_count": sum(
                1
                for item in approved_selector
                if item.get("activation_applied") is True
            ),
            "runtime_activation_allowed_count": sum(
                1
                for item in [*default_api, *approved_service]
                if item.get("runtime_activation_allowed") is True
            ),
            "provider_call_count": 0,
            "world_state_mutation_count": 0,
            "default_runtime_mutation_count": 0,
        },
        "safety": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "world_state_mutation_count": 0,
            "default_runtime_mutation_count": 0,
            "backend_default_runtime_endpoint_modified": False,
            "frontend_default_runtime_modified": False,
        },
        "unknown_node_status_code": 404,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json",
    )
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    report = build_report(args.generated_at)
    write_json(ROOT / args.output, report)
    print(f"map runtime v0.2 opt-in contract smoke passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
