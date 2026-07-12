"""Durable queue and real background ResearchWorker contracts."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.db import db_cursor, now_iso
from app.services import research_service


def _seed_session_and_proposal() -> tuple[str, dict]:
    session_id = f"worker-{time.time_ns()}"
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (session_id, display_name, created_at, last_active_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, "worker test", ts, ts),
        )
    proposal = research_service.create_proposal(
        session_id,
        "在入口布置一份能拖慢影潮的临时装置",
        "gray_lantern_station",
    )
    return session_id, proposal


def _enqueue(monkeypatch) -> tuple[str, dict, dict]:
    monkeypatch.setenv("AI_TD_RESEARCH_WORKER_MODE", "background")
    session_id, proposal = _seed_session_and_proposal()
    job = research_service.confirm_proposal(session_id, proposal["proposal_id"])
    assert job["status"] == "queued"
    return session_id, proposal, job


def test_atomic_claim_allows_only_one_competing_consumer(app_env, monkeypatch):
    _session_id, _proposal, job = _enqueue(monkeypatch)
    barrier = threading.Barrier(2)

    def compete():
        barrier.wait()
        return research_service.claim_next_job()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _index: compete(), range(2)))

    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0]["job_id"] == job["job_id"]
    assert research_service.get_job(_session_id, job["job_id"])["status"] == "running"


def test_startup_recovery_returns_running_jobs_to_queue(app_env, monkeypatch):
    session_id, _proposal, job = _enqueue(monkeypatch)
    assert research_service.claim_next_job()["job_id"] == job["job_id"]

    assert research_service.recover_running_jobs() == 1
    recovered = research_service.get_job(session_id, job["job_id"])
    assert recovered["status"] == "queued"
    assert recovered["completed_at"] is None
    assert "重新接续" in recovered["player_state_message"]


def test_confirm_same_proposal_is_idempotent(app_env, monkeypatch):
    session_id, proposal, first = _enqueue(monkeypatch)
    second = research_service.confirm_proposal(session_id, proposal["proposal_id"])

    assert second["job_id"] == first["job_id"]
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS count FROM research_jobs WHERE proposal_id = ?",
            (proposal["proposal_id"],),
        )
        assert cur.fetchone()["count"] == 1


def test_claimed_job_failure_is_durable_and_player_safe(app_env, monkeypatch):
    session_id, _proposal, job = _enqueue(monkeypatch)
    claimed = research_service.claim_next_job()
    assert claimed is not None

    def fail_workflows(*_args, **_kwargs):
        raise RuntimeError("private workflow traceback detail")

    monkeypatch.setattr(research_service, "_run_two_workflows", fail_workflows)
    failed = research_service.run_claimed_job(claimed)

    assert failed["status"] == "failed"
    assert failed["completed_at"] is not None
    assert "traceback" not in failed["player_state_message"].lower()
    assert "workflow" not in failed["player_state_message"].lower()
    assert research_service.get_job(session_id, job["job_id"])["status"] == "failed"


def test_lifespan_worker_keeps_confirm_fast_and_completes_job(
    app_env: Path, monkeypatch
):
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("AI_TD_RESEARCH_WORKER_MODE", "background")
    monkeypatch.setenv("AI_TD_RESEARCH_WORKER_POLL_SECONDS", "0.01")
    workflow_started = threading.Event()
    allow_workflow_finish = threading.Event()

    def controlled_workflows(_session_id, _job_id, _proposal):
        workflow_started.set()
        assert allow_workflow_finish.wait(timeout=5)
        return {
            "ok": True,
            "error": None,
            "trace_paths": ["/tmp/research-worker-trace-a", "/tmp/research-worker-trace-b"],
            "runtime_package_path": "/tmp/research-worker-runtime-package.json",
            "delivery_payload_path": "/tmp/research-worker-delivery-payload.json",
            "promotion_report_path": None,
            "promotion_blocked": False,
            "media_status": "not_applicable",
            "media_evidence_path": None,
        }

    monkeypatch.setattr(research_service, "_run_two_workflows", controlled_workflows)
    app = create_app()
    with TestClient(app) as client:
        session = client.post("/api/sessions").json()
        proposal = client.post(
            f"/api/sessions/{session['session_id']}/research/proposals",
            json={
                "intent_text": "做一份临时迟滞装置",
                "node_id": "gray_lantern_station",
            },
        ).json()
        started_at = time.monotonic()
        response = client.post(
            f"/api/sessions/{session['session_id']}/research/proposals/"
            f"{proposal['proposal_id']}/confirm"
        )
        elapsed = time.monotonic() - started_at
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["status"] in {"queued", "running"}
        assert elapsed < 1.0
        assert workflow_started.wait(timeout=2)

        allow_workflow_finish.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = client.get(
                f"/api/sessions/{session['session_id']}/research/jobs/{job['job_id']}"
            ).json()
            if current["status"] == "completed":
                break
            time.sleep(0.02)
        assert current["status"] == "completed"
        assert current["completed_at"] is not None


def test_lifespan_worker_runs_existing_workflows_end_to_end(app_env: Path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("AI_TD_RESEARCH_WORKER_MODE", "background")
    monkeypatch.setenv("AI_TD_RESEARCH_WORKER_POLL_SECONDS", "0.01")
    with TestClient(create_app()) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        proposal = client.post(
            f"/api/sessions/{session_id}/research/proposals",
            json={
                "intent_text": "在入口布置一份能拖慢影潮的临时装置",
                "node_id": "gray_lantern_station",
            },
        ).json()
        queued = client.post(
            f"/api/sessions/{session_id}/research/proposals/"
            f"{proposal['proposal_id']}/confirm"
        ).json()
        assert queued["status"] == "queued"

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = client.get(
                f"/api/sessions/{session_id}/research/jobs/{queued['job_id']}"
            ).json()
            if current["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)

        assert current["status"] == "completed"
        assert Path(current["runtime_package_path"]).is_file()
        assert Path(current["delivery_payload_path"]).is_file()
        assert len(current["trace_paths"]) == 2
