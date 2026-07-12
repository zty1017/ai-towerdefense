"""Tests for the ResearchJob API: proposal -> confirm -> job lifecycle.

Covers session scoping, AssetGraph workflow execution, artifact presence, and
the player-facing text safety boundary (no technical vocabulary leaks).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

# Terms that must never appear in player-facing text. Union of the task spec
# forbidden list and the worldbook forbidden_terms_in_player_text.
_FORBIDDEN_PLAYER_TERMS = (
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


def _create_session(client) -> str:
    resp = client.post("/api/sessions")
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def _create_proposal(client, session_id: str, intent: str = "我想让敌人在入口处被短暂拖慢") -> dict:
    resp = client.post(
        f"/api/sessions/{session_id}/research/proposals",
        json={"intent_text": intent, "node_id": "gray_lantern_station"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assert_no_forbidden_terms(*texts: str) -> None:
    for text in texts:
        for term in _FORBIDDEN_PLAYER_TERMS:
            assert term not in text, (
                f"forbidden term {term!r} found in player-facing text: {text!r}"
            )


def _assert_native_core_artifacts(metadata: dict) -> dict:
    artifacts = metadata["core_artifacts"]
    for key, value in artifacts["refs"].items():
        assert metadata["core_artifact_refs"][key] == value
    context = artifacts["context_package"]
    fact = artifacts["fact_entry"]
    cgop = artifacts["compiled_game_object_package"]
    assert context["schema_version"] == "context_package.v0.1"
    assert fact["schema_version"] == "fact_entry.v0.1"
    assert cgop["schema_version"] == "compiled_game_object_package.v0.1"
    assert context["context_package_id"] == cgop["context_package_id"]
    assert fact["fact_id"] in cgop["world_context"]["required_fact_ids"]
    assert context["authority"]["advisory_only"] is True
    assert fact["submission_policy"]["commit_requires_world_state_delta"] is True
    assert cgop["runtime_contract"]["runtime_loadable"] is False
    return artifacts


# ---------------------------------------------------------------------------
# Session existence
# ---------------------------------------------------------------------------


def test_create_proposal_missing_session_returns_404(client):
    resp = client.post(
        "/api/sessions/nope/research/proposals",
        json={"intent_text": "x", "node_id": "gray_lantern_station"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_confirm_missing_session_returns_404(client):
    resp = client.post(
        "/api/sessions/nope/research/proposals/somepid/confirm"
    )
    assert resp.status_code == 404


def test_get_job_missing_session_returns_404(client):
    resp = client.get("/api/sessions/nope/research/jobs/somejid")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Proposal creation
# ---------------------------------------------------------------------------


def test_create_proposal_happy_path(client):
    sid = _create_session(client)
    body = _create_proposal(client, sid, intent="我想让敌人在入口处被短暂拖慢")
    assert body["session_id"] == sid
    assert body["node_id"] == "gray_lantern_station"
    assert body["proposal_id"]
    assert body["display_name"]
    assert body["summary"]
    assert body["risk_note"]
    assert body["player_state_message"]
    metadata = body["compiler_metadata"]
    assert metadata["schema_version"] == "compiler_metadata.v0.1"
    assert metadata["compiled_object"]["object_model"] == "CGOP"
    assert metadata["context_package"]["node_id"] == "gray_lantern_station"
    assert metadata["context_package"]["map_runtime_package_ref"].endswith(
        "mvp_first_battle.map_runtime_package.json"
    )
    assert metadata["core_artifact_refs"]["context_package"].endswith(
        "mvp_first_battle.context_package.json"
    )
    assert metadata["core_artifact_refs"]["compiled_game_object_package"].endswith(
        "mvp_light_snare.compiled_game_object_package.json"
    )
    assert metadata["core_artifact_refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    artifacts = _assert_native_core_artifacts(metadata)
    assert artifacts["status"] == "native_snapshots_ready"
    assert artifacts["compiled_game_object_package"]["lifecycle_state"] == "compiled"
    # Player-facing text must stay in world language.
    _assert_no_forbidden_terms(
        body["display_name"],
        body["summary"],
        body["risk_note"],
        body["player_state_message"],
    )


def test_create_proposal_is_persisted(client, raw_conn: sqlite3.Connection):
    sid = _create_session(client)
    body = _create_proposal(client, sid)
    rows = raw_conn.execute(
        "SELECT proposal_id, session_id, status FROM research_proposals "
        "WHERE session_id = ?",
        (sid,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["proposal_id"] == body["proposal_id"]
    assert rows[0]["status"] == "proposed"


def test_live_candidate_is_lowered_promoted_and_activated(client, monkeypatch):
    from app.services import live_asset_compile_service
    from tools.dev.validate_provider_artifact_promotion_report import (
        validate_provider_artifact_promotion_report,
    )
    from tools.dev.validate_provider_artifact_staging_manifest import (
        validate_provider_artifact_staging_manifest,
    )
    from tools.dev.validate_provider_output_envelope import validate_provider_output_envelope

    candidate = {
        "id": "asset_live_prism_tower",
        "lifecycle": "session_blueprint",
        "gameplay": {
            "asset_type": "tower_blueprint",
            "base_stats": {"build_cost": 17, "range": 3.4, "cooldown_ms": 1200},
            "effect_blocks": [
                {"type": "damage", "amount": 13, "damage_type": "light"},
                {"type": "slow", "duration_ms": 1400, "slow_ratio": 0.24},
            ],
            "constraints": {"max_instances": 2},
            "type_specific": {"tower_slot": "standard"},
        },
        "presentation": {
            "name": "棱潮束灯塔",
            "short_description": "折射灯束打击来敌，并留下短暂迟滞。",
            "icon_prompt": "clean tower icon",
            "animation_card_prompt": "tower animation card",
            "visual_tags": ["棱镜", "束光", "迟滞"],
        },
        "provenance": {
            "proposal_id": "rebound",
            "mode": "runtime_safe",
            "worldbook_id": "long_night_lanterns",
            "provider": "ark_deepseek_v4_flash",
            "model": "deepseek-v4-flash",
            "npc_ids": [],
            "material_ids": [],
            "validation_status": "pending",
            "simulation_report_id": None,
        },
    }
    monkeypatch.setattr(
        live_asset_compile_service,
        "compile_candidate",
        lambda **_: {
            "status": "live_validated",
            "candidate": candidate,
            "provenance": {
                "mode": "live",
                "profile": "ark_deepseek_v4_flash",
                "model": "deepseek-v4-flash",
                "provider_call_performed": True,
                "raw_prompt_stored": False,
                "raw_response_stored": False,
            },
        },
    )

    sid = _create_session(client)
    proposal = _create_proposal(client, sid, intent="做一座折射灯塔攻击并拖慢影潮")
    assert proposal["display_name"] == "棱潮束灯塔"
    assert proposal["compiled_candidate"] == candidate
    assert proposal["compiler_metadata"]["generation"]["mode"] == "live"
    job = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    ).json()
    assert job["status"] == "completed"
    report_path = Path(job["compiler_metadata"]["runtime_refs"]["promotion_report_path"])
    assert report_path.exists()
    evidence_root = report_path.parent
    envelope = json.loads((evidence_root / "provider_output_envelope.json").read_text())
    staging = json.loads(
        (evidence_root / "provider_artifact_staging_manifest.json").read_text()
    )
    promotion = json.loads(report_path.read_text())
    assert validate_provider_output_envelope(envelope) == []
    assert validate_provider_artifact_staging_manifest(staging) == []
    assert validate_provider_artifact_promotion_report(promotion) == []
    assert promotion["gate_results"]["human_review"] == {
        "status": "not_applicable",
        "required_before_promotion": False,
        "report_ref": None,
    }
    simulation_ref = Path(promotion["gate_results"]["simulation_gate"]["report_ref"])
    assert simulation_ref.name == "live_candidate_simulation_report.v0.1.json"
    assert simulation_ref.exists()
    simulation = json.loads(simulation_ref.read_text(encoding="utf-8"))
    assert simulation["candidate_id"] == candidate["id"]
    assert promotion["gate_results"]["simulation_gate"]["status"] == "passed"
    assert simulation_ref != evidence_root / "validated_live_asset_candidate.json"
    assert str(simulation_ref) not in job["trace_paths"]
    package = json.loads(Path(job["runtime_package_path"]).read_text(encoding="utf-8"))
    assert package["assets"][0]["display"]["name"] == "棱潮束灯塔"
    assert package["assets"][0]["gameplay_ref"]["path"].endswith(
        "validated_live_asset_candidate.json"
    )

    activated = client.post(
        f"/api/sessions/{sid}/research/jobs/{job['job_id']}/activate"
    )
    assert activated.status_code == 200, activated.text
    receipt = activated.json()["activation_receipt"]
    assert receipt["status"] == "activated"
    assert receipt["promotion"]["mode"] == "provider_promotion_report"
    assert receipt["validation"]["behavior_abi"]["status"] == "passed", receipt["warnings"]
    capability = next(
        item
        for item in activated.json()["activated_runtime_bundle"]["capabilities"]["battle_objects"]
        if item["object_id"] in receipt["runtime_effect"]["activated_object_ids"]
    )
    assert capability["display_name"] == "棱潮束灯塔"
    assert capability["behavior_abi"]["targeting"]["range_cells"] == 3.4


def test_live_candidate_without_playable_impact_is_not_promoted(client, monkeypatch):
    from app.services import live_asset_compile_service

    candidate = {
        "id": "asset_live_empty_support",
        "lifecycle": "ephemeral",
        "gameplay": {
            "asset_type": "support_item",
            "base_stats": {"activation_cost": 12, "cooldown": 8, "use_count": 1},
            "effect_blocks": [{"type": "power_cost", "power_per_second": 2}],
            "constraints": {"max_instances": 1},
            "type_specific": {},
        },
        "presentation": {
            "name": "空响灯芯",
            "short_description": "尚未形成有效作用的试作品。",
            "icon_prompt": "clean item icon",
            "animation_card_prompt": "item animation card",
            "visual_tags": ["灯芯"],
        },
        "provenance": {
            "proposal_id": "rebound",
            "mode": "runtime_safe",
            "worldbook_id": "long_night_lanterns",
            "provider": "ark_deepseek_v4_flash",
            "model": "deepseek-v4-flash",
            "npc_ids": [],
            "material_ids": [],
            "validation_status": "pending",
            "simulation_report_id": None,
        },
    }
    monkeypatch.setattr(
        live_asset_compile_service,
        "compile_candidate",
        lambda **_: {
            "status": "live_validated",
            "candidate": candidate,
            "provenance": {
                "mode": "live",
                "profile": "ark_deepseek_v4_flash",
                "model": "deepseek-v4-flash",
                "provider_call_performed": True,
                "raw_prompt_stored": False,
                "raw_response_stored": False,
            },
        },
    )

    sid = _create_session(client)
    proposal = _create_proposal(client, sid, intent="做一个应急支援灯芯")
    job_response = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    )
    assert job_response.status_code == 200, job_response.text
    job = job_response.json()
    assert job["status"] == "failed"
    report_path = Path(job["compiler_metadata"]["runtime_refs"]["promotion_report_path"])
    promotion = json.loads(report_path.read_text(encoding="utf-8"))
    simulation_ref = Path(promotion["gate_results"]["simulation_gate"]["report_ref"])
    simulation = json.loads(simulation_ref.read_text(encoding="utf-8"))
    assert simulation["candidate_id"] == candidate["id"]
    assert "no_direct_impact" in simulation["balance_flags"]
    assert promotion["decision"]["promotion_allowed"] is False
    assert promotion["decision"]["promotion_decision"] == "blocked_validation_failed"
    assert promotion["gate_results"]["simulation_gate"]["status"] == "failed"
    assert simulation_ref.name == "live_candidate_simulation_report.v0.1.json"
    assert all("mock_compile" not in str(path) for path in [simulation_ref])

    activation = client.post(
        f"/api/sessions/{sid}/research/jobs/{job['job_id']}/activate"
    )
    assert activation.status_code == 200, activation.text
    receipt = activation.json()["activation_receipt"]
    assert receipt["status"] == "blocked"
    assert receipt["runtime_effect"]["applied"] is False


# ---------------------------------------------------------------------------
# Confirm -> completed job
# ---------------------------------------------------------------------------


def test_confirm_proposal_runs_workflows_and_produces_artifacts(client):
    sid = _create_session(client)
    proposal = _create_proposal(client, sid)
    resp = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["session_id"] == sid
    assert job["proposal_id"] == proposal["proposal_id"]
    assert job["status"] == "completed"
    assert job["job_id"]

    # Two trace files (one per workflow).
    assert len(job["trace_paths"]) == 2
    for trace_path in job["trace_paths"]:
        assert Path(trace_path).exists(), f"trace missing: {trace_path}"

    # Runtime package and delivery payload artifacts must exist on disk.
    assert job["runtime_package_path"]
    assert job["delivery_payload_path"]
    assert Path(job["runtime_package_path"]).exists()
    assert Path(job["delivery_payload_path"]).exists()
    metadata = job["compiler_metadata"]
    assert metadata["schema_version"] == "compiler_metadata.v0.1"
    assert metadata["stage"] == "compiled_sample"
    assert metadata["job_status"] == "completed"
    assert metadata["validation"]["gate_status"] == "passed"
    assert metadata["runtime_refs"]["trace_count"] == 2
    assert metadata["runtime_refs"]["runtime_package_path"] == job["runtime_package_path"]
    assert metadata["core_artifact_refs"]["runtime_package_path"] == job["runtime_package_path"]
    assert metadata["core_artifact_refs"]["delivery_payload_path"] == job["delivery_payload_path"]
    artifacts = metadata["core_artifacts"]
    assert artifacts["status"] == "native_snapshots_compiled"
    cgop = _assert_native_core_artifacts(metadata)["compiled_game_object_package"]
    assert cgop["lifecycle_state"] == "reviewed"
    assert cgop["validation_report"]["gate_status"] == "passed"
    assert cgop["runtime_contract"]["manifest_refs"][0]["path"] == job["runtime_package_path"]
    assert artifacts["delivery_payload_ref"] == job["delivery_payload_path"]

    # Player-facing message stays in world language.
    _assert_no_forbidden_terms(job["player_state_message"])


@pytest.mark.parametrize(
    ("intent", "asset_kind", "display_name", "placement_mode", "uses"),
    [
        ("做一座能攻击影潮的灯塔", "tower_blueprint", "聚光刺塔", "build_slot", 3),
        ("在路口布置绊索陷阱", "temporary_trap_sample", "折光绊索", "path_adjacent_or_slot", 2),
        ("释放一次守灯支援脉冲", "support_item", "守灯脉冲", "free_point", 1),
    ],
)
def test_player_intent_compiles_to_distinct_playable_runtime_objects(
    client, intent, asset_kind, display_name, placement_mode, uses
):
    sid = _create_session(client)
    proposal = _create_proposal(client, sid, intent=intent)
    job = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    ).json()
    assert job["status"] == "completed"

    package = json.loads(Path(job["runtime_package_path"]).read_text(encoding="utf-8"))
    asset = package["assets"][0]
    assert package["session_id"] == sid
    assert asset["asset_kind"] == asset_kind
    assert asset["display"]["name"] == display_name
    assert asset["battle_availability"]["uses_per_battle"] == uses

    activation = client.post(
        f"/api/sessions/{sid}/research/jobs/{job['job_id']}/activate"
    )
    assert activation.status_code == 200, activation.text
    body = activation.json()
    receipt = body["activation_receipt"]
    assert receipt["status"] == "activated"
    object_id = receipt["runtime_effect"]["activated_object_ids"][0]
    capability = next(
        item
        for item in body["activated_runtime_bundle"]["capabilities"]["battle_objects"]
        if item["object_id"] == object_id
    )
    assert capability["asset_kind"] == asset_kind
    assert capability["display_name"] == display_name
    assert capability["tool_id"] == "sample"
    assert capability["lifecycle"]["max_uses"] == uses
    assert capability["behavior_abi"]["placement"]["mode"] == placement_mode


def test_confirm_proposal_marks_proposal_confirmed(client, raw_conn):
    sid = _create_session(client)
    proposal = _create_proposal(client, sid)
    client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    )
    row = raw_conn.execute(
        "SELECT status FROM research_proposals WHERE proposal_id = ?",
        (proposal["proposal_id"],),
    ).fetchone()
    assert row["status"] == "confirmed"


def test_confirm_unknown_proposal_returns_404(client):
    sid = _create_session(client)
    resp = client.post(
        f"/api/sessions/{sid}/research/proposals/nope/confirm"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET job
# ---------------------------------------------------------------------------


def test_get_job_happy_path(client):
    sid = _create_session(client)
    proposal = _create_proposal(client, sid)
    confirm = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    ).json()
    got = client.get(f"/api/sessions/{sid}/research/jobs/{confirm['job_id']}")
    assert got.status_code == 200, got.text
    info = got.json()
    assert info["job_id"] == confirm["job_id"]
    assert info["status"] == "completed"
    assert info["created_at"]
    assert info["updated_at"]
    assert info["completed_at"] is not None
    assert info["compiler_metadata"]["stage"] == "compiled_sample"


def test_get_missing_job_returns_404(client):
    sid = _create_session(client)
    resp = client.get(f"/api/sessions/{sid}/research/jobs/nope")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


def test_job_is_session_isolated(client):
    """A job created in session A must not be readable from session B."""
    a = _create_session(client)
    b = _create_session(client)
    proposal = _create_proposal(client, a)
    confirm = client.post(
        f"/api/sessions/{a}/research/proposals/{proposal['proposal_id']}/confirm"
    ).json()
    # B cannot read A's job.
    resp = client.get(f"/api/sessions/{b}/research/jobs/{confirm['job_id']}")
    assert resp.status_code == 404
    # B cannot confirm A's proposal either.
    resp2 = client.post(
        f"/api/sessions/{b}/research/proposals/{proposal['proposal_id']}/confirm"
    )
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Reset clears research data
# ---------------------------------------------------------------------------


def test_reset_clears_research_data(client, raw_conn: sqlite3.Connection):
    sid = _create_session(client)
    proposal = _create_proposal(client, sid)
    confirm = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    ).json()

    def count(table):
        return raw_conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (sid,)
        ).fetchone()[0]

    assert count("research_proposals") == 1
    assert count("research_jobs") == 1

    reset = client.post(f"/api/sessions/{sid}/reset")
    assert reset.status_code == 200

    assert count("research_proposals") == 0
    assert count("research_jobs") == 0
    # And the job is no longer readable via the API.
    assert client.get(
        f"/api/sessions/{sid}/research/jobs/{confirm['job_id']}"
    ).status_code == 404


# ---------------------------------------------------------------------------
# Player-facing text safety
# ---------------------------------------------------------------------------


def test_player_facing_text_has_no_technical_terms(client):
    """Every player-visible string across the lifecycle avoids tech vocabulary."""
    sid = _create_session(client)
    proposal = _create_proposal(client, sid, intent="在入口布置一个临时陷阱绊住影潮")
    _assert_no_forbidden_terms(
        proposal["display_name"],
        proposal["summary"],
        proposal["risk_note"],
        proposal["player_state_message"],
    )
    confirm = client.post(
        f"/api/sessions/{sid}/research/proposals/{proposal['proposal_id']}/confirm"
    ).json()
    _assert_no_forbidden_terms(confirm["player_state_message"])
    # The serialized confirm response's player-facing fields stay clean.
    info = client.get(
        f"/api/sessions/{sid}/research/jobs/{confirm['job_id']}"
    ).json()
    _assert_no_forbidden_terms(info["player_state_message"])


def test_new_tables_carry_session_id(raw_conn: sqlite3.Connection):
    """research_proposals and research_jobs must be session-scoped."""
    for table in ("research_proposals", "research_jobs"):
        cols = {
            r[1] for r in raw_conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        assert "session_id" in cols, f"table {table} missing session_id column"
