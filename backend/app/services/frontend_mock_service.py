"""Fixture-backed frontend mock service.

This service exposes the reviewed MVP content through backend APIs without
calling LLMs, image providers, or reading `.env`. It is the stable demo mode
for frontend development: the UI can exercise the full player flow while all
content comes from existing JSON packages and generated media manifests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..db import db_cursor, now_iso
from . import (
    battle_content_service,
    frontend_media_service,
    generation_scheduler_service,
    map_runtime_service,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]

_WORLD_INSTANCE_CONFIG = (
    _REPO_ROOT / "content/worldbooks/long_night_lanterns/world_instance_config.json"
)
_OPENING = _REPO_ROOT / "content/worldbooks/long_night_lanterns/opening.json"
_INITIAL_RUN_STATE = _REPO_ROOT / "examples/run_world_states/demo_initial.run_world_state.json"
_INITIAL_MAP = _REPO_ROOT / "game_data/demo/initial_map.json"
_FIRST_CRISIS_NODE = _REPO_ROOT / "game_data/demo/first_crisis_node.json"
_FIRST_BATTLE_DELTA = (
    _REPO_ROOT / "examples/world_deltas/repaired_first_battle_semantic_pass.world_delta.json"
)
_FIRST_BATTLE_TRANSACTION = (
    _REPO_ROOT
    / "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json"
)
_FRONTEND_MOCK_PACK = _REPO_ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json"
_AUDIT_REPORT = _REPO_ROOT / "examples/review_packs/mvp_handoff_audit_report.v0.1.json"
_REVIEW_DOSSIER = _REPO_ROOT / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json"
_CONTEXT_PACKAGE_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
)
_FACT_ENTRY_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_gray_lantern.fact_entry.json"
)
_CGOP_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json"
)

class FixtureNotFoundError(LookupError):
    """Raised when a mock fixture cannot satisfy the requested node."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _load_frontend_pack() -> dict[str, Any]:
    return _load_json(_FRONTEND_MOCK_PACK)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _core_artifact_refs() -> dict[str, str]:
    return {
        "context_package": _rel(_CONTEXT_PACKAGE_EXAMPLE),
        "fact_entry": _rel(_FACT_ENTRY_EXAMPLE),
        "compiled_game_object_package": _rel(_CGOP_EXAMPLE),
        "world_delta_transaction": _rel(_FIRST_BATTLE_TRANSACTION),
    }


def _load_ai_compile_core_artifacts() -> dict[str, Any]:
    return {
        "status": "field_boundary_examples_ready",
        "refs": _core_artifact_refs(),
        "context_package": _load_json(_CONTEXT_PACKAGE_EXAMPLE),
        "fact_entry": _load_json(_FACT_ENTRY_EXAMPLE),
        "compiled_game_object_package": _load_json(_CGOP_EXAMPLE),
        "world_delta_transaction": _load_json(_FIRST_BATTLE_TRANSACTION),
    }


def _load_campaign_state(session_id: str) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM campaign_state WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if row and row.get("payload"):
        return json.loads(row["payload"])
    return _load_json(_INITIAL_RUN_STATE)


def _save_campaign_state(session_id: str, payload: dict[str, Any]) -> None:
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO campaign_state (session_id, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, _dump_payload(payload), ts, ts),
        )


def _selected_options(config: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, str]:
    defaults = config.get("recommended_defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    options = {
        "creativity_mode": str(defaults.get("creativity_mode", "stable")),
        "player_origin": str(defaults.get("player_origin", "lampwright_apprentice")),
        "visual_style_id": str(defaults.get("visual_style_id", "lantern_wasteland_pseudo3d")),
    }
    if isinstance(overrides, dict):
        for key in options:
            value = overrides.get(key)
            if isinstance(value, str) and value:
                options[key] = value
    return options


def _asset_for_sample_delivery(pack: dict[str, Any]) -> dict[str, Any] | None:
    """Pick a generated support item that matches the tutorial sample role."""
    assets = pack.get("assets", [])
    if not isinstance(assets, list):
        return None
    preferred_ids = (
        "asset_mirror_lure_trap_001",
        "asset_signal_wick_decoy",
        "asset_signal_echo_marker",
    )
    for asset_id in preferred_ids:
        for asset in assets:
            if isinstance(asset, dict) and asset.get("stable_internal_id") == asset_id:
                return asset
    return None


def _battle_toolbar_assets(pack: dict[str, Any]) -> list[dict[str, Any]]:
    assets = pack.get("assets", [])
    if not isinstance(assets, list):
        return []
    return [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and isinstance(asset.get("frontend_usage"), dict)
        and asset["frontend_usage"].get("battle_toolbar") is True
    ]


