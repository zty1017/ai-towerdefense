"""Closed-loop tests for guarded live post-battle world evolution."""

from __future__ import annotations

import json
from typing import Any

from app.services import post_battle_world_evolution_service as evolution_service


def _payload(response):
    assert response.status_code < 400, response.text
    return response.json()["payload"]


def _create_world(client) -> str:
    session_id = client.post("/api/sessions").json()["session_id"]
    _payload(client.post(f"/api/sessions/{session_id}/world-instance"))
    return session_id


def _delta(*, operations: list[dict[str, Any]] | None = None, summary: str | None = None):
    return {
        "schema_version": "world_state_delta.v0.1",
        "delta_id": "delta_run_demo_001_gray_lantern_station_3_live_evolution",
        "run_id": "run_demo_001",
        "worldbook_id": "long_night_lanterns",
        "source": "battle_result",
        "created_turn": 3,
        "summary": summary or "余烬尚温，北路的微光引出了新的巡查机会。",
        "operations": operations
        or [
            {
                "op": "append_event",
                "event": {
                    "event_id": "event_live_north_road_afterglow",
                    "turn": 3,
                    "kind": "npc",
                    "summary": "守灯人听见北路传来短促回响，提醒你趁灯火未熄查明源头。",
                },
            },
            {
                "op": "upsert_task",
                "task": {
                    "task_id": "task_live_north_road_afterglow",
                    "kind": "side",
                    "status": "active",
                    "title": "追查北路余光",
                    "summary": "前往北路岔口，确认战后回响是否会引来新的影潮。",
                    "node_id": "northern_road_crossing",
                    "objective_refs": ["northern_road_crossing"],
                    "reward_refs": [],
                },
            },
            {
                "op": "schedule_random_event",
                "random_event": {
                    "random_event_id": "random_live_north_road_echo",
                    "event_type": "threat_warning",
                    "status": "pending",
                    "summary": "北路回响可能在下一轮巡查时聚成新的影群。",
                    "node_id": "northern_road_crossing",
                    "trigger_turn": 4,
                    "related_task_id": "task_live_north_road_afterglow",
                },
            },
            {
                "op": "adjust_resource",
                "resource_id": "lamp_oil",
                "amount_delta": -1,
            },
        ],
    }


def _enable_live(monkeypatch):
    monkeypatch.setenv("AI_TD_LIVE_WORLD_EVOLUTION", "live")
    monkeypatch.setenv("ARK_API_KEY", "test-key-must-never-be-stored")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


def _mock_delta_response(monkeypatch, delta, observed=None):
    def request(messages, *, timeout, max_tokens):
        if observed is not None:
            observed["prompt"] = json.loads(messages[1]["content"])
            observed["timeout"] = timeout
            observed["max_tokens"] = max_tokens
        return {
            "choices": [
                {"message": {"content": json.dumps(delta, ensure_ascii=False)}}
            ]
        }

    monkeypatch.setattr(evolution_service, "_request_provider_response", request)


def _settle(client, session_id: str):
    return _payload(
        client.post(
            f"/api/sessions/{session_id}/battles/gray_lantern_station/results",
            json={
                "result": "victory",
                "protected_core_hp": 7,
                "optional_target_state": "secured",
                "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
                "leaked_enemy_count": 2,
            },
        )
    )


