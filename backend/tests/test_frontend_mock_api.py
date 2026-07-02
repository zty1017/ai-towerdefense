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
    runtime_art_kit = payload["runtime_art_kit"]
    runtime_art_media_manifest = payload["runtime_art_media_manifest"]
    core_artifacts = payload["ai_compile_core_artifacts"]

    assert pack["schema_version"] == "frontend_mock_pack.v0.1"
    assert len(pack["assets"]) == 11
    assert media_manifest["summary"]["generated_count"] == 22
    assert media_manifest["summary"]["processed_count"] == 22
    assert animation_seed_manifest["summary"]["media_count"] == 22
    assert runtime_art_kit["mode"] == "developer_compiled_runtime_art"
    assert len(runtime_art_kit["coverage"]["enemy_archetypes"]) == 3
    assert len(runtime_art_kit["procedural_effects"]) == 5
    assert runtime_art_media_manifest["summary"]["media_count"] == 18
    assert core_artifacts["context_package"]["schema_version"] == "context_package.v0.1"
    assert core_artifacts["fact_entry"]["schema_version"] == "fact_entry.v0.1"
    assert core_artifacts["compiled_game_object_package"]["schema_version"] == (
        "compiled_game_object_package.v0.1"
    )
    assert core_artifacts["world_delta_transaction"]["schema_version"] == (
        "world_state_delta_transaction.v0.1"
    )
    assert core_artifacts["refs"]["context_package"].endswith(
        "mvp_first_battle.context_package.json"
    )
    assert core_artifacts["refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    pack_core_artifacts = pack["core_artifacts"]
    assert pack_core_artifacts["status"] == (
        "frontend_pack_review_only_core_artifacts_ready"
    )
    assert pack_core_artifacts["review_only"] is True
    assert pack_core_artifacts["refs"] == core_artifacts["refs"]
    assert pack_core_artifacts["context_package"]["schema_version"] == (
        "context_package.v0.1"
    )
    assert pack_core_artifacts["fact_entry"]["schema_version"] == "fact_entry.v0.1"
    assert pack_core_artifacts["compiled_game_object_package"]["schema_version"] == (
        "compiled_game_object_package.v0.1"
    )
    assert payload["animation_pipeline_status"] == (
        "multiframe_atlas_ready_video_keyframes_not_generated"
    )
    assert payload["runtime_art_pipeline_status"] == (
        "developer_compiled_multiframe_atlas_ready_video_keyframes_not_generated"
    )

    first_icon = pack["assets"][0]["media_refs"]["generated_roles"]["icon"]["url"]
    media_resp = client.get(first_icon)
    assert media_resp.status_code == 200
    assert media_resp.headers["content-type"] == "image/png"

    runtime_icon = runtime_art_media_manifest["items"][0]["url"]
    runtime_media_resp = client.get(runtime_icon)
    assert runtime_media_resp.status_code == 200
    assert runtime_media_resp.headers["content-type"] == "image/png"


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

    runtime_art = _payload(client.get(f"/api/sessions/{sid}/runtime-art-kit"))
    assert runtime_art["runtime_art_kit"]["schema_version"] == (
        "frontend_battle_mock_art_kit.v0.1"
    )
    assert runtime_art["runtime_art_media_manifest"]["summary"]["asset_count"] == 9

    schedule = _payload(client.get(f"/api/sessions/{sid}/generation-schedule"))
    generation_schedule = schedule["generation_schedule"]
    buffer = generation_schedule["buffer"]
    assert generation_schedule["plan"]["schema_version"] == "generation_schedule_plan.v0.1"
    assert generation_schedule["run_report"]["schema_version"] == (
        "generation_schedule_run_report.v0.1"
    )
    assert generation_schedule["refs"]["plan"].endswith(
        "mvp_generation_schedule_plan.v0.1.json"
    )
    assert buffer["status"] == "fixture_backed_scheduler_buffer_ready"
    assert buffer["control_plane_mode"] == "review_only_dry_run"
    assert buffer["provider_call_count"] == 0
    assert buffer["world_mutation_count"] == 0
    assert buffer["latency_class_counts"]["sync_blocking"] == 3
    assert buffer["latency_class_counts"]["background_prefetch"] == 2
    assert buffer["fallback_selected_count"] == 1
    assert buffer["scheduled_count"] == 4
    assert buffer["activation_requires_revalidation"] is True
    assert {item["latency_class"] for item in buffer["items"]} >= {
        "sync_blocking",
        "background_prefetch",
        "background",
        "lazy",
        "fallback_static",
    }
    assert schedule["latest_generation_schedule_run"] is None

    schedule_run = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run = schedule_run["generation_schedule_run"]
    queue = schedule_run["generation_schedule_queue"]
    assert run["status"] == "completed"
    assert run["scheduler_mode"] == "fixture_backed_dry_run"
    assert run["generation_schedule"]["buffer"]["provider_call_count"] == 0
    assert run["generation_schedule"]["buffer"]["world_mutation_count"] == 0
    assert run["source_report_summary"]["scheduled_count"] == 4
    assert queue["summary"]["item_count"] == 8
    assert queue["summary"]["status_counts"] == {
        "completed": 3,
        "fallback_ready": 1,
        "queued": 4,
    }
    assert queue["summary"]["claimable_count"] == 4
    assert queue["summary"]["provider_review_required_count"] == 4
    schedule_run_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_runs WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    assert schedule_run_rows == 1
    queue_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_queue_items WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    assert queue_rows == 8

    latest_schedule_run = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/runs/latest")
    )
    assert latest_schedule_run["generation_schedule_run"]["run_id"] == run["run_id"]
    assert latest_schedule_run["generation_schedule_queue"]["summary"]["item_count"] == 8

    latest_queue = _payload(client.get(f"/api/sessions/{sid}/generation-schedule/queue"))
    assert latest_queue["generation_schedule_run"]["run_id"] == run["run_id"]
    assert latest_queue["generation_schedule_queue"]["summary"]["status_counts"]["queued"] == 4
    assert latest_queue["generation_schedule_worker_cache_summary"]["item_count"] == 0
    assert {
        item["latency_class"] for item in latest_queue["generation_schedule_queue"]["items"]
    } >= {"background_prefetch", "background", "lazy"}

    initial_worker_cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/worker-cache")
    )
    assert initial_worker_cache["generation_schedule_run"]["run_id"] == run["run_id"]
    assert initial_worker_cache["generation_schedule_worker_cache"]["summary"][
        "item_count"
    ] == 0

    worker_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={"worker_id": "dry-worker-test", "note": "dry worker smoke test"},
        )
    )
    assert worker_step["worker_step"]["status"] == "processed"
    assert worker_step["worker_step"]["provider_call_count"] == 0
    assert worker_step["worker_step"]["world_mutation_count"] == 0
    assert worker_step["generation_schedule_queue_item"]["status"] == "waiting_review"
    assert worker_step["generation_schedule_queue_item"]["worker_id"] == "dry-worker-test"
    assert worker_step["generation_schedule_queue"]["summary"]["waiting_review_count"] == 1
    assert worker_step["generation_schedule_queue"]["summary"]["claimable_count"] == 3
    worker_cache = worker_step["generation_schedule_worker_cache"]
    assert worker_cache["summary"]["item_count"] == 1
    assert worker_cache["summary"]["provider_call_count"] == 0
    assert worker_cache["summary"]["world_mutation_count"] == 0
    assert worker_cache["summary"]["activation_allowed_count"] == 0
    assert worker_cache["summary"]["review_required_count"] == 1
    cache_item = worker_cache["items"][0]
    assert cache_item["schedule_item_id"] == (
        worker_step["generation_schedule_queue_item"]["schedule_item_id"]
    )
    assert cache_item["worker_id"] == "dry-worker-test"
    assert cache_item["status"] == "waiting_review"
    assert cache_item["artifact_placeholder"]["status"] == "review_only_placeholder"
    assert cache_item["artifact_placeholder"]["provider_call_performed"] is False
    assert cache_item["artifact_placeholder"]["world_mutation_performed"] is False
    assert cache_item["artifact_placeholder"]["activation_allowed_now"] is False
    assert cache_item["activation_gate"]["blocked_reason"] == (
        "review_required_before_activation"
    )

    latest_worker_cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/worker-cache")
    )
    assert latest_worker_cache["generation_schedule_worker_cache"]["summary"][
        "item_count"
    ] == 1
    worker_cache_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_worker_cache WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert worker_cache_rows == 1

    reviewed_item_id = worker_step["generation_schedule_queue_item"]["schedule_item_id"]
    reviewed_complete = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{reviewed_item_id}/complete",
            json={"worker_id": "review-gate", "note": "manual review accepted"},
        )
    )
    assert reviewed_complete["generation_schedule_queue_item"]["status"] == "completed"
    assert (
        reviewed_complete["generation_schedule_queue"]["summary"]["waiting_review_count"] == 0
    )
    assert reviewed_complete["generation_schedule_queue"]["summary"]["status_counts"][
        "completed"
    ] == 4

    queued_item_id = next(
        item["schedule_item_id"]
        for item in reviewed_complete["generation_schedule_queue"]["items"]
        if item["status"] == "queued"
    )
    claimed = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{queued_item_id}/claim",
            json={"worker_id": "test-worker", "note": "claim for smoke test"},
        )
    )
    assert claimed["generation_schedule_queue_item"]["status"] == "claimed"
    assert claimed["generation_schedule_queue_item"]["claimed_by"] == "test-worker"
    assert claimed["generation_schedule_queue"]["summary"]["status_counts"]["claimed"] == 1
    assert claimed["generation_schedule_queue"]["summary"]["claimable_count"] == 2

    completed = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{queued_item_id}/complete",
            json={"worker_id": "test-worker", "note": "complete for smoke test"},
        )
    )
    assert completed["generation_schedule_queue_item"]["status"] == "completed"
    assert completed["generation_schedule_queue"]["summary"]["status_counts"]["completed"] == 5
    assert completed["generation_schedule_queue"]["summary"]["claimable_count"] == 2

    completed_sync_item_id = next(
        item["schedule_item_id"]
        for item in completed["generation_schedule_queue"]["items"]
        if item["dry_run_status"] == "passed"
    )
    conflict = client.post(
        f"/api/sessions/{sid}/generation-schedule/queue/{completed_sync_item_id}/claim"
    )
    assert conflict.status_code == 409
    assert "cannot claim" in conflict.json()["detail"]

    schedule_after_run = _payload(client.get(f"/api/sessions/{sid}/generation-schedule"))
    assert schedule_after_run["latest_generation_schedule_run"]["run_id"] == run["run_id"]

    map_payload = _payload(client.get(f"/api/sessions/{sid}/map"))
    assert map_payload["map"]["display_name"] == "余灯中枢态势图"
    assert map_payload["run_world_state"]["progress"]["phase"] == "first_defense"

    briefing = _payload(
        client.get(f"/api/sessions/{sid}/nodes/gray_lantern_station/briefing")
    )
    assert briefing["briefing"]["node_id"] == "gray_lantern_station"
    assert briefing["suggested_input"]

    reset = client.post(f"/api/sessions/{sid}/reset")
    assert reset.status_code == 200, reset.text
    worker_cache_rows_after_reset = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_worker_cache WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert worker_cache_rows_after_reset == 0


