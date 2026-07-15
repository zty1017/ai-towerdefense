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
    ai_core_artifact_service,
    battle_content_service,
    frontend_feature_projection_service,
    frontend_media_service,
    generation_scheduler_service,
    map_render_plan_service,
    map_runtime_service,
    post_battle_world_evolution_service,
    world_catalog_service,
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
_STAGE04_DELTA = (
    _REPO_ROOT / "examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json"
)
_STAGE04_TRANSACTION = (
    _REPO_ROOT
    / "examples/world_delta_transactions/stage_04_wick_store_pressure_battle.world_delta_transaction.json"
)
_STAGE04_AFTER_STATE = (
    _REPO_ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
)
_STAGE06_TRANSACTION = (
    _REPO_ROOT
    / "examples/world_delta_transactions/stage_06_signal_resonance_trial.world_delta_transaction.json"
)
_STAGE06_AFTER_STATE = (
    _REPO_ROOT / "examples/run_world_states/demo_after_stage_06_signal_resonance.run_world_state.json"
)
_FRONTEND_MOCK_PACK = _REPO_ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json"
_AUDIT_REPORT = _REPO_ROOT / "examples/review_packs/mvp_handoff_audit_report.v0.1.json"
_REVIEW_DOSSIER = _REPO_ROOT / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json"

_NODE_BRIEFING_OVERRIDES = {
    "gray_lantern_station": {
        "source_path": _FIRST_CRISIS_NODE,
        "suggested_input": "我想做一个能拖慢影潮的临时装置。",
    },
    "lamp_wick_store": {
        "suggested_input": "我想把灯灰和导线做成能逼退密集影潮的临时灯具。",
    },
    "old_signal_tower": {
        "suggested_input": "我想让信号塔的回光形成短暂屏障，争取修复时间。",
    },
}

_NODE_SETTLEMENT_SPECS = {
    "gray_lantern_station": {
        "mode": "transaction",
        "world_delta_path": _FIRST_BATTLE_DELTA,
        "transaction_path": None,
        "after_state_path": None,
        "sample_performance": "样品对高速敌潮有效，但稳定性偏低，适合进入后续正式研发。",
        "npc_feedback": "在场技师记录了样品迟滞效果，并建议保留战斗数据。",
    },
    "lamp_wick_store": {
        "mode": "transaction",
        "world_delta_path": _STAGE04_DELTA,
        "transaction_path": _STAGE04_TRANSACTION,
        "after_state_path": _STAGE04_AFTER_STATE,
        "sample_performance": "灯灰爆鸣结构能清出短促空隙，但材料消耗和误触风险仍需登记。",
        "npc_feedback": "修线匠确认补给线恢复，建议把辉晶样品转入正式蓝图整理。",
    },
    "old_signal_tower": {
        "mode": "fixture_bridge",
        "world_delta_path": None,
        "transaction_path": _STAGE06_TRANSACTION,
        "after_state_path": _STAGE06_AFTER_STATE,
        "sample_performance": "回光试验短暂稳定了信号塔，后续仍需把分潮方向转入下一节点准备。",
        "npc_feedback": "侦察员记录到回流方向，提醒中枢不要把这次稳定误判为长期安全。",
    },
}

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


def _load_committed_world_evolution_deltas(session_id: str) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM battle_results WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = cur.fetchall()
    deltas: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload"]) if row.get("payload") else {}
        settlement = payload.get("settlement") if isinstance(payload, dict) else None
        delta = (
            settlement.get("world_evolution_delta")
            if isinstance(settlement, dict)
            else None
        )
        if isinstance(delta, dict):
            deltas.append(delta)
    return deltas


def _load_battle_result_by_run_id(
    session_id: str, battle_run_id: str | None
) -> dict[str, Any] | None:
    if not battle_run_id:
        return None
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM battle_results "
            "WHERE session_id = ? AND idempotency_key = ? LIMIT 1",
            (session_id, battle_run_id),
        )
        row = cur.fetchone()
    if not row or not row.get("payload"):
        return None
    payload = json.loads(row["payload"])
    return payload if isinstance(payload, dict) else None


def _save_campaign_state(session_id: str, payload: dict[str, Any]) -> None:
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO campaign_state (session_id, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, _dump_payload(payload), ts, ts),
        )


