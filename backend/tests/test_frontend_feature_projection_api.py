"""Focused API tests for activated frontend feature projections."""

from __future__ import annotations

import asyncio

import fastapi.routing
import httpx

from app.main import create_app
from tools.frontend.validate_frontend_feature_snapshots import validate_bundle


async def _create_session(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/sessions")
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _payload(response):
    assert response.status_code < 400, response.text
    body = response.json()
    assert body["mode"] == "frontend_mock_fixture"
    return body["payload"]


def _run_api_scenario(monkeypatch, scenario) -> None:
    async def run() -> None:
        # The current local Starlette/AnyIO combination stalls its worker-thread
        # bridge. Executing sync route callables inline keeps this focused ASGI
        # contract test deterministic without changing production behavior.
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


def test_feature_snapshot_api_projects_activated_world_state(app_env, monkeypatch):
    async def scenario(client: httpx.AsyncClient) -> None:
        session_id = await _create_session(client)
        _payload(await client.post(f"/api/sessions/{session_id}/world-instance"))

        pack = _payload(await client.get(f"/api/sessions/{session_id}/frontend-mock-pack"))
        runtime = _payload(
            await client.get(f"/api/sessions/{session_id}/runtime/feature-snapshots")
        )
        map_payload = _payload(await client.get(f"/api/sessions/{session_id}/map"))

        for bundle in (
            pack["activated_runtime_bundle"],
            runtime["activated_runtime_bundle"],
            map_payload["activated_runtime_bundle"],
        ):
            assert bundle["frontend_role"] == "consume_only"
            assert bundle["activation_receipt"]["runtime_safe_scan"] == "passed"
            assert bundle["runtime_selection"]["activation_applied"] is True
            assert validate_bundle(bundle) == []

        snapshots = runtime["activated_runtime_bundle"]["feature_snapshots"]
        contribution_ids = {
            item["contribution_id"]
            for item in snapshots["strategic_map"]["contributions"]
        }
        assert "compiled_objective_gray_station_supply_watch" in contribution_ids
        assert "world_npc_engineer_001_gray_lantern_station" in contribution_ids
        assert any(
            item["kind"] == "narrative_beat"
            for item in snapshots["narrative"]["contributions"]
        )

    _run_api_scenario(monkeypatch, scenario)


def test_feature_snapshots_follow_research_and_settlement_state(app_env, monkeypatch):
    async def scenario(client: httpx.AsyncClient) -> None:
        session_id = await _create_session(client)
        _payload(await client.post(f"/api/sessions/{session_id}/world-instance"))
        proposal_response = await client.post(
            f"/api/sessions/{session_id}/research/proposals",
            json={
                "intent_text": "把灯芯和导线编成减速装置",
                "node_id": "gray_lantern_station",
            },
        )
        assert proposal_response.status_code == 201
        proposal = proposal_response.json()

        runtime_after_proposal = _payload(
            await client.get(
                f"/api/sessions/{session_id}/runtime/feature-snapshots"
                "?node_id=gray_lantern_station"
            )
        )["activated_runtime_bundle"]
        assert validate_bundle(runtime_after_proposal) == []
        workshop = runtime_after_proposal["feature_snapshots"]["workshop"]
        proposal_items = [
            item
            for item in workshop["contributions"]
            if item["kind"] == "proposal_hint"
        ]
        assert proposal_items
        assert proposal_items[0]["payload"]["title"] == proposal["display_name"]
        assert runtime_after_proposal["runtime_selection"]["current_node_id"] == (
            "gray_lantern_station"
        )

        settlement_response = _payload(
            await client.post(
                f"/api/sessions/{session_id}/battles/gray_lantern_station/results",
                json={"result": "victory", "protected_core_hp": 8},
            )
        )
        runtime_after_battle = settlement_response["activated_runtime_bundle"]
        assert validate_bundle(runtime_after_battle) == []
        settlement = runtime_after_battle["feature_snapshots"]["settlement"]
        assert {item["slot"] for item in settlement["contributions"]} == {
            "result_summary",
            "world_delta",
        }
        assert all(
            item["payload"]["node_id"] == "gray_lantern_station"
            for item in settlement["contributions"]
        )
        world_delta = next(
            item for item in settlement["contributions"] if item["slot"] == "world_delta"
        )
        assert "灰灯驿站首战结束" in world_delta["payload"]["summary"]
        assert "样品对高速敌潮有效" not in world_delta["payload"]["summary"]

    _run_api_scenario(monkeypatch, scenario)