def test_live_success_uses_real_result_and_commits_player_projection(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    observed: dict[str, Any] = {}
    candidate = _delta()
    _mock_delta_response(monkeypatch, candidate, observed)
    session_id = _create_world(client)

    response = _settle(client, session_id)
    settlement = response["settlement"]
    assert settlement["world_delta"]["delta_id"].endswith("_repaired")
    assert settlement["world_evolution_delta"] == candidate
    assert settlement["interlude_summary"] == candidate["summary"]
    assert settlement["npc_feedback"].startswith("守灯人听见北路")
    assert settlement["next_task"]["task_id"] == "task_live_north_road_afterglow"
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"
    assert settlement["run_world_state"]["resources"][0]["amount"] == 10
    assert settlement["run_world_state"]["tasks"][0]["task_id"] == (
        "task_live_north_road_afterglow"
    )

    prompt = observed["prompt"]
    assert prompt["run_world_state"]["progress"]["phase"] == "post_first_defense"
    assert prompt["battle_result"]["enemies_leaked"] == 2
    assert prompt["battle_result"]["protected_core_hp"] == 7
    assert prompt["battle_result"]["deployed_objects"][0]["object_id"] == (
        "asset_mirror_lure_trap_001"
    )
    assert prompt["session_context"]["player_origin"] == "lampwright_apprentice"
    assert prompt["compiler_contract"]["post_battle_live_policy"][
        "deterministic_campaign_progress_is_immutable"
    ] is True

    contributions = response["activated_runtime_bundle"]["feature_snapshots"][
        "settlement"
    ]["contributions"]
    projected = next(item for item in contributions if item["slot"] == "world_delta")
    assert "余烬尚温" in projected["payload"]["summary"]
    assert "追查北路余光" in projected["payload"]["summary"]

    stored = raw_conn.execute(
        "SELECT payload FROM battle_results WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()[0]
    assert "raw_prompt" not in stored
    assert "choices" not in stored
    assert "test-key-must-never-be-stored" not in stored


def test_explicit_off_mode_never_calls_provider(client, monkeypatch):
    monkeypatch.setenv("AI_TD_LIVE_WORLD_EVOLUTION", "off")
    monkeypatch.setenv("ARK_API_KEY", "present-but-live-not-authorized")

    def forbidden(*args, **kwargs):
        raise AssertionError("offline default attempted a provider call")

    monkeypatch.setattr(evolution_service, "_request_provider_response", forbidden)
    settlement = _settle(client, _create_world(client))["settlement"]
    assert "world_evolution_delta" not in settlement
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"


def test_battle_run_id_makes_retry_idempotent(client, raw_conn, monkeypatch):
    _enable_live(monkeypatch)
    calls = {"count": 0}

    def request(messages, *, timeout, max_tokens):
        calls["count"] += 1
        return {"choices": [{"message": {"content": json.dumps(_delta(), ensure_ascii=False)}}]}

    monkeypatch.setattr(evolution_service, "_request_provider_response", request)
    session_id = _create_world(client)
    body = {
        "result": "victory",
        "protected_core_hp": 7,
        "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
        "leaked_enemy_count": 2,
        "battle_run_id": "battle-retry-demo-001",
    }
    first = _payload(
        client.post(
            f"/api/sessions/{session_id}/battles/gray_lantern_station/results",
            json=body,
        )
    )
    second = _payload(
        client.post(
            f"/api/sessions/{session_id}/battles/gray_lantern_station/results",
            json=body,
        )
    )

    assert second["settlement"] == first["settlement"]
    assert calls["count"] == 1
    count = raw_conn.execute(
        "SELECT COUNT(*) FROM battle_results WHERE session_id = ?",
        (session_id,),
    ).fetchone()[0]
    assert count == 1


def test_auto_mode_loads_shared_worktree_dotenv(client, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("AI_TD_LIVE_WORLD_EVOLUTION", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    adapter, *_ = evolution_service._modules()
    observed = {}

    def load_dotenv(path):
        observed["dotenv"] = path
        monkeypatch.setenv("ARK_API_KEY", "loaded-by-test")

    monkeypatch.setattr(adapter, "load_dotenv", load_dotenv)
    _mock_delta_response(monkeypatch, _delta())
    settlement = _settle(client, _create_world(client))["settlement"]

    assert observed["dotenv"].name == ".env"
    assert settlement["world_evolution_delta"]["summary"].startswith("余烬尚温")


def test_committed_live_append_survives_next_deterministic_campaign_baseline(
    client, monkeypatch
):
    _enable_live(monkeypatch)
    _mock_delta_response(monkeypatch, _delta())
    session_id = _create_world(client)
    first = _settle(client, session_id)["settlement"]
    assert first["run_world_state"]["tasks"][0]["task_id"] == (
        "task_live_north_road_afterglow"
    )

    monkeypatch.setenv("AI_TD_LIVE_WORLD_EVOLUTION", "off")
    second = _payload(
        client.post(
            f"/api/sessions/{session_id}/battles/lamp_wick_store/results",
            json={"result": "victory", "protected_core_hp": 8},
        )
    )["settlement"]
    assert second["run_world_state"]["progress"]["phase"] == "post_wick_store_defense"
    assert any(
        task.get("task_id") == "task_live_north_road_afterglow"
        for task in second["run_world_state"]["tasks"]
    )
    assert any(
        event.get("event_id") == "event_live_north_road_afterglow"
        for event in second["run_world_state"]["event_log"]
    )


def test_structurally_invalid_live_delta_silently_uses_deterministic_state(
    client, monkeypatch
):
    _enable_live(monkeypatch)
    invalid = _delta()
    invalid["raw_prompt"] = "must never pass"
    _mock_delta_response(monkeypatch, invalid)

    settlement = _settle(client, _create_world(client))["settlement"]
    assert "world_evolution_delta" not in settlement
    assert "interlude_summary" not in settlement
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"
    assert "tasks" not in settlement["run_world_state"]


def test_policy_rejection_cannot_roll_back_or_pollute_session_state(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    candidate = _delta(
        operations=[{"op": "set_progress_phase", "phase": "first_defense"}],
        summary="驿站的灯火暂时安稳。",
    )
    _mock_delta_response(monkeypatch, candidate)
    session_id = _create_world(client)

    settlement = _settle(client, session_id)["settlement"]
    assert "world_evolution_delta" not in settlement
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"
    stored_state = json.loads(
        raw_conn.execute(
            "SELECT payload FROM campaign_state WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()[0]
    )
    assert stored_state["progress"]["phase"] == "post_first_defense"
    assert stored_state["event_log"][-1]["event_id"] == (
        "gray_lantern_first_defense_repaired_success"
    )


def test_timeout_is_hidden_from_player_and_keeps_deterministic_settlement(
    client, monkeypatch
):
    _enable_live(monkeypatch)

    def timeout(*args, **kwargs):
        raise TimeoutError("private upstream timeout detail")

    monkeypatch.setattr(evolution_service, "_request_provider_response", timeout)
    settlement = _settle(client, _create_world(client))["settlement"]
    rendered = json.dumps(settlement, ensure_ascii=False)
    assert "TimeoutError" not in rendered
    assert "private upstream" not in rendered
    assert "world_evolution_delta" not in settlement
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"


def test_unsafe_live_text_never_reaches_settlement_or_saved_state(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    unsafe = "<img src=x onerror=alert('night')>"
    _mock_delta_response(monkeypatch, _delta(summary=unsafe))
    session_id = _create_world(client)

    settlement = _settle(client, session_id)["settlement"]
    assert unsafe not in json.dumps(settlement, ensure_ascii=False)
    assert "world_evolution_delta" not in settlement
    stored = raw_conn.execute(
        "SELECT payload FROM battle_results WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()[0]
    assert unsafe not in stored


def _mock_delta_sequence(monkeypatch, deltas):
    calls = {"count": 0}

    def request(messages, *, timeout, max_tokens):
        calls["count"] += 1
        index = min(calls["count"], len(deltas)) - 1
        return {
            "choices": [
                {"message": {"content": json.dumps(deltas[index], ensure_ascii=False)}}
            ]
        }

    monkeypatch.setattr(evolution_service, "_request_provider_response", request)
    return calls


def _last_studio_diagnostic(raw_conn, session_id):
    row = raw_conn.execute(
        "SELECT payload FROM studio_logs WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def test_null_related_task_id_repaired_on_second_attempt(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    bad = _delta()
    bad["operations"][2]["random_event"]["related_task_id"] = None
    good = _delta()
    calls = _mock_delta_sequence(monkeypatch, [bad, good])
    session_id = _create_world(client)

    settlement = _settle(client, session_id)["settlement"]

    # Second attempt (repair) succeeds and the valid delta reaches the player.
    assert calls["count"] == 2
    assert settlement["world_evolution_delta"] == good
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"

    diagnostic = _last_studio_diagnostic(raw_conn, session_id)
    assert diagnostic is not None
    assert diagnostic["kind"] == "post_battle_world_evolution"
    assert diagnostic["diagnostic"]["attempt_count"] == 2
    assert diagnostic["diagnostic"]["fallback_stage"] is None
    assert diagnostic["diagnostic"]["error_codes"] == []

    rendered = json.dumps(settlement, ensure_ascii=False)
    rendered_delta = json.dumps(
        settlement["world_evolution_delta"], ensure_ascii=False
    )
    assert "structure_invalid" not in rendered
    assert "provider_error" not in rendered
    assert "raw_prompt" not in rendered
    assert "TimeoutError" not in rendered
    assert '"related_task_id": null' not in rendered_delta


def test_repair_failure_falls_back_deterministically(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    bad = _delta()
    bad["operations"][2]["random_event"]["related_task_id"] = None
    # Both attempts return the same structurally invalid candidate.
    calls = _mock_delta_sequence(monkeypatch, [bad, bad])
    session_id = _create_world(client)

    settlement = _settle(client, session_id)["settlement"]

    assert calls["count"] == 2
    assert "world_evolution_delta" not in settlement
    assert settlement["run_world_state"]["progress"]["phase"] == "post_first_defense"

    diagnostic = _last_studio_diagnostic(raw_conn, session_id)
    assert diagnostic is not None
    assert diagnostic["diagnostic"]["attempt_count"] == 2
    assert diagnostic["diagnostic"]["fallback_stage"] in {
        "structure",
        "semantic",
        "policy",
        "apply",
        "output_state",
    }
    assert diagnostic["diagnostic"]["error_codes"]

    rendered = json.dumps(settlement, ensure_ascii=False)
    assert "structure_invalid" not in rendered
    assert "provider_error" not in rendered
    assert "raw_prompt" not in rendered


def test_diagnostic_contains_only_internal_codes_and_no_raw_content(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    bad = _delta()
    bad["operations"][2]["random_event"]["related_task_id"] = None
    _mock_delta_sequence(monkeypatch, [bad, bad])
    session_id = _create_world(client)
    _settle(client, session_id)

    diagnostic = _last_studio_diagnostic(raw_conn, session_id)
    diag = diagnostic["diagnostic"]
    # Only the compact internal fields, no prompt/response/credential/key.
    assert set(diag.keys()) == {"attempt_count", "fallback_stage", "error_codes"}
    for code in diag["error_codes"]:
        assert code in {
            "structure_invalid",
            "semantic_invalid",
            "policy_violation",
            "apply_failed",
            "output_state_invalid",
        }
    assert "raw_prompt" not in diagnostic
    assert "raw_response" not in diagnostic
    assert "api_key" not in diagnostic
    assert "secret" not in diagnostic


def test_player_settlement_omits_diagnostic_and_technical_terms(
    client, raw_conn, monkeypatch
):
    _enable_live(monkeypatch)
    bad = _delta()
    bad["operations"][2]["random_event"]["related_task_id"] = None
    good = _delta()
    _mock_delta_sequence(monkeypatch, [bad, good])
    session_id = _create_world(client)

    response = _settle(client, session_id)
    settlement = response["settlement"]
    bundle = response["activated_runtime_bundle"]
    rendered = json.dumps(
        {"settlement": settlement, "bundle": bundle}, ensure_ascii=False
    )

    # No internal diagnostic leaks into the player-facing payload.
    assert "fallback_stage" not in rendered
    assert "attempt_count" not in rendered
    assert "error_codes" not in rendered
    assert "structure_invalid" not in rendered
    assert "provider_error" not in rendered
    # No raw provider artifact leaks.
    assert "raw_prompt" not in rendered
    assert "test-key-must-never-be-stored" not in rendered
