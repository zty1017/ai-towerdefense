"""End-to-end contracts for session-scoped runtime activation and rollback."""

from __future__ import annotations

import asyncio

import fastapi.routing
import httpx
import pytest

from app.db import db_cursor
from app.main import create_app
from app.services import runtime_activation_service
from app.services.runtime_activation_service import _normalize_behavior
from tools.frontend.validate_frontend_feature_snapshots import validate_bundle


def _assert_receipt_valid(receipt: dict) -> None:
    assert receipt["schema_version"] == "runtime_activation_receipt.v0.1"
    assert receipt["status"] in {"activated", "blocked", "rolled_back"}
    assert receipt["source"]["kind"] == "research_job"
    assert len(receipt["source"]["runtime_package_sha256"]) == 64
    assert set(receipt["validation"]) == {
        "package_schema", "runtime_safety", "semantic", "behavior_abi", "media"
    }
    assert receipt["promotion"]["status"] in {"passed", "blocked"}
    assert receipt["runtime_effect"]["scope"] == "anonymous_session"
    assert receipt["rollback"]["supported"] is True
    assert receipt["safety"]["reads_env_file"] is False
    assert receipt["safety"]["calls_provider"] is False
    assert receipt["safety"]["writes_world_state"] is False


async def _create_session(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/sessions")
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


async def _compile_job(client: httpx.AsyncClient, session_id: str) -> dict:
    proposal_response = await client.post(
        f"/api/sessions/{session_id}/research/proposals",
        json={
            "intent_text": "把灯芯和导线编成能拖慢影潮的临时装置",
            "node_id": "gray_lantern_station",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["proposal_id"]
    job_response = await client.post(
        f"/api/sessions/{session_id}/research/proposals/{proposal_id}/confirm",
        json={},
    )
    assert job_response.status_code == 200, job_response.text
    assert job_response.json()["status"] == "completed"
    return job_response.json()


def _run_api_scenario(monkeypatch, scenario) -> None:
    async def run() -> None:
        async def run_inline(function, *args, **kwargs):
            return function(*args, **kwargs)

        monkeypatch.setattr(fastapi.routing, "run_in_threadpool", run_inline)
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await scenario(client)

    asyncio.run(run())


def test_activation_is_idempotent_projected_and_rollbackable(app_env, monkeypatch):
    async def scenario(client: httpx.AsyncClient) -> None:
        session_id = await _create_session(client)
        job = await _compile_job(client, session_id)
        endpoint = (
            f"/api/sessions/{session_id}/research/jobs/{job['job_id']}/activate"
        )

        first = await client.post(endpoint, json={})
        assert first.status_code == 200, first.text
        first_body = first.json()
        receipt = first_body["activation_receipt"]
        _assert_receipt_valid(receipt)
        assert receipt["status"] == "activated"
        assert receipt["promotion"]["mode"] == "trusted_deterministic_workflow"
        assert receipt["runtime_effect"]["applied"] is True
        assert receipt["safety"]["player_runtime_mutation_count"] == 1
        assert receipt["validation"]["behavior_abi"]["status"] == "degraded"
        assert receipt["validation"]["media"]["status"] == "degraded"

        bundle = first_body["activated_runtime_bundle"]
        assert validate_bundle(bundle) == []
        assert bundle["runtime_selection"]["session_activation_ids"] == [
            receipt["activation_id"]
        ]
        activated_id = receipt["runtime_effect"]["activated_object_ids"][0]
        capability = next(
            item
            for item in bundle["capabilities"]["battle_objects"]
            if item["object_id"] == activated_id
        )
        assert capability["schema_version"] == "battle_object_capability.v0.1"
        assert capability["source_runtime_ref"]["activation_id"] == receipt["activation_id"]
        assert capability["source_runtime_ref"]["node_id"] == "gray_lantern_station"
        assert capability["media_refs"]["icon"]["url"].startswith(
            "/assets/frontend_mock/processed/"
        )

        second = await client.post(endpoint, json={})
        assert second.status_code == 200, second.text
        assert second.json()["activation_receipt"] == receipt
        listed = await client.get(
            f"/api/sessions/{session_id}/runtime/activations"
        )
        assert listed.status_code == 200, listed.text
        assert len(listed.json()["activation_receipts"]) == 1

        rollback = await client.post(
            f"/api/sessions/{session_id}/runtime/activations/"
            f"{receipt['activation_id']}/rollback",
            json={},
        )
        assert rollback.status_code == 200, rollback.text
        rolled_back = rollback.json()["activation_receipt"]
        _assert_receipt_valid(rolled_back)
        assert rolled_back["status"] == "rolled_back"
        assert rolled_back["runtime_effect"]["applied"] is False
        restored_bundle = rollback.json()["activated_runtime_bundle"]
        assert restored_bundle["runtime_selection"]["session_activation_ids"] == []
        assert all(
            item["object_id"] != activated_id
            for item in restored_bundle["capabilities"]["battle_objects"]
        )

        second_rollback = await client.post(
            f"/api/sessions/{session_id}/runtime/activations/"
            f"{receipt['activation_id']}/rollback",
            json={},
        )
        assert second_rollback.status_code == 200
        assert second_rollback.json()["activation_receipt"] == rolled_back

        reset = await client.post(f"/api/sessions/{session_id}/reset", json={})
        assert reset.status_code == 200, reset.text
        after_reset = await client.get(
            f"/api/sessions/{session_id}/runtime/activations"
        )
        assert after_reset.status_code == 200
        assert after_reset.json()["activation_receipts"] == []

    _run_api_scenario(monkeypatch, scenario)


def test_missing_promotion_evidence_blocks_without_runtime_mutation(app_env, monkeypatch):
    async def scenario(client: httpx.AsyncClient) -> None:
        session_id = await _create_session(client)
        job = await _compile_job(client, session_id)
        with db_cursor() as cur:
            cur.execute(
                "UPDATE research_jobs SET trace_paths = '[]' WHERE job_id = ?",
                (job["job_id"],),
            )

        response = await client.post(
            f"/api/sessions/{session_id}/research/jobs/{job['job_id']}/activate",
            json={},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        receipt = body["activation_receipt"]
        _assert_receipt_valid(receipt)
        assert receipt["status"] == "blocked"
        assert receipt["runtime_effect"]["applied"] is False
        assert receipt["safety"]["player_runtime_mutation_count"] == 0
        assert any("promotion report" in item for item in receipt["blocked_reasons"])
        assert body["activated_runtime_bundle"]["runtime_selection"][
            "session_activation_ids"
        ] == []

    _run_api_scenario(monkeypatch, scenario)


def test_unavailable_schema_validator_blocks_runtime_mutation(app_env, monkeypatch):
    async def scenario(client: httpx.AsyncClient) -> None:
        session_id = await _create_session(client)
        job = await _compile_job(client, session_id)

        def unavailable(*_args, **_kwargs):
            raise runtime_activation_service.RuntimeSchemaValidationUnavailable(
                "validator unavailable in test"
            )

        monkeypatch.setattr(runtime_activation_service, "_schema_errors", unavailable)
        response = await client.post(
            f"/api/sessions/{session_id}/research/jobs/{job['job_id']}/activate",
            json={},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        receipt = body["activation_receipt"]
        assert receipt["status"] == "blocked"
        assert receipt["runtime_effect"]["applied"] is False
        assert receipt["safety"]["player_runtime_mutation_count"] == 0
        assert any(
            "schema validation unavailable" in reason
            for reason in receipt["blocked_reasons"]
        )
        assert body["activated_runtime_bundle"]["runtime_selection"][
            "session_activation_ids"
        ] == []

    _run_api_scenario(monkeypatch, scenario)


def test_behavior_abi_is_cropped_clamped_and_rejects_unknown_effects():
    raw = {
        "placement": {"mode": "build_slot", "slot_source": "map_runtime_package.build_slots"},
        "cost": {"resource": "materials", "amount": -500, "untrusted": "drop"},
        "cooldown": {"milliseconds": 999999},
        "targeting": {"mode": "nearest_path_enemy", "range_cells": 99},
        "effect_blocks": [
            {
                "effect_id": "damage",
                "kind": "damage",
                "amount": 9999,
                "damage_type": "unknown",
                "script": "drop",
            }
        ],
        "ui_surfaces": ["battle_hotbar"],
        "simulation_hooks": ["on_attack_tick"],
        "generated_code": "drop",
    }
    normalized = _normalize_behavior(raw, "tower_blueprint")
    assert normalized["cost"] == {"resource": "materials", "amount": 0}
    assert normalized["cooldown"] == {"milliseconds": 120000}
    assert normalized["targeting"]["range_cells"] == 8
    assert normalized["effect_blocks"][0] == {
        "effect_id": "damage",
        "kind": "damage",
        "amount": 320,
        "damage_type": "light",
    }
    assert "generated_code" not in normalized

    raw["effect_blocks"][0]["kind"] = "execute_script"
    with pytest.raises(ValueError, match="effect kind"):
        _normalize_behavior(raw, "tower_blueprint")


def test_compiled_candidate_stats_and_effects_lower_into_runtime_behavior():
    candidate = {
        "gameplay": {
            "base_stats": {
                "build_cost": 37,
                "range": 144,
                "cooldown": 2.5,
            },
            "effect_blocks": [
                {"type": "area_damage", "amount": 64, "radius": 96},
                {"type": "slow", "slow_ratio": 0.35, "duration": 1.8},
                {"type": "pierce_or_chain", "max_targets": 3},
            ],
        }
    }
    normalized = _normalize_behavior(candidate, "tower_blueprint")
    assert normalized["cost"] == {"resource": "materials", "amount": 37}
    assert normalized["cooldown"] == {"milliseconds": 2500}
    assert normalized["targeting"]["range_cells"] == 3
    assert normalized["effect_blocks"][0]["amount"] == 64
    assert normalized["effect_blocks"][0]["radius_cells"] == 2
    assert normalized["effect_blocks"][0]["max_targets"] == 3
    assert normalized["effect_blocks"][0]["chain_radius_cells"] == 2.4
    assert normalized["effect_blocks"][1]["strength"] == 0.35
    assert normalized["effect_blocks"][1]["duration_ms"] == 1800
