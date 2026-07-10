"""Scheduler PromotionReport-to-runtime apply gate contracts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fastapi.routing
import httpx

from app.api import sessions as sessions_api
from app.db import db_cursor, now_iso
from app.main import create_app
from app.services.generation_scheduler_artifact_ledger_builders import (
    compact_provider_artifact_promotion_report,
)
from app.services.generation_scheduler_artifact_ledger_repository import (
    upsert_generation_artifact_ledger,
)
from app.services.generation_scheduler_run_queue_repository import (
    load_generation_queue_item_row,
    update_generation_queue_item,
)
from tools.frontend.validate_frontend_feature_snapshots import validate_bundle


_ROOT = Path(__file__).resolve().parents[2]
_SESSION_ID = "session_provider_promotion_sample"
_SCHEDULE_ITEM_ID = "sched_static_fallback_runtime_route"
_PROMOTION_REPORT = (
    _ROOT
    / "examples/provider_artifact_staging/"
    "provider_runtime_activation_sample.promotion_report.json"
)


def _payload(response: httpx.Response) -> dict:
    assert response.status_code in {200, 201}, response.text
    return response.json()["payload"]


async def _create_scheduler_candidate(client: httpx.AsyncClient) -> str:
    created = await client.post("/api/sessions")
    assert created.status_code == 201, created.text
    assert created.json()["session_id"] == _SESSION_ID
    run_payload = _payload(
        await client.post(f"/api/sessions/{_SESSION_ID}/generation-schedule/runs")
    )
    run_id = run_payload["generation_schedule_run"]["run_id"]

    queue_row = load_generation_queue_item_row(
        _SESSION_ID, _SCHEDULE_ITEM_ID, run_id
    )
    assert queue_row is not None
    queue_item = queue_row["payload"]
    queue_item["object_kind"] = "runtime_package"
    queue_item["object_ref"] = "runtime_package:provider_promotion_sample"
    queue_item["status"] = "waiting_review"
    update_generation_queue_item(
        queue_row["id"], "waiting_review", queue_item, now_iso()
    )

    report = json.loads(_PROMOTION_REPORT.read_text(encoding="utf-8"))
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": (
                f"gled_{_SESSION_ID}_provider_artifact_promotion_report_"
                "provider_runtime_activation_sample"
            ),
            "run_id": run_id,
            "session_id": _SESSION_ID,
            "schedule_item_id": _SCHEDULE_ITEM_ID,
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": report["report_id"],
            "status": "promotion_allowed",
            "created_at": report["created_at"],
            "updated_at": report["created_at"],
            "compact": compact_provider_artifact_promotion_report(report),
        }
    )
    return run_id


def _run_api_scenario(monkeypatch, scenario) -> None:
    async def run() -> None:
        async def run_inline(function, *args, **kwargs):
            return function(*args, **kwargs)

        monkeypatch.setattr(fastapi.routing, "run_in_threadpool", run_inline)
        monkeypatch.setattr(sessions_api, "_new_session_id", lambda: _SESSION_ID)
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await scenario(client)

    asyncio.run(run())


def test_provider_promotion_report_closes_scheduler_runtime_apply_loop(
    app_env, monkeypatch
):
    async def scenario(client: httpx.AsyncClient) -> None:
        await _create_scheduler_candidate(client)
        endpoint = (
            f"/api/sessions/{_SESSION_ID}/generation-schedule/workers/"
            "apply-runtime-activation"
        )

        unauthorized = await client.post(
            endpoint, json={"schedule_item_id": _SCHEDULE_ITEM_ID}
        )
        assert unauthorized.status_code == 409
        assert "authorization" in unauthorized.text

        readiness = _payload(
            await client.post(
                f"/api/sessions/{_SESSION_ID}/generation-schedule/workers/"
                "run-runtime-activation-readiness-chain",
                json={"schedule_item_id": _SCHEDULE_ITEM_ID},
            )
        )
        target = readiness["generation_runtime_artifact_build_report"][
            "resolved_targets"
        ]["runtime_package_refs"][0]
        assert target["path"].endswith(
            "provider_promotion_sample.runtime_package.json"
        )
        assert len(target["sha256"]) == 64

        applied = _payload(
            await client.post(endpoint, json={"schedule_item_id": _SCHEDULE_ITEM_ID})
        )
        receipt = applied["runtime_activation_receipt"]
        assert receipt["schema_version"] == "runtime_activation_receipt.v0.1"
        assert receipt["source"]["kind"] == "generation_schedule"
        assert receipt["status"] == "activated"
        assert receipt["promotion"] == {
            "mode": "provider_promotion_report",
            "status": "passed",
            "evidence_id": "ppromo_provider_runtime_activation_sample_001",
        }
        assert receipt["validation"]["behavior_abi"]["status"] == "passed"
        assert receipt["validation"]["media"]["status"] == "passed"
        assert receipt["runtime_effect"]["activated_object_ids"] == [
            "provider_promoted_lamp_tower_001"
        ]

        bundle = applied["activated_runtime_bundle"]
        assert validate_bundle(bundle) == []
        capability = next(
            item
            for item in bundle["capabilities"]["battle_objects"]
            if item["object_id"] == "provider_promoted_lamp_tower_001"
        )
        assert capability["behavior_abi"]["effect_blocks"][0]["amount"] == 15
        assert capability["source_runtime_ref"]["activation_id"] == receipt[
            "activation_id"
        ]

        cache_item = next(
            item
            for item in applied["generation_prefetch_cache"]["items"]
            if item["schedule_item_id"] == _SCHEDULE_ITEM_ID
        )
        assert cache_item["cache_status"] == "runtime_activated"
        assert cache_item["runtime_ready"] is True
        gate_item = next(
            item
            for item in applied["generation_activation_gate"]["items"]
            if item["schedule_item_id"] == _SCHEDULE_ITEM_ID
        )
        assert gate_item["activation_status"] == "activated"
        assert gate_item["runtime_ready"] is True
        daemon = _payload(
            await client.get(
                f"/api/sessions/{_SESSION_ID}/generation-schedule/daemon-readiness"
            )
        )["generation_daemon_readiness"]
        assert daemon["summary"]["runtime_activated_count"] == 1
        assert daemon["summary"]["runtime_ready_count"] == 1
        assert "wait_for_runtime_activation_apply_gate" not in {
            item["action"] for item in daemon["recommended_next_actions"]
        }

        applied_again = _payload(
            await client.post(endpoint, json={"schedule_item_id": _SCHEDULE_ITEM_ID})
        )
        assert applied_again["runtime_activation_receipt"] == receipt
        with db_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM runtime_activations "
                "WHERE session_id = ? AND source_kind = 'generation_schedule'",
                (_SESSION_ID,),
            )
            assert cur.fetchone()["count"] == 1

    _run_api_scenario(monkeypatch, scenario)


def test_scheduler_apply_rejects_post_authorization_target_tampering(
    app_env, monkeypatch
):
    async def scenario(client: httpx.AsyncClient) -> None:
        run_id = await _create_scheduler_candidate(client)
        _payload(
            await client.post(
                f"/api/sessions/{_SESSION_ID}/generation-schedule/workers/"
                "run-runtime-activation-readiness-chain",
                json={"schedule_item_id": _SCHEDULE_ITEM_ID},
            )
        )
        with db_cursor() as cur:
            cur.execute(
                "SELECT ledger_id, payload FROM generation_artifact_ledger "
                "WHERE session_id = ? AND run_id = ? AND schedule_item_id = ? "
                "AND artifact_kind = 'generation_runtime_activation_authorization'",
                (_SESSION_ID, run_id, _SCHEDULE_ITEM_ID),
            )
            row = cur.fetchone()
            assert row is not None
            payload = json.loads(row["payload"])
            payload["compact"]["resolved_targets"]["runtime_package_refs"][0][
                "sha256"
            ] = "f" * 64
            cur.execute(
                "UPDATE generation_artifact_ledger SET payload = ? WHERE ledger_id = ?",
                (json.dumps(payload, ensure_ascii=False), row["ledger_id"]),
            )

        rejected = await client.post(
            f"/api/sessions/{_SESSION_ID}/generation-schedule/workers/"
            "apply-runtime-activation",
            json={"schedule_item_id": _SCHEDULE_ITEM_ID},
        )
        assert rejected.status_code == 409
        assert "changed after review" in rejected.text
        with db_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS count FROM runtime_activations WHERE session_id = ?",
                (_SESSION_ID,),
            )
            assert cur.fetchone()["count"] == 0

    _run_api_scenario(monkeypatch, scenario)
