"""Tests for the fixture-backed frontend mock API surface."""

from __future__ import annotations

import sqlite3


def _create_session(client) -> str:
    resp = client.post("/api/sessions")
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def _payload(resp):
    assert resp.status_code < 400, resp.text
    body = resp.json()
    assert body["mode"] == "frontend_mock_fixture"
    return body["payload"]


def test_frontend_mock_pack_exposes_generated_media_and_animation_seeds(client):
    sid = _create_session(client)
    payload = _payload(client.get(f"/api/sessions/{sid}/frontend-mock-pack"))

    pack = payload["pack"]
    media_manifest = payload["media_manifest"]
    animation_seed_manifest = payload["animation_seed_manifest"]

    assert pack["schema_version"] == "frontend_mock_pack.v0.1"
    assert len(pack["assets"]) == 11
    assert media_manifest["summary"]["generated_count"] == 22
    assert media_manifest["summary"]["processed_count"] == 22
    assert animation_seed_manifest["summary"]["media_count"] == 22
    assert payload["animation_pipeline_status"] == (
        "seed_images_ready_video_frames_not_generated"
    )

    first_icon = pack["assets"][0]["media_refs"]["generated_roles"]["icon"]["url"]
    media_resp = client.get(first_icon)
    assert media_resp.status_code == 200
    assert media_resp.headers["content-type"] == "image/png"


def test_world_instance_opening_map_and_briefing_flow(client, raw_conn: sqlite3.Connection):
    sid = _create_session(client)

    created = _payload(
        client.post(
            f"/api/sessions/{sid}/world-instance",
            json={"selected_options": {"creativity_mode": "experimental"}},
        )
    )
    assert created["world_instance"]["selected_options"]["creativity_mode"] == "experimental"
    assert created["run_world_state"]["progress"]["phase"] == "first_defense"

    world_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM world_instance WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    state_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM campaign_state WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    assert world_rows == 1
    assert state_rows == 1

    opening = _payload(client.get(f"/api/sessions/{sid}/opening"))
    assert opening["opening"]

    animation = _payload(client.get(f"/api/sessions/{sid}/animation-seeds"))
    assert animation["animation_seed_manifest"]["summary"]["media_count"] == 22

    map_payload = _payload(client.get(f"/api/sessions/{sid}/map"))
    assert map_payload["map"]["display_name"] == "余灯中枢态势图"
    assert map_payload["run_world_state"]["progress"]["phase"] == "first_defense"

    briefing = _payload(
        client.get(f"/api/sessions/{sid}/nodes/gray_lantern_station/briefing")
    )
    assert briefing["briefing"]["node_id"] == "gray_lantern_station"
    assert briefing["suggested_input"]


def test_battle_runtime_settlement_and_evidence_flow(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    battle = _payload(client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/config"))
    assert battle["battle_config"]["sample_asset"]["delivery_delay_ms"] == 30000
    assert battle["toolbar_assets"]
    assert battle["sample_delivery_asset"]["stable_internal_id"] == "asset_mirror_lure_trap_001"
    assert battle["animation_pipeline_status"] == (
        "seed_images_ready_video_frames_not_generated"
    )

    runtime = _payload(
        client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/runtime-package")
    )
    assert runtime["runtime_package"]["schema_version"] == "runtime_package.v0.1"
    assert runtime["sample_delivery_asset"]["media_refs"]["mode"] == "generated"

    settlement = _payload(
        client.post(
            f"/api/sessions/{sid}/battles/gray_lantern_station/results",
            json={
                "result": "victory",
                "protected_core_hp": 7,
                "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
                "leaked_enemy_count": 1,
            },
        )
    )
    assert settlement["settlement"]["result"] == "victory"
    assert settlement["settlement"]["world_delta"]["delta_id"] == "delta_first_battle_result_001"
    assert settlement["settlement"]["run_world_state"]["progress"]["phase"] == (
        "post_first_defense"
    )

    latest = _payload(client.get(f"/api/sessions/{sid}/settlement/latest"))
    assert latest["settlement"]["world_delta"]["source"] == "battle_result"

    evidence = _payload(client.get(f"/api/sessions/{sid}/evidence"))
    assert evidence["audit_summary"]["overall_status"] == "passed"
    assert evidence["battle_result"]["settlement"]["node_id"] == "gray_lantern_station"


def test_frontend_mock_endpoints_require_existing_session(client):
    resp = client.get("/api/sessions/missing/frontend-mock-pack")
    assert resp.status_code == 404
    assert "session not found" in resp.json()["detail"].lower()


def test_unknown_node_returns_404(client):
    sid = _create_session(client)
    resp = client.get(f"/api/sessions/{sid}/nodes/unknown/briefing")
    assert resp.status_code == 404
    assert "mock fixture not found" in resp.json()["detail"]
