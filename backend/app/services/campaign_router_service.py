"""Fixture-backed live campaign router.

The router is the thin runtime glue between the current RunWorldState cursor,
reviewed battle/map packages, WorldStateDeltaTransaction evidence, and the
Generation Scheduler dry-run queue. It does not call providers, generate
content, or mutate world state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..db import db_cursor
from . import battle_content_service, generation_scheduler_service, map_runtime_service


_REPO_ROOT = Path(__file__).resolve().parents[3]
_INITIAL_RUN_STATE = _REPO_ROOT / "examples/run_world_states/demo_initial.run_world_state.json"


class CampaignRouteNotFoundError(LookupError):
    """Raised when the fixture campaign route cannot resolve a node."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_campaign_state(session_id: str) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM campaign_state WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if row and row.get("payload"):
        payload = json.loads(row["payload"])
        if isinstance(payload, dict):
            return payload
    return _load_json(_INITIAL_RUN_STATE)


def _known_battle_nodes() -> set[str]:
    return set(battle_content_service.available_battle_node_ids())


def _known_map_nodes() -> set[str]:
    return set(map_runtime_service.available_map_runtime_node_ids())


def _asset_handle(node_id: str) -> dict[str, Any]:
    battle_config_ref = battle_content_service.battle_config_ref(node_id)
    runtime_package_ref = battle_content_service.runtime_package_ref(node_id)
    map_package_ref = map_runtime_service.map_runtime_package_ref(node_id)
    ready = all((battle_config_ref, runtime_package_ref, map_package_ref))
    return {
        "node_id": node_id,
        "status": "ready" if ready else "fallback_ready",
        "battle_config_ref": battle_config_ref,
        "runtime_package_ref": runtime_package_ref,
        "map_runtime_package_ref": map_package_ref,
        "fallback_ref": "examples/runtime_packages/mvp_demo.runtime_package.json"
        if not ready
        else None,
        "provider_call_required": False,
        "world_mutation_required": False,
    }


def _route_steps() -> list[dict[str, Any]]:
    return [
        {
            "stage_index": 1,
            "node_id": "gray_lantern_station",
            "kind": "battle",
            "display_name": "灰灯驿站",
            "phase_triggers": ["first_defense"],
            "transaction_ref": (
                "examples/world_delta_transactions/"
                "stage_01_gray_lantern_first_defense.world_delta_transaction.json"
            ),
        },
        {
            "stage_index": 4,
            "node_id": "lamp_wick_store",
            "kind": "battle",
            "display_name": "灯芯仓",
            "phase_triggers": [
                "post_first_defense",
                "dawn_review_supply_line",
                "northern_road_scouting",
            ],
            "transaction_ref": (
                "examples/world_delta_transactions/"
                "stage_04_wick_store_pressure_battle.world_delta_transaction.json"
            ),
        },
        {
            "stage_index": 5,
            "node_id": "old_signal_tower",
            "kind": "battle",
            "display_name": "旧信号塔",
            "phase_triggers": [
                "post_wick_store_defense",
                "old_signal_tower_pressure_planned",
                "signal_resonance_trial",
            ],
            "transaction_ref": (
                "examples/world_delta_transactions/"
                "stage_05_old_signal_tower_pressure.world_delta_transaction.json"
            ),
        },
        {
            "stage_index": 7,
            "node_id": "northern_road_crossing",
            "kind": "future_branch",
            "display_name": "北路分潮口",
            "phase_triggers": ["split_tide_containment_planned"],
            "transaction_ref": (
                "examples/world_delta_transactions/"
                "stage_07_split_tide_containment.world_delta_transaction.json"
            ),
        },
    ]


def _current_route_index(state: dict[str, Any], steps: list[dict[str, Any]]) -> int:
    progress = state.get("progress", {})
    phase = progress.get("phase") if isinstance(progress, dict) else None
    for index, step in enumerate(steps):
        if phase in step.get("phase_triggers", []):
            return index
    return 0


def _route_step_payload(step: dict[str, Any]) -> dict[str, Any]:
    node_id = str(step["node_id"])
    handle = _asset_handle(node_id)
    playable = (
        node_id in _known_battle_nodes()
        and node_id in _known_map_nodes()
        and handle["status"] == "ready"
    )
    return {
        **step,
        "playable": playable,
        "asset_handle": handle,
        "api_refs": {
            "briefing": f"/api/sessions/{{session_id}}/nodes/{node_id}/briefing",
            "battle_config": f"/api/sessions/{{session_id}}/battles/{node_id}/config",
            "runtime_package": (
                f"/api/sessions/{{session_id}}/battles/{node_id}/runtime-package"
            ),
            "map_runtime_package": (
                f"/api/sessions/{{session_id}}/battles/{node_id}/map-runtime-package"
            ),
        },
    }