def _battle_evolution_session_context(
    session_id: str, state: dict[str, Any], node_id: str
) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM world_instance WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    instance = json.loads(row["payload"]) if row and row.get("payload") else {}
    selected = instance.get("selected_options") if isinstance(instance, dict) else {}
    if not isinstance(selected, dict):
        selected = {}
    prior_events = [
        str(event.get("summary"))[:240]
        for event in state.get("event_log", [])[-8:]
        if isinstance(event, dict) and event.get("summary")
    ]
    return {
        "player_origin": selected.get("player_origin"),
        "node_id": node_id,
        "prior_events": prior_events,
    }


def _live_battle_result(
    submitted: dict[str, Any],
    *,
    node_id: str,
    battle_config: dict[str, Any],
    deployed_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    result = str(submitted.get("result") or "victory")
    leaked = submitted.get("leaked_enemy_count", 0)
    if not isinstance(leaked, int) or isinstance(leaked, bool):
        leaked = 0
    core_hp = submitted.get("protected_core_hp")
    core_target = battle_config.get("core_target")
    core_durability = (
        core_target.get("durability") if isinstance(core_target, dict) else None
    )
    primary = _primary_deployed_asset(deployed_assets)
    return {
        "winner": "player" if result == "victory" else "enemy",
        "result": result,
        "core_damaged": (
            isinstance(core_hp, int)
            and not isinstance(core_hp, bool)
            and isinstance(core_durability, int)
            and core_hp < core_durability
        ),
        "protected_core_hp": core_hp,
        "optional_target_state": submitted.get("optional_target_state"),
        "enemies_leaked": leaked,
        "waves_survived": len(
            [wave for wave in battle_config.get("waves", []) if isinstance(wave, dict)]
        ),
        "sample_triggered": any(
            asset.get("role") in {"sample", "compiled"} for asset in deployed_assets
        ),
        "node_id": node_id,
        "sample_performance": primary.get("effect_summary") if primary else None,
    }


def _save_battle_settlement_and_state(
    session_id: str,
    *,
    node_id: str,
    submitted: dict[str, Any],
    settlement: dict[str, Any],
    state: dict[str, Any],
    created_at: str,
) -> bool:
    """Commit the player settlement and its final gated state atomically."""
    with db_cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO battle_results "
            "(session_id, idempotency_key, payload, created_at) VALUES (?, ?, ?, ?)",
            (
                session_id,
                submitted.get("battle_run_id"),
                _dump_payload(
                    {
                        "node_id": node_id,
                        "submitted_result": submitted,
                        "settlement": settlement,
                    }
                ),
                created_at,
            ),
        )
        if cur.rowcount != 1:
            return False
        cur.execute(
            "INSERT INTO campaign_state (session_id, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, _dump_payload(state), created_at, created_at),
        )
    return True


def _record_world_evolution_diagnostic(
    session_id: str, diagnostic: dict[str, Any] | None
) -> None:
    """Persist the internal-only evolution diagnostic to studio_logs.

    The diagnostic carries no player-facing content and never the raw prompt,
    provider response, or credentials. It is written best-effort so a logging
    failure can never break the player settlement.
    """
    if not isinstance(diagnostic, dict):
        return
    try:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO studio_logs (session_id, payload, created_at) "
                "VALUES (?, ?, ?)",
                (
                    session_id,
                    _dump_payload(
                        {
                            "kind": "post_battle_world_evolution",
                            "diagnostic": {
                                "attempt_count": diagnostic.get("attempt_count"),
                                "fallback_stage": diagnostic.get("fallback_stage"),
                                "error_codes": diagnostic.get("error_codes"),
                            },
                        }
                    ),
                    now_iso(),
                ),
            )
    except Exception:
        # Diagnostics are auxiliary; never fail the settlement over them.
        pass