def test_campaign_router_prefetches_next_node_without_provider_calls(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    router_payload = _payload(client.get(f"/api/sessions/{sid}/campaign-router"))
    router = router_payload["campaign_router"]
    assert router["schema_version"] == "campaign_router.v0.1"
    assert router["router_mode"] == "fixture_backed_thin_router"
    assert router["current"]["node_id"] == "gray_lantern_station"
    assert router["current"]["playable"] is True
    assert router["next"]["node_id"] == "lamp_wick_store"
    assert router["next"]["asset_handle"]["status"] == "ready"
    assert router["scheduler_signal"]["latest_run_id"] is None
    assert router["boundary"]["provider_calls"] is False
    assert router["boundary"]["world_mutations"] is False

    prefetch_payload = _payload(
        client.post(f"/api/sessions/{sid}/campaign-router/prefetch-next")
    )
    request = prefetch_payload["prefetch_request"]
    assert request["target_node_id"] == "lamp_wick_store"
    assert request["created_generation_schedule_run"] is True
    assert request["provider_call_count"] == 0
    assert request["world_mutation_count"] == 0
    assert prefetch_payload["worker_step"]["status"] == "processed"
    assert prefetch_payload["generation_schedule_queue_item"]["status"] in {
        "completed",
        "waiting_review",
    }
    assert prefetch_payload["campaign_router"]["scheduler_signal"]["latest_run_id"]

    _payload(client.post(f"/api/sessions/{sid}/battles/gray_lantern_station/results"))
    after_battle_payload = _payload(client.get(f"/api/sessions/{sid}/campaign-router"))
    after_router = after_battle_payload["campaign_router"]
    assert after_router["run_progress"]["phase"] == "post_first_defense"
    assert after_router["current"]["node_id"] == "lamp_wick_store"
    assert after_router["next"]["node_id"] == "old_signal_tower"


def test_multinode_battle_results_advance_campaign_without_mislabeling(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    _payload(client.post(f"/api/sessions/{sid}/battles/gray_lantern_station/results"))
    wick_briefing = _payload(client.get(f"/api/sessions/{sid}/nodes/lamp_wick_store/briefing"))
    assert wick_briefing["briefing"]["node_id"] == "lamp_wick_store"
    wick_battle = _payload(client.get(f"/api/sessions/{sid}/battles/lamp_wick_store/config"))
    assert wick_battle["map_runtime_package"]["node_id"] == "lamp_wick_store"
    wick = _payload(
        client.post(
            f"/api/sessions/{sid}/battles/lamp_wick_store/results",
            json={"result": "victory", "protected_core_hp": 6},
        )
    )
    wick_settlement = wick["settlement"]
    assert wick_settlement["settlement_mode"] == "transaction"
    assert wick_settlement["world_delta"]["source"] == "battle_result"
    assert wick_settlement["world_delta_transaction"]["source"] == "battle_result"
    assert wick_settlement["world_delta_transaction"]["transaction_id"] == (
        "tx_stage_04_wick_store_pressure_battle_001"
    )
    assert wick_settlement["core_artifact_refs"]["world_delta_transaction"].endswith(
        "stage_04_wick_store_pressure_battle.world_delta_transaction.json"
    )
    assert wick_settlement["run_world_state"]["progress"]["phase"] == (
        "post_wick_store_defense"
    )

    tower_route = _payload(client.get(f"/api/sessions/{sid}/campaign-router"))
    assert tower_route["campaign_router"]["current"]["node_id"] == "old_signal_tower"
    tower_briefing = _payload(client.get(f"/api/sessions/{sid}/nodes/old_signal_tower/briefing"))
    assert tower_briefing["briefing"]["node_id"] == "old_signal_tower"
    tower = _payload(
        client.post(
            f"/api/sessions/{sid}/battles/old_signal_tower/results",
            json={"result": "victory", "protected_core_hp": 5},
        )
    )
    tower_settlement = tower["settlement"]
    assert tower_settlement["settlement_mode"] == "fixture_bridge"
    assert tower_settlement["world_delta"] is None
    assert tower_settlement["world_delta_transaction"]["source"] == "research_job"
    assert tower_settlement["fixture_baseline"]["baseline_type"] == "research_job"
    assert tower_settlement["fixture_baseline"]["baseline_ref"].endswith(
        "demo_after_stage_06_signal_resonance.run_world_state.json"
    )
    assert tower_settlement["run_world_state"]["progress"]["phase"] == (
        "signal_resonance_trial"
    )


def test_battle_runtime_settlement_and_evidence_flow(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))
    schedule_run = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))

    battle = _payload(client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/config"))
    assert battle["battle_config"]["sample_asset"]["delivery_delay_ms"] == 30000
    assert battle["map_runtime_package"]["schema_version"] == "map_runtime_package.v0.1"
    assert battle["map_runtime_package"]["build_slots"]
    assert battle["toolbar_assets"]
    assert battle["sample_delivery_asset"]["stable_internal_id"] == "asset_mirror_lure_trap_001"
    assert battle["animation_pipeline_status"] == (
        "multiframe_atlas_ready_video_keyframes_not_generated"
    )
    assert battle["runtime_art_kit"]["coverage"]["battle_nodes"] == ["gray_lantern_station"]

    runtime = _payload(
        client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/runtime-package")
    )
    assert runtime["runtime_package"]["schema_version"] == "runtime_package.v0.1"
    assert runtime["map_runtime_package"]["node_id"] == "gray_lantern_station"
    assert runtime["sample_delivery_asset"]["media_refs"]["mode"] == "generated"
    assert runtime["runtime_art_media_manifest"]["summary"]["media_count"] == 18

    map_runtime = _payload(
        client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/map-runtime-package")
    )
    map_package = map_runtime["map_runtime_package"]
    assert map_package["schema_version"] == "map_runtime_package.v0.1"
    assert len(map_package["path_routes"]) == 1
    assert len(map_package["build_slots"]) >= 8
    first_visual_url = map_package["visual_layers"][0]["url"]
    assert first_visual_url.startswith("/assets/map_visual_reference/")
    visual_resp = client.get(first_visual_url)
    assert visual_resp.status_code == 200
    assert visual_resp.headers["content-type"] == "image/png"

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
    assert settlement["settlement"]["world_delta"]["delta_id"] == (
        "delta_run_demo_001_gray_lantern_station_2_battle_result_repaired"
    )
    assert settlement["settlement"]["world_delta_transaction"]["transaction_id"] == (
        "tx_first_battle_result_repaired_001"
    )
    assert settlement["settlement"]["core_artifact_refs"]["fact_entry"].endswith(
        "mvp_gray_lantern.fact_entry.json"
    )
    assert settlement["settlement"]["core_artifact_refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    settlement_core = settlement["settlement"]["core_artifacts"]
    assert settlement_core["status"] == "native_settlement_committed"
    assert settlement_core["refs"] == settlement["settlement"]["core_artifact_refs"]
    assert settlement_core["context_package"]["purpose"] == "world_delta"
    assert settlement_core["fact_entry"]["commit_state"] == "committed"
    assert settlement_core["fact_entry"]["source_tx_id"] == (
        "tx_first_battle_result_repaired_001"
    )
    assert settlement_core["compiled_game_object_package"]["runtime_contract"][
        "world_delta_refs"
    ][0]["path"] == settlement["settlement"]["core_artifact_refs"]["world_delta"]
    assert settlement_core["world_delta"]["delta_id"] == settlement["settlement"][
        "world_delta"
    ]["delta_id"]
    assert settlement_core["world_delta_transaction"]["transaction_id"] == settlement[
        "settlement"
    ]["world_delta_transaction"]["transaction_id"]
    assert settlement["settlement"]["run_world_state"]["progress"]["phase"] == (
        "post_first_defense"
    )

    latest = _payload(client.get(f"/api/sessions/{sid}/settlement/latest"))
    assert latest["settlement"]["world_delta"]["source"] == "battle_result"

    evidence = _payload(client.get(f"/api/sessions/{sid}/evidence"))
    assert evidence["audit_summary"]["overall_status"] == "passed"
    assert evidence["battle_result"]["settlement"]["node_id"] == "gray_lantern_station"
    assert evidence["battle_result"]["settlement"]["core_artifacts"]["status"] == (
        "native_settlement_committed"
    )
    assert evidence["ai_compile_core_artifacts"]["context_package"]["schema_version"] == (
        "context_package.v0.1"
    )
    assert evidence["ai_compile_core_artifacts"]["refs"]["compiled_game_object_package"].endswith(
        "mvp_light_snare.compiled_game_object_package.json"
    )
    assert evidence["ai_compile_core_artifacts"]["refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    assert evidence["generation_scheduler"]["refs"]["run_report"].endswith(
        "mvp_generation_schedule_run_report.v0.1.json"
    )
    assert evidence["generation_scheduler"]["buffer"]["provider_call_count"] == 0
    assert evidence["generation_scheduler"]["buffer"]["world_mutation_count"] == 0
    assert evidence["generation_scheduler"]["latest_run"]["run_id"] == (
        schedule_run["generation_schedule_run"]["run_id"]
    )
    assert evidence["generation_scheduler"]["latest_run"]["scheduler_mode"] == (
        "fixture_backed_dry_run"
    )
    assert evidence["generation_scheduler"]["latest_queue"]["summary"]["item_count"] == 8
    assert evidence["generation_scheduler"]["latest_queue"]["summary"]["claimable_count"] == 4


def test_generation_scheduler_retry_budget_and_fallback_flow(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))

    first_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={"worker_id": "budget-worker"},
        )
    )
    item_id = first_step["generation_schedule_queue_item"]["schedule_item_id"]
    assert first_step["generation_schedule_queue_item"]["status"] == "waiting_review"
    assert first_step["generation_schedule_queue_item"]["attempt_count"] == 1
    assert first_step["generation_schedule_queue_item"]["max_attempts"] == 2

    first_fail = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/fail",
            json={"worker_id": "budget-worker", "note": "first attempt rejected"},
        )
    )
    assert first_fail["generation_schedule_queue_item"]["status"] == "failed"

    retry = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/retry",
            json={"worker_id": "budget-worker", "note": "retry within budget"},
        )
    )
    assert retry["generation_schedule_queue_item"]["status"] == "queued"
    assert retry["generation_schedule_queue"]["summary"]["claimable_count"] == 4

    second_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={"worker_id": "budget-worker"},
        )
    )
    assert second_step["generation_schedule_queue_item"]["schedule_item_id"] == item_id
    assert second_step["generation_schedule_queue_item"]["attempt_count"] == 2
    assert second_step["generation_schedule_queue_item"]["attempt_budget_exhausted"] is True

    second_fail = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/fail",
            json={"worker_id": "budget-worker", "note": "second attempt rejected"},
        )
    )
    assert second_fail["generation_schedule_queue_item"]["status"] == "failed"

    retry_conflict = client.post(
        f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/retry",
        json={"worker_id": "budget-worker"},
    )
    assert retry_conflict.status_code == 409
    assert "cannot retry" in retry_conflict.json()["detail"]

    fallback = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/fallback",
            json={"worker_id": "budget-worker", "note": "use reviewed fallback"},
        )
    )
    assert fallback["generation_schedule_queue_item"]["status"] == "fallback_ready"
    assert fallback["generation_schedule_queue_item"]["fallback_ref"]
    assert fallback["generation_schedule_queue"]["summary"]["fallback_ready_count"] == 2