def _scheduler_signal(session_id: str) -> dict[str, Any]:
    latest = generation_scheduler_service.get_latest_generation_schedule_run(session_id)
    run = latest.get("generation_schedule_run")
    queue = latest.get("generation_schedule_queue", {})
    return {
        "latest_run_id": run.get("run_id") if isinstance(run, dict) else None,
        "queue_summary": queue.get("summary", {}) if isinstance(queue, dict) else {},
        "prefetch_endpoint": f"/api/sessions/{session_id}/campaign-router/prefetch-next",
        "provider_call_count": 0,
        "world_mutation_count": 0,
    }


def get_campaign_router(session_id: str) -> dict[str, Any]:
    state = _load_campaign_state(session_id)
    steps = _route_steps()
    current_index = _current_route_index(state, steps)
    current = _route_step_payload(steps[current_index])
    lookahead_steps = [
        _route_step_payload(step) for step in steps[current_index + 1 : current_index + 3]
    ]
    next_step = lookahead_steps[0] if lookahead_steps else None
    progress = state.get("progress", {})
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "campaign_router": {
            "schema_version": "campaign_router.v0.1",
            "router_mode": "fixture_backed_thin_router",
            "current": current,
            "next": next_step,
            "lookahead": lookahead_steps,
            "prefetch_window": {"behind": 1, "ahead": 2},
            "route": [_route_step_payload(step) for step in steps],
            "run_progress": {
                "phase": progress.get("phase") if isinstance(progress, dict) else None,
                "chapter": progress.get("chapter") if isinstance(progress, dict) else None,
                "turn": progress.get("turn") if isinstance(progress, dict) else None,
            },
            "scheduler_signal": _scheduler_signal(session_id),
            "boundary": {
                "provider_calls": False,
                "world_mutations": False,
                "state_owner": "WorldStateDeltaTransaction + campaign_state",
                "content_owner": "reviewed runtime packages and map runtime packages",
            },
        },
    }


def prefetch_next(session_id: str) -> dict[str, Any]:
    before = get_campaign_router(session_id)["campaign_router"]
    target = before.get("next")
    if not isinstance(target, dict):
        return {
            "session_id": session_id,
            "mode": "frontend_mock_fixture",
            "prefetch_request": {
                "status": "idle_no_next_node",
                "target_node_id": None,
                "target_asset_handle": None,
                "created_generation_schedule_run": False,
                "provider_call_count": 0,
                "world_mutation_count": 0,
            },
            "generation_schedule_run": None,
            "worker_step": {
                "status": "idle",
                "worker_mode": "fixture_backed_dry_worker",
                "provider_call_count": 0,
                "world_mutation_count": 0,
            },
            "generation_schedule_queue_item": None,
            "generation_schedule_queue": None,
            "campaign_router": before,
        }
    latest = generation_scheduler_service.get_latest_generation_schedule_run(session_id)
    run = latest.get("generation_schedule_run")
    created_run = None
    if run is None:
        created_run = generation_scheduler_service.create_generation_schedule_run(session_id)
    worker_step = generation_scheduler_service.run_generation_schedule_dry_worker_step(
        session_id,
        {
            "worker_id": "campaign_router_prefetch",
            "note": "router lookahead prefetch dry-run step",
        },
    )
    after = get_campaign_router(session_id)["campaign_router"]
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "prefetch_request": {
            "status": "requested",
            "target_node_id": target.get("node_id"),
            "target_asset_handle": target.get("asset_handle"),
            "created_generation_schedule_run": created_run is not None,
            "provider_call_count": 0,
            "world_mutation_count": 0,
        },
        "generation_schedule_run": (
            created_run.get("generation_schedule_run") if isinstance(created_run, dict) else None
        ),
        "worker_step": worker_step.get("worker_step"),
        "generation_schedule_queue_item": worker_step.get("generation_schedule_queue_item"),
        "generation_schedule_queue": worker_step.get("generation_schedule_queue"),
        "campaign_router": after,
    }