def _apply_delta_to_state(state: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Apply the small subset of WorldStateDelta ops needed for the MVP mock."""
    updated = json.loads(json.dumps(state, ensure_ascii=False))
    for op in delta.get("operations", []):
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "set_progress_phase":
            progress = updated.setdefault("progress", {})
            if isinstance(progress, dict):
                progress["phase"] = op.get("phase", progress.get("phase"))
                progress["turn"] = max(int(progress.get("turn", 1)), int(delta.get("created_turn", 2)))
        elif kind == "set_map_node_state":
            node_id = op.get("node_id")
            patch = op.get("patch", {})
            if isinstance(node_id, str) and isinstance(patch, dict):
                for node in updated.get("map_nodes", []):
                    if isinstance(node, dict) and node.get("node_id") == node_id:
                        node.update(patch)
        elif kind == "adjust_resource":
            resource_id = op.get("resource_id")
            amount_delta = op.get("amount_delta", 0)
            for resource in updated.get("resources", []):
                if isinstance(resource, dict) and resource.get("resource_id") == resource_id:
                    resource["amount"] = int(resource.get("amount", 0)) + int(amount_delta)
        elif kind == "adjust_global_state":
            field = op.get("field")
            amount_delta = op.get("amount_delta", 0)
            global_state = updated.setdefault("global_state", {})
            if isinstance(field, str) and isinstance(global_state, dict):
                global_state[field] = round(float(global_state.get(field, 0)) + float(amount_delta), 4)
        elif kind == "update_npc_relationship":
            npc_id = op.get("npc_id")
            rel_delta = op.get("relationship_delta", {})
            if isinstance(npc_id, str) and isinstance(rel_delta, dict):
                for npc in updated.get("npcs", []):
                    if isinstance(npc, dict) and npc.get("npc_id") == npc_id:
                        rel = npc.setdefault("relationship", {})
                        if isinstance(rel, dict):
                            for key, value in rel_delta.items():
                                rel[key] = round(float(rel.get(key, 0)) + float(value), 4)
        elif kind == "unlock_fact":
            fact = op.get("fact")
            if isinstance(fact, dict):
                facts = updated.setdefault("unlocked_facts", [])
                if isinstance(facts, list):
                    facts.append(fact)
        elif kind == "add_temporary_sample":
            sample = op.get("sample")
            research = updated.setdefault("research", {})
            if isinstance(sample, dict) and isinstance(research, dict):
                samples = research.setdefault("temporary_samples", [])
                if isinstance(samples, list):
                    samples.append(sample)
        elif kind == "append_event":
            event = op.get("event")
            if isinstance(event, dict):
                event_log = updated.setdefault("event_log", [])
                if isinstance(event_log, list):
                    event_log.append(event)
        elif kind == "set_flag":
            flag = op.get("flag")
            flags = updated.setdefault("flags", {})
            if isinstance(flag, str) and isinstance(flags, dict):
                flags[flag] = op.get("value")
    return updated


def create_world_instance(session_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _load_json(_WORLD_INSTANCE_CONFIG)
    state = _load_json(_INITIAL_RUN_STATE)
    selected = _selected_options(config, overrides)
    payload = {
        "worldbook_id": config.get("worldbook_template_id"),
        "config": config,
        "selected_options": selected,
        "mode": "frontend_mock_fixture",
    }
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO world_instance (session_id, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, _dump_payload(payload), ts, ts),
        )
    _save_campaign_state(session_id, state)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "world_instance": payload,
        "run_world_state": state,
    }


def get_frontend_mock_pack(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "pack": _load_frontend_pack(),
        "ai_compile_core_artifacts": _load_ai_compile_core_artifacts(),
        **frontend_media_service.frontend_media_payload(),
        **frontend_media_service.runtime_art_payload(),
    }


def get_runtime_art_kit(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        **frontend_media_service.runtime_art_payload(),
    }


def get_opening(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "opening": _load_json(_OPENING),
    }


def get_animation_seeds(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "animation_seed_manifest": frontend_media_service.load_animation_seed_manifest(),
        "animation_pipeline_status": "seed_images_ready_video_frames_not_generated",
    }


def get_map(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "map": _load_json(_INITIAL_MAP),
        "run_world_state": _load_campaign_state(session_id),
    }


def get_node_briefing(session_id: str, node_id: str) -> dict[str, Any]:
    if node_id != "gray_lantern_station":
        raise FixtureNotFoundError(node_id)
    pack = _load_frontend_pack()
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "briefing": _load_json(_FIRST_CRISIS_NODE),
        "materials": pack.get("materials", []),
        "npcs": pack.get("npcs", []),
        "suggested_input": "我想做一个能拖慢影潮的临时装置。",
    }


def get_battle_config(session_id: str, node_id: str) -> dict[str, Any]:
    try:
        config = battle_content_service.load_battle_config(node_id)
    except battle_content_service.BattleContentNotFoundError as exc:
        raise FixtureNotFoundError(node_id) from exc
    pack = _load_frontend_pack()
    map_runtime_package = map_runtime_service.load_map_runtime_package_optional(node_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "battle_config": config,
        "map_runtime_package": map_runtime_package,
        "toolbar_assets": _battle_toolbar_assets(pack),
        "sample_delivery_asset": _asset_for_sample_delivery(pack),
        **frontend_media_service.frontend_media_payload(),
        **frontend_media_service.runtime_art_payload(),
    }


def get_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    try:
        runtime_package = battle_content_service.load_runtime_package(node_id)
    except battle_content_service.BattleContentNotFoundError as exc:
        raise FixtureNotFoundError(node_id) from exc
    pack = _load_frontend_pack()
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "runtime_package": runtime_package,
        "map_runtime_package": map_runtime_service.load_map_runtime_package_optional(node_id),
        "sample_delivery_asset": _asset_for_sample_delivery(pack),
        **frontend_media_service.frontend_media_payload(),
        **frontend_media_service.runtime_art_payload(),
    }


def record_battle_result(
    session_id: str,
    node_id: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if node_id != "gray_lantern_station":
        raise FixtureNotFoundError(node_id)
    battle_config = battle_content_service.load_battle_config(node_id)
    delta = _load_json(_FIRST_BATTLE_DELTA)
    transaction = _load_json(_FIRST_BATTLE_TRANSACTION)
    previous_state = _load_campaign_state(session_id)
    next_state = _apply_delta_to_state(previous_state, delta)
    submitted = result if isinstance(result, dict) else {}
    settlement = {
        "node_id": node_id,
        "result": submitted.get("result", "victory"),
        "battle_summary": battle_config.get("post_battle", {}).get(
            "on_victory", "节点守住，样品表现已记录。"
        ),
        "sample_performance": "样品对高速敌潮有效，但稳定性偏低，适合进入后续正式研发。",
        "npc_feedback": "在场技师记录了样品迟滞效果，并建议保留战斗数据。",
        "world_delta": delta,
        "world_delta_transaction": transaction,
        "core_artifact_refs": {
            **_core_artifact_refs(),
            "world_delta": _rel(_FIRST_BATTLE_DELTA),
        },
        "run_world_state": next_state,
    }
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO battle_results (session_id, payload, created_at) VALUES (?, ?, ?)",
            (
                session_id,
                _dump_payload(
                    {
                        "node_id": node_id,
                        "submitted_result": submitted,
                        "settlement": settlement,
                    }
                ),
                ts,
            ),
        )
    _save_campaign_state(session_id, next_state)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "settlement": settlement,
    }


def get_latest_settlement(session_id: str) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload, created_at FROM battle_results WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {
            "session_id": session_id,
            "mode": "frontend_mock_fixture",
            "settlement": None,
            "run_world_state": _load_campaign_state(session_id),
        }
    payload = json.loads(row["payload"])
    settlement = payload.get("settlement")
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "created_at": row["created_at"],
        "settlement": settlement,
    }


def get_evidence(session_id: str) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT proposal_id, node_id, display_name, summary, risk_note, status "
            "FROM research_proposals WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        )
        proposal = cur.fetchone()
        cur.execute(
            "SELECT job_id, proposal_id, status, runtime_package_path, delivery_payload_path, "
            "trace_paths, completed_at FROM research_jobs WHERE session_id = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        )
        job = cur.fetchone()
        cur.execute(
            "SELECT payload, created_at FROM battle_results WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        battle = cur.fetchone()
    audit = _load_json(_AUDIT_REPORT)
    dossier = _load_json(_REVIEW_DOSSIER)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "studio_surface": "simple_evidence",
        "ai_compile_core_artifacts": {
            "status": "field_boundary_examples_ready",
            "refs": _core_artifact_refs(),
        },
        "generation_scheduler": (
            generation_scheduler_service.get_generation_scheduler_evidence(session_id)
        ),
        "proposal": dict(proposal) if proposal else None,
        "research_job": dict(job) if job else None,
        "battle_result": json.loads(battle["payload"]) if battle else None,
        "audit_summary": {
            "overall_status": audit.get("overall_status"),
            "command_count": len(audit.get("command_results", [])),
            "coverage_count": len(audit.get("coverage_checks", [])),
            "review_entrypoints": audit.get("review_entrypoints", []),
        },
        "dossier_summary": {
            "report_id": dossier.get("report_id"),
            "status": dossier.get("status") or dossier.get("overall_status"),
            "known_risks": dossier.get("known_risks", []),
        },
    }