def test_all_battle_nodes_expose_map_runtime_packages(client):
    sid = _create_session(client)
    expected = {
        "gray_lantern_station": "map_pkg_gray_lantern_station_v0_1",
        "lamp_wick_store": "map_pkg_lamp_wick_store_v0_1",
        "old_signal_tower": "map_pkg_old_signal_tower_v0_1",
    }
    for node_id, package_id in expected.items():
        battle = _payload(client.get(f"/api/sessions/{sid}/battles/{node_id}/config"))
        assert battle["battle_config"]["node_id"] == node_id
        assert battle["map_runtime_package"]["package_id"] == package_id
        assert battle["map_runtime_package"]["node_id"] == node_id
        assert battle["map_runtime_package"]["path_routes"]
        assert battle["map_runtime_package"]["build_slots"]

        runtime = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-runtime-package")
        )
        map_package = runtime["map_runtime_package"]
        assert map_package["package_id"] == package_id
        assert map_package["node_id"] == node_id
        roles = {layer["role"] for layer in map_package["visual_layers"]}
        assert "battle_runtime_background" in roles


def test_frontend_mock_endpoints_require_existing_session(client):
    resp = client.get("/api/sessions/missing/frontend-mock-pack")
    assert resp.status_code == 404
    assert "session not found" in resp.json()["detail"].lower()


def test_unknown_node_returns_404(client):
    sid = _create_session(client)
    resp = client.get(f"/api/sessions/{sid}/nodes/unknown/briefing")
    assert resp.status_code == 404
    assert "mock fixture not found" in resp.json()["detail"]