def _player_runtime_bundle(
    session_id: str,
    *,
    node_id: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return frontend_feature_projection_service.build_player_runtime_bundle(
        session_id,
        run_world_state=state or _load_campaign_state(session_id),
        node_id=node_id,
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


def _effect_summary(display_name: str, behavior_abi: dict[str, Any]) -> str:
    effects = behavior_abi.get("effect_blocks", [])
    if not isinstance(effects, list):
        effects = []
    damage = next(
        (item for item in effects if isinstance(item, dict) and item.get("kind") == "damage"),
        None,
    )
    slow = any(isinstance(item, dict) and item.get("kind") == "slow" for item in effects)
    aura = any(isinstance(item, dict) and item.get("kind") == "aura" for item in effects)
    reveal = any(isinstance(item, dict) and item.get("kind") == "reveal" for item in effects)
    clauses: list[str] = []
    if damage:
        radius = float(damage.get("radius_cells") or 0)
        clauses.append(f"形成约 {radius:g} 格范围打击" if radius > 0 else "完成单体打击")
    if slow:
        clauses.append("附带迟滞")
    if aura:
        clauses.append("形成短时光环")
    if reveal:
        clauses.append("揭示来敌")
    if not clauses:
        return f"{display_name}已在本场实际部署，运行数据已经留档。"
    return f"{display_name}在实战中{'，'.join(clauses)}，对应数据已经留档。"


def _configured_battle_assets(config: dict[str, Any]) -> list[dict[str, Any]]:
    configured: list[dict[str, Any]] = []
    for field, role, default_kind in (
        ("basic_defense", "basic", "tower_blueprint"),
        ("sample_asset", "sample", "temporary_trap_sample"),
        ("support_asset", "support", "support_item"),
    ):
        item = config.get(field)
        if not isinstance(item, dict) or not item:
            continue
        ids = {
            str(value)
            for value in (item.get("stable_internal_id"), item.get("runtime_object_id"))
            if value
        }
        configured.append(
            {
                "ids": ids,
                "object_id": str(item.get("runtime_object_id") or item.get("stable_internal_id") or ""),
                "display_name": str(item.get("display_name") or "未命名装置"),
                "asset_kind": str(item.get("asset_kind") or default_kind),
                "role": role,
                "behavior_abi": item.get("runtime_behavior_abi")
                if isinstance(item.get("runtime_behavior_abi"), dict)
                else {},
                "effect_summary": str(item.get("effect_summary") or ""),
                "source": "battle_config",
            }
        )
    return configured


def _deployed_asset_summaries(
    deployed_asset_ids: list[Any],
    battle_config: dict[str, Any],
    runtime_bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    configured = _configured_battle_assets(battle_config)
    configured_by_id = {
        asset_id: item for item in configured for asset_id in item["ids"]
    }
    capabilities = runtime_bundle.get("capabilities", {})
    runtime_objects = capabilities.get("battle_objects", []) if isinstance(capabilities, dict) else []
    runtime_by_id = {
        str(item.get("object_id")): item
        for item in runtime_objects
        if isinstance(item, dict) and item.get("object_id")
    }
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_id in deployed_asset_ids:
        asset_id = str(raw_id or "").strip()
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        runtime_object = runtime_by_id.get(asset_id)
        configured_asset = configured_by_id.get(asset_id)
        if runtime_object:
            behavior = runtime_object.get("behavior_abi")
            if not isinstance(behavior, dict):
                behavior = {}
            tool_id = str(runtime_object.get("tool_id") or runtime_object.get("hotbar_id") or "")
            role = tool_id if tool_id in {"basic", "sample", "support"} else (
                configured_asset["role"] if configured_asset else "compiled"
            )
            name = str(runtime_object.get("display_name") or asset_id)
            summary = {
                "object_id": asset_id,
                "display_name": name,
                "asset_kind": str(runtime_object.get("asset_kind") or "runtime_object"),
                "role": role,
                "source": "activated_runtime" if runtime_object.get("source_runtime_ref") else "runtime_fixture",
                "effect_summary": _effect_summary(name, behavior),
            }
        elif configured_asset:
            name = configured_asset["display_name"]
            effect_summary = configured_asset["effect_summary"] or _effect_summary(
                name, configured_asset["behavior_abi"]
            )
            summary = {
                "object_id": configured_asset["object_id"] or asset_id,
                "display_name": name,
                "asset_kind": configured_asset["asset_kind"],
                "role": configured_asset["role"],
                "source": configured_asset["source"],
                "effect_summary": effect_summary,
            }
        else:
            summary = {
                "object_id": asset_id,
                "display_name": asset_id,
                "asset_kind": "unknown",
                "role": "unknown",
                "source": "submitted_result",
                "effect_summary": "该对象已部署，但当前运行包中没有可用于结算的说明。",
            }
        summaries.append(summary)
    return summaries


def _primary_deployed_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (item for item in reversed(assets) if item.get("role") in {"sample", "compiled"}),
        next((item for item in reversed(assets) if item.get("role") != "basic"), None),
    )


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


def _compiled_world_initial_state(bundle: dict[str, Any]) -> dict[str, Any]:
    world_map = bundle["map"]
    worldbook = bundle["worldbook"]
    return {
        "schema_version": "run_world_state.v0.1",
        "worldbook_id": world_map["worldbook_id"],
        "progress": {"chapter": 1, "turn": 1, "phase": "first_defense"},
        "map_nodes": [
            {
                "node_id": item["stable_internal_id"],
                "display_name": item["display_name"],
                "state": item.get("state"),
                "summary": item.get("summary"),
            }
            for item in world_map.get("nodes", [])
        ],
        "resources": [
            {"resource_id": resource_id, "display_name": item.get("display_name"), "quantity": 4}
            for resource_id, item in worldbook.get("resource_mapping", {}).items()
        ],
        "npcs": [
            {"npc_id": item.get("stable_internal_id"), "display_name": item.get("display_name")}
            for item in worldbook.get("npc_archetypes", [])
        ],
        "flags": {"compiled_world_instance": True},
        "event_log": [],
    }


def create_world_instance(
    session_id: str,
    overrides: dict[str, Any] | None = None,
    *,
    world_id: str = "long_night_lanterns",
) -> dict[str, Any]:
    bundle = world_catalog_service.load_world_bundle(world_id)
    config = bundle["world_config"]
    state = (
        _load_json(_INITIAL_RUN_STATE)
        if world_id == "long_night_lanterns"
        else _compiled_world_initial_state(bundle)
    )
    selected = _selected_options(config, overrides)
    payload = {
        "worldbook_id": config.get("worldbook_template_id"),
        "config": config,
        "selected_options": selected,
        "mode": "reviewed_template" if world_id == "long_night_lanterns" else "compiled_world_runtime",
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
        "world_bundle": bundle,
        "world_catalog": world_catalog_service.get_catalog(),
    }


def get_frontend_mock_pack(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "pack": _load_frontend_pack(),
        "ai_compile_core_artifacts": ai_core_artifact_service.core_artifact_payload(),
        "activated_runtime_bundle": _player_runtime_bundle(session_id),
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
    bundle = world_catalog_service.session_bundle(session_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "opening": bundle["opening"],
    }


def get_animation_seeds(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "animation_seed_manifest": frontend_media_service.load_animation_seed_manifest(),
        "animation_pipeline_status": "seed_images_ready_video_frames_not_generated",
    }


def get_map(session_id: str) -> dict[str, Any]:
    state = _load_campaign_state(session_id)
    bundle = world_catalog_service.session_bundle(session_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "map": bundle["map"],
        "run_world_state": state,
        "activated_runtime_bundle": _player_runtime_bundle(session_id, state=state),
    }


def get_feature_runtime(session_id: str, node_id: str | None = None) -> dict[str, Any]:
    state = _load_campaign_state(session_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "activated_runtime_bundle": _player_runtime_bundle(
            session_id,
            node_id=node_id,
            state=state,
        ),
    }


def get_node_briefing(session_id: str, node_id: str) -> dict[str, Any]:
    bundle = world_catalog_service.session_bundle(session_id)
    if bundle["catalog_entry"]["world_id"] != "long_night_lanterns":
        if node_id != bundle["catalog_entry"]["entry_node_id"]:
            raise FixtureNotFoundError(node_id)
        worldbook = bundle["worldbook"]
        materials = [
            {"material_id": key, **value}
            for key, value in worldbook.get("resource_mapping", {}).items()
        ]
        npcs = list(worldbook.get("npc_archetypes") or [])
        return {
            "session_id": session_id,
            "mode": "compiled_world_runtime",
            "node_id": node_id,
            "briefing": bundle["briefing"],
            "materials": materials,
            "npcs": npcs,
            "suggested_input": bundle["suggested_input"],
            "activated_runtime_bundle": _player_runtime_bundle(session_id, node_id=node_id),
        }
    if node_id not in _NODE_BRIEFING_OVERRIDES:
        raise FixtureNotFoundError(node_id)
    override = _NODE_BRIEFING_OVERRIDES[node_id]
    pack = _load_frontend_pack()
    state = _load_campaign_state(session_id)
    if override.get("source_path"):
        briefing = _load_json(override["source_path"])
    else:
        try:
            battle_config = battle_content_service.load_battle_config(node_id)
        except battle_content_service.BattleContentNotFoundError as exc:
            raise FixtureNotFoundError(node_id) from exc
        node = next(
            (
                item
                for item in state.get("map_nodes", [])
                if isinstance(item, dict) and item.get("node_id") == node_id
            ),
            {},
        )
        available_materials = [
            {
                "material_id": item.get("material_id")
                or item.get("resource_id")
                or item.get("stable_internal_id"),
                "quantity": item.get("quantity", item.get("amount", item.get("default_quantity", 0))),
            }
            for item in pack.get("materials", [])
            if isinstance(item, dict)
        ]
        briefing = {
            "node_id": node_id,
            "display_name": battle_config.get("display_name", node_id),
            "summary": battle_config.get("summary")
            or node.get("summary")
            or battle_config.get("victory_condition", "守住当前节点。"),
            "threat": {
                "enemy_traits": ", ".join(
                    wave.get("display_name", "影潮")
                    for wave in battle_config.get("waves", [])
                    if isinstance(wave, dict)
                )
                or "影潮压力正在升高。",
                "approach_direction": "由节点外缘向核心设施压近。",
            },
            "protection_targets": [
                target
                for target in [
                    battle_config.get("core_target"),
                    *(battle_config.get("optional_targets", []) or []),
                ]
                if isinstance(target, dict)
            ],
            "available_materials": available_materials,
            "facility_state": {"summary": "现场工坊可进行应急试作。"},
            "constraints": {"sample_delivery": "样品可在战斗中途送达。"},
        }
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "briefing": briefing,
        "materials": pack.get("materials", []),
        "npcs": pack.get("npcs", []),
        "suggested_input": override["suggested_input"],
        "activated_runtime_bundle": _player_runtime_bundle(
            session_id,
            node_id=node_id,
            state=state,
        ),
    }


def get_battle_config(session_id: str, node_id: str) -> dict[str, Any]:
    bundle = world_catalog_service.session_bundle(session_id)
    if bundle["catalog_entry"]["world_id"] != "long_night_lanterns":
        if node_id != bundle["catalog_entry"]["entry_node_id"]:
            raise FixtureNotFoundError(node_id)
        pack = _load_frontend_pack()
        map_package = bundle["map_runtime_package"]
        render_bundle = {
            "node_id": node_id,
            "refs": {},
            "map_style_pack": bundle["map_style_pack"],
            "procedural_map_render_plan": bundle["map_render_plan"],
            "semantic_visual_consistency_report": bundle["semantic_visual_consistency_report"],
        }
        return {
            "session_id": session_id,
            "mode": "compiled_world_runtime",
            "node_id": node_id,
            "battle_config": bundle["battle_config"],
            "map_runtime_package": map_package,
            "runtime_selection": {
                "selection_mode": "compiled_world_manifest",
                "selected_schema_version": map_package.get("schema_version"),
                "selected_package_id": map_package.get("package_id"),
                "activation_applied": True,
                "fallback_reasons": [],
            },
            "map_render_plan_bundle": render_bundle,
            "layered_map_visual_package": bundle["layered_map_visual_package"],
            "toolbar_assets": _battle_toolbar_assets(pack),
            "sample_delivery_asset": _asset_for_sample_delivery(pack),
            "activated_runtime_bundle": _player_runtime_bundle(session_id, node_id=node_id),
            **frontend_media_service.frontend_media_payload(),
            **frontend_media_service.runtime_art_payload(),
        }
    try:
        config = battle_content_service.load_battle_config(node_id)
    except battle_content_service.BattleContentNotFoundError as exc:
        raise FixtureNotFoundError(node_id) from exc
    pack = _load_frontend_pack()
    map_runtime_payload = map_runtime_service.get_map_runtime_package(session_id, node_id)
    map_runtime_package = map_runtime_payload["map_runtime_package"]
    runtime_selection = map_runtime_payload["runtime_selection"]
    map_render_plan_bundle = (
        map_render_plan_service.load_map_render_plan_bundle_for_runtime_optional(
            node_id, runtime_selection.get("selected_schema_version")
        )
    )
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "battle_config": config,
        "map_runtime_package": map_runtime_package,
        "runtime_selection": runtime_selection,
        "map_render_plan_bundle": map_render_plan_bundle,
        "toolbar_assets": _battle_toolbar_assets(pack),
        "sample_delivery_asset": _asset_for_sample_delivery(pack),
        "activated_runtime_bundle": _player_runtime_bundle(session_id, node_id=node_id),
        **frontend_media_service.frontend_media_payload(),
        **frontend_media_service.runtime_art_payload(),
    }


def get_map_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    bundle = world_catalog_service.session_bundle(session_id)
    if bundle["catalog_entry"]["world_id"] == "long_night_lanterns":
        return map_runtime_service.get_map_runtime_package(session_id, node_id)
    if node_id != bundle["catalog_entry"]["entry_node_id"]:
        raise FixtureNotFoundError(node_id)
    map_package = bundle["map_runtime_package"]
    return {
        "session_id": session_id,
        "mode": "compiled_world_runtime",
        "node_id": node_id,
        "map_runtime_package": map_package,
        "runtime_selection": {
            "selection_mode": "compiled_world_manifest",
            "selected_schema_version": map_package.get("schema_version"),
            "selected_package_id": map_package.get("package_id"),
            "activation_applied": True,
            "fallback_reasons": [],
        },
    }


def get_map_render_plan(session_id: str, node_id: str) -> dict[str, Any]:
    bundle = world_catalog_service.session_bundle(session_id)
    if bundle["catalog_entry"]["world_id"] == "long_night_lanterns":
        runtime_payload = map_runtime_service.get_map_runtime_package(session_id, node_id)
        runtime_selection = runtime_payload["runtime_selection"]
        return map_render_plan_service.get_map_render_plan_bundle(
            session_id,
            node_id,
            runtime_schema_version=runtime_selection.get("selected_schema_version"),
            runtime_selection=runtime_selection,
        )
    if node_id != bundle["catalog_entry"]["entry_node_id"]:
        raise FixtureNotFoundError(node_id)
    map_package = bundle["map_runtime_package"]
    runtime_selection = {
        "selection_mode": "compiled_world_manifest",
        "selected_schema_version": map_package.get("schema_version"),
        "selected_package_id": map_package.get("package_id"),
        "activation_applied": True,
        "fallback_reasons": [],
    }
    return {
        "session_id": session_id,
        "mode": "compiled_world_runtime",
        "node_id": node_id,
        "map_render_plan_bundle": {
            "node_id": node_id,
            "refs": {},
            "map_style_pack": bundle["map_style_pack"],
            "procedural_map_render_plan": bundle["map_render_plan"],
            "semantic_visual_consistency_report": bundle[
                "semantic_visual_consistency_report"
            ],
        },
        "runtime_selection": runtime_selection,
    }


def get_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    try:
        runtime_package = battle_content_service.load_runtime_package(node_id)
    except battle_content_service.BattleContentNotFoundError as exc:
        raise FixtureNotFoundError(node_id) from exc
    pack = _load_frontend_pack()
    map_runtime_payload = map_runtime_service.get_map_runtime_package(session_id, node_id)
    runtime_selection = map_runtime_payload["runtime_selection"]
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "runtime_package": runtime_package,
        "map_runtime_package": map_runtime_payload["map_runtime_package"],
        "runtime_selection": runtime_selection,
        "map_render_plan_bundle": (
            map_render_plan_service.load_map_render_plan_bundle_for_runtime_optional(
                node_id, runtime_selection.get("selected_schema_version")
            )
        ),
        "sample_delivery_asset": _asset_for_sample_delivery(pack),
        "activated_runtime_bundle": _player_runtime_bundle(session_id, node_id=node_id),
        **frontend_media_service.frontend_media_payload(),
        **frontend_media_service.runtime_art_payload(),
    }


def record_battle_result(
    session_id: str,
    node_id: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bundle = world_catalog_service.session_bundle(session_id)
    submitted = result if isinstance(result, dict) else {}
    battle_run_id = submitted.get("battle_run_id")
    if not isinstance(battle_run_id, str):
        battle_run_id = None
    existing_result = _load_battle_result_by_run_id(session_id, battle_run_id)
    if existing_result is not None:
        existing_node_id = existing_result.get("node_id")
        if existing_node_id != node_id:
            raise FixtureNotFoundError(node_id)
        state = _load_campaign_state(session_id)
        return {
            "session_id": session_id,
            "mode": (
                "frontend_mock_fixture"
                if bundle["catalog_entry"]["world_id"] == "long_night_lanterns"
                else "compiled_world_runtime"
            ),
            "settlement": existing_result.get("settlement"),
            "activated_runtime_bundle": _player_runtime_bundle(
                session_id, node_id=node_id, state=state
            ),
        }
    if bundle["catalog_entry"]["world_id"] != "long_night_lanterns":
        if node_id != bundle["catalog_entry"]["entry_node_id"]:
            raise FixtureNotFoundError(node_id)
        state = _load_campaign_state(session_id)
        settlement = {
            "node_id": node_id,
            "settlement_mode": "compiled_world_mvp",
            "result": submitted.get("result", "victory"),
            "battle_summary": bundle["battle_config"].get("post_battle", {}).get(
                "on_victory", "节点守住，新的线索开始生长。"
            ),
            "sample_performance": "试作品的首轮表现已经写入本局档案。",
            "npc_feedback": "在场角色会依据实战表现调整后续建议。",
            "world_delta": {
                "summary": f"{bundle['briefing']['display_name']}的局势因本场战斗发生变化。"
            },
            "world_delta_transaction": None,
            "fixture_baseline": None,
            "core_artifact_refs": {},
            "core_artifacts": None,
            "run_world_state": state,
        }
        ts = now_iso()
        with db_cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO battle_results "
                "(session_id, idempotency_key, payload, created_at) VALUES (?, ?, ?, ?)",
                (session_id, battle_run_id, _dump_payload({"node_id": node_id, "submitted_result": submitted, "settlement": settlement}), ts),
            )
        return {
            "session_id": session_id,
            "mode": "compiled_world_runtime",
            "settlement": settlement,
            "activated_runtime_bundle": _player_runtime_bundle(session_id, node_id=node_id, state=state),
        }
    spec = _NODE_SETTLEMENT_SPECS.get(node_id)
    if spec is None:
        raise FixtureNotFoundError(node_id)
    battle_config = battle_content_service.load_battle_config(node_id)
    delta = _load_json(spec["world_delta_path"]) if spec.get("world_delta_path") else None
    if node_id == "gray_lantern_station":
        transaction = ai_core_artifact_service.load_world_delta_transaction()
    elif spec.get("transaction_path"):
        transaction = _load_json(spec["transaction_path"])
    else:
        transaction = None
    previous_state = _load_campaign_state(session_id)
    if spec.get("after_state_path"):
        next_state = _load_json(spec["after_state_path"])
        next_state = post_battle_world_evolution_service.replay_committed_deltas(
            next_state, _load_committed_world_evolution_deltas(session_id)
        )
    elif delta:
        next_state = _apply_delta_to_state(previous_state, delta)
    else:
        next_state = previous_state
    runtime_bundle = _player_runtime_bundle(session_id, node_id=node_id, state=previous_state)
    deployed_assets = _deployed_asset_summaries(
        submitted.get("deployed_asset_ids", [])
        if isinstance(submitted.get("deployed_asset_ids"), list)
        else [],
        battle_config,
        runtime_bundle,
    )
    primary_asset = _primary_deployed_asset(deployed_assets)
    ts = now_iso()
    core_artifacts = None
    if delta and transaction:
        core_artifacts = ai_core_artifact_service.battle_settlement_core_artifacts(
            node_id=node_id,
            world_delta_ref=_rel(spec["world_delta_path"]),
            world_delta=delta,
            transaction=transaction,
            transaction_ref=_rel(spec["transaction_path"]) if spec.get("transaction_path") else None,
            created_at=ts,
        )
    refs: dict[str, Any] = {}
    if core_artifacts:
        refs.update(core_artifacts["refs"])
    if spec.get("world_delta_path"):
        refs["world_delta"] = _rel(spec["world_delta_path"])
    if spec.get("transaction_path"):
        refs["world_delta_transaction"] = _rel(spec["transaction_path"])
    if spec.get("after_state_path"):
        refs["run_world_state_after"] = _rel(spec["after_state_path"])
    settlement_mode = spec["mode"]
    baseline = None
    if settlement_mode == "fixture_bridge":
        baseline = {
            "mode": "fixture_bridge",
            "baseline_ref": refs.get("run_world_state_after"),
            "baseline_type": (transaction or {}).get("source"),
            "transaction_id": (transaction or {}).get("transaction_id"),
            "notes": "MVP 旧信号塔使用已审研究/世界状态快照作为结算桥接，不伪装为 battle_result transaction。",
        }
    settlement = {
        "node_id": node_id,
        "settlement_mode": settlement_mode,
        "result": submitted.get("result", "victory"),
        "battle_summary": battle_config.get("post_battle", {}).get(
            "on_victory", "节点守住，样品表现已记录。"
        ),
        "sample_performance": (
            primary_asset["effect_summary"]
            if primary_asset
            else "本场没有实际部署试作品；结算只记录基础防线表现。"
        ),
        "deployed_assets": deployed_assets,
        "primary_deployed_asset": primary_asset,
        "primary_sample_name": (
            primary_asset["display_name"]
            if primary_asset and primary_asset.get("role") in {"sample", "compiled"}
            else None
        ),
        "npc_feedback": spec["npc_feedback"],
        "world_delta": delta,
        "world_delta_transaction": transaction,
        "fixture_baseline": baseline,
        "core_artifact_refs": refs,
        "core_artifacts": core_artifacts,
        "run_world_state": next_state,
    }
    evolution = post_battle_world_evolution_service.evolve_world(
        deterministic_state=next_state,
        battle_result=_live_battle_result(
            submitted,
            node_id=node_id,
            battle_config=battle_config,
            deployed_assets=deployed_assets,
        ),
        deployed_objects=deployed_assets,
        session_context=_battle_evolution_session_context(session_id, next_state, node_id),
    )
    # The diagnostic is internal-only: record it for studio observability but
    # never surface it through the player settlement or FeatureSnapshot.
    _record_world_evolution_diagnostic(session_id, evolution.get("diagnostic"))
    if evolution.get("applied") is True:
        next_state = evolution["state"]
        settlement["run_world_state"] = next_state
        settlement["world_evolution_delta"] = evolution["delta"]
        projection = evolution.get("projection")
        if isinstance(projection, dict):
            if projection.get("interlude_summary"):
                settlement["interlude_summary"] = projection["interlude_summary"]
            if projection.get("npc_feedback"):
                settlement["npc_feedback"] = projection["npc_feedback"]
            if isinstance(projection.get("next_task"), dict):
                settlement["next_task"] = projection["next_task"]
    inserted = _save_battle_settlement_and_state(
        session_id,
        node_id=node_id,
        submitted=submitted,
        settlement=settlement,
        state=next_state,
        created_at=ts,
    )
    if not inserted:
        existing_result = _load_battle_result_by_run_id(session_id, battle_run_id)
        if existing_result is not None:
            next_state = _load_campaign_state(session_id)
            settlement = existing_result.get("settlement") or settlement
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "settlement": settlement,
        "activated_runtime_bundle": _player_runtime_bundle(
            session_id,
            node_id=node_id,
            state=next_state,
        ),
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
            "activated_runtime_bundle": _player_runtime_bundle(session_id),
        }
    payload = json.loads(row["payload"])
    settlement = payload.get("settlement")
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "created_at": row["created_at"],
        "settlement": settlement,
        "activated_runtime_bundle": _player_runtime_bundle(
            session_id,
            node_id=(settlement or {}).get("node_id") if isinstance(settlement, dict) else None,
        ),
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
        "ai_compile_core_artifacts": ai_core_artifact_service.core_artifact_payload(),
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
