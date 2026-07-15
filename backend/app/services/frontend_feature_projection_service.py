"""Build player-safe FeatureSnapshots from activated runtime and session state.

The service never consumes candidate/provider output directly. It starts from an
explicitly activated runtime bundle, then projects committed RunWorldState and
session records into allowlisted declarative frontend contributions.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from ..db import db_cursor
from . import runtime_activation_service


_REPO_ROOT = Path(__file__).resolve().parents[3]
_ACTIVATED_RUNTIME_BUNDLE = (
    _REPO_ROOT / "examples/frontend_runtime/activated_runtime_bundle.mvp.v0.1.json"
)
_ACTIVE_TASK_STATUSES = {"active", "available", "running", "queued"}
_ACTIVE_EVENT_STATUSES = {"available", "pending"}
_NPC_NAMES = {
    "engineer_001": "驿站守灯人",
    "scout_002": "北路斥候",
    "npc_wire_mender_003": "补线人",
    "npc_road_scout": "北路斥候",
}
_ROLE_NAMES = {
    "field_engineer": "现场改造",
    "route_repair": "补给线抢修",
    "material_adjustment": "材料替换",
    "field_review": "试作评审",
    "path_prediction": "路径预判",
    "weakness_hint": "敌情提示",
    "scouting_reliability": "侦察校准",
    "scout": "侦察",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_id(value: Any, fallback: str = "runtime") -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or ""))[:128]
    return normalized or fallback


def _safe_text(value: Any, limit: int = 600) -> str:
    return str(value or "").replace("<", "").replace(">", "")[:limit]


def _contribution(
    *,
    contribution_id: str,
    feature_id: str,
    surface: str,
    kind: str,
    slot: str,
    priority: int,
    payload: dict[str, Any],
    target_node_id: str | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "schema_version": "frontend_surface_contribution.v0.1",
        "contribution_id": _safe_id(contribution_id),
        "feature_id": feature_id,
        "surface": surface,
        "kind": kind,
        "slot": slot,
        "priority": max(-1000, min(1000, int(priority))),
        "visibility": "player_visible",
        "payload": payload,
    }
    if target_node_id:
        item["target_node_id"] = _safe_id(target_node_id)
    if source_refs:
        item["source_refs"] = [_safe_text(ref, 240) for ref in source_refs[:16]]
    return item


def _latest_proposal(session_id: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT proposal_id, node_id, display_name, summary, risk_note, status "
            "FROM research_proposals WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _latest_settlement(session_id: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM battle_results WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if not row or not row.get("payload"):
        return None
    payload = json.loads(row["payload"])
    settlement = payload.get("settlement")
    return settlement if isinstance(settlement, dict) else None


def _strategic_contributions(world: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for task in _as_list(world.get("tasks")):
        task = _as_dict(task)
        if task.get("status") not in _ACTIVE_TASK_STATUSES:
            continue
        task_id = _safe_id(task.get("task_id"), "task")
        node_id = _safe_id(task.get("node_id"), "")
        items.append(
            _contribution(
                contribution_id=f"world_task_{task_id}",
                feature_id="strategic_map",
                surface="strategic_map",
                kind="objective_card",
                slot="objective_overlay",
                priority=80,
                target_node_id=node_id or None,
                source_refs=[f"run_world_state.tasks.{task_id}"],
                payload={
                    "title": _safe_text(task.get("title") or "当前任务", 120),
                    "summary": _safe_text(task.get("summary")),
                    "status": _safe_id(task.get("status"), "active"),
                    **({"node_id": node_id} if node_id else {}),
                },
            )
        )
    for event in _as_list(world.get("random_events")):
        event = _as_dict(event)
        if event.get("status") not in _ACTIVE_EVENT_STATUSES:
            continue
        event_id = _safe_id(event.get("random_event_id"), "random_event")
        node_id = _safe_id(event.get("node_id"), "")
        event_type = str(event.get("event_type") or "")
        items.append(
            _contribution(
                contribution_id=f"world_event_{event_id}",
                feature_id="strategic_map",
                surface="strategic_map",
                kind="map_notice",
                slot="objective_overlay",
                priority=70,
                target_node_id=node_id or None,
                source_refs=[f"run_world_state.random_events.{event_id}"],
                payload={
                    "title": "随机预警" if event_type == "threat_warning" else "临机事件",
                    "summary": _safe_text(event.get("summary")),
                    "severity": "warning" if event_type in {"threat_warning", "map_pressure"} else "notice",
                    "node_id": node_id or "world",
                },
            )
        )
    for npc in _as_list(world.get("npcs")):
        npc = _as_dict(npc)
        if npc.get("availability") == "absent" or not npc.get("location_node_id"):
            continue
        npc_id = _safe_id(npc.get("npc_id"), "npc")
        node_id = _safe_id(npc.get("location_node_id"), "world")
        roles = [_safe_id(role) for role in _as_list(npc.get("gameplay_roles"))[:8]]
        role_summary = " / ".join(_ROLE_NAMES.get(role, role) for role in roles[:2]) or "现场建议"
        items.append(
            _contribution(
                contribution_id=f"world_npc_{npc_id}_{node_id}",
                feature_id="strategic_map",
                surface="strategic_map",
                kind="node_participant",
                slot="node_panel",
                priority=50,
                target_node_id=node_id,
                source_refs=[f"run_world_state.npcs.{npc_id}"],
                payload={
                    "npc_id": npc_id,
                    "display_name": _safe_text(npc.get("display_name") or _NPC_NAMES.get(npc_id) or npc_id, 120),
                    "summary": _safe_text(npc.get("player_summary") or f"可提供{role_summary}"),
                    "node_id": node_id,
                    "gameplay_roles": roles,
                },
            )
        )
    return items


def _workshop_contributions(
    world: dict[str, Any], proposal: dict[str, Any] | None, node_id: str | None
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if proposal:
        proposal_id = _safe_id(proposal.get("proposal_id"), "proposal")
        proposal_node = _safe_id(proposal.get("node_id"), node_id or "world")
        items.append(
            _contribution(
                contribution_id=f"research_proposal_{proposal_id}",
                feature_id="workshop",
                surface="prototype_workshop",
                kind="proposal_hint",
                slot="proposal_panel",
                priority=90,
                target_node_id=proposal_node,
                source_refs=[f"research_proposals.{proposal_id}"],
                payload={
                    "title": _safe_text(proposal.get("display_name") or "当前试作", 120),
                    "summary": _safe_text(proposal.get("summary")),
                    "status": _safe_id(proposal.get("status"), "proposed"),
                    "node_id": proposal_node,
                },
            )
        )
    for npc in _as_list(world.get("npcs")):
        npc = _as_dict(npc)
        npc_node = _safe_id(npc.get("location_node_id"), "")
        if not node_id or npc_node != _safe_id(node_id) or npc.get("availability") == "absent":
            continue
        npc_id = _safe_id(npc.get("npc_id"), "npc")
        items.append(
            _contribution(
                contribution_id=f"workshop_npc_{npc_id}_{npc_node}",
                feature_id="workshop",
                surface="prototype_workshop",
                kind="participant_notice",
                slot="participant_panel",
                priority=50,
                target_node_id=npc_node,
                source_refs=[f"run_world_state.npcs.{npc_id}"],
                payload={
                    "npc_id": npc_id,
                    "display_name": _safe_text(_NPC_NAMES.get(npc_id) or npc_id, 120),
                    "summary": _safe_text("可参与当前节点的现场试作评审。"),
                    "node_id": npc_node,
                },
            )
        )
    return items[:8]


def _narrative_contributions(world: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in _as_list(world.get("event_log"))[-3:]:
        event = _as_dict(event)
        event_id = _safe_id(event.get("event_id"), "event")
        items.append(
            _contribution(
                contribution_id=f"narrative_{event_id}",
                feature_id="narrative",
                surface="dialogue_modal",
                kind="narrative_beat",
                slot="dialogue_queue",
                priority=int(event.get("turn") or 0),
                source_refs=[f"run_world_state.event_log.{event_id}"],
                payload={
                    "beat_id": event_id,
                    "speaker_id": "world_narrator",
                    "speaker_name": "长夜回响",
                    "text": _safe_text(event.get("summary"), 1200),
                },
            )
        )
    return items


def _settlement_contributions(settlement: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not settlement:
        return []
    node_id = _safe_id(settlement.get("node_id"), "world")
    items = [
        _contribution(
            contribution_id=f"settlement_result_{node_id}",
            feature_id="settlement",
            surface="settlement_panel",
            kind="settlement_note",
            slot="result_summary",
            priority=90,
            target_node_id=node_id,
            source_refs=[f"battle_results.{node_id}.settlement"],
            payload={
                "title": "战斗复盘",
                "summary": _safe_text(settlement.get("battle_summary")),
                "node_id": node_id,
            },
        )
    ]
    world_delta = _as_dict(settlement.get("world_delta"))
    interlude_summary = _safe_text(settlement.get("interlude_summary"))
    next_task = _as_dict(settlement.get("next_task"))
    evolution_parts = [interlude_summary] if interlude_summary else []
    if next_task.get("title"):
        task_summary = _safe_text(next_task.get("summary"))
        evolution_parts.append(
            f"下一步：{_safe_text(next_task.get('title'), 120)}"
            + (f"。{task_summary}" if task_summary else "")
        )
    world_delta_summary = _safe_text(" ".join(evolution_parts))
    if not world_delta_summary:
        world_delta_summary = _safe_text(world_delta.get("summary"))
    if not world_delta_summary:
        committed_events = _as_list(_as_dict(settlement.get("run_world_state")).get("event_log"))
        if committed_events:
            world_delta_summary = _safe_text(_as_dict(committed_events[-1]).get("summary"))
    if not world_delta_summary:
        world_delta_summary = _safe_text(settlement.get("npc_feedback"))
    if world_delta_summary:
        items.append(
            _contribution(
                contribution_id=f"settlement_world_delta_{node_id}",
                feature_id="settlement",
                surface="settlement_panel",
                kind="settlement_note",
                slot="world_delta",
                priority=70,
                target_node_id=node_id,
                source_refs=[f"battle_results.{node_id}.world_delta"],
                payload={
                    "title": "世界变化",
                    "summary": world_delta_summary,
                    "node_id": node_id,
                },
            )
        )
    return items


def _merge_contributions(snapshot: dict[str, Any], additions: list[dict[str, Any]]) -> None:
    merged: dict[str, dict[str, Any]] = {}
    for item in [*_as_list(snapshot.get("contributions")), *additions]:
        item = _as_dict(item)
        contribution_id = str(item.get("contribution_id") or "")
        if contribution_id:
            merged[contribution_id] = item
    snapshot["contributions"] = sorted(
        merged.values(),
        key=lambda item: (-int(item.get("priority") or 0), str(item.get("contribution_id"))),
    )[:128]


def build_player_runtime_bundle(
    session_id: str,
    *,
    run_world_state: dict[str, Any],
    node_id: str | None = None,
) -> dict[str, Any]:
    bundle = copy.deepcopy(_load_json(_ACTIVATED_RUNTIME_BUNDLE))
    activation_ids: list[str] = []
    battle_objects = {
        str(item.get("object_id")): item
        for item in _as_list(_as_dict(bundle.get("capabilities")).get("battle_objects"))
        if isinstance(item, dict) and item.get("object_id")
    }
    for patch in runtime_activation_service.active_runtime_patches(session_id):
        activation_id = str(patch.get("activation_id") or "")
        if activation_id:
            activation_ids.append(activation_id)
        for item in _as_list(patch.get("battle_objects")):
            if isinstance(item, dict) and item.get("object_id"):
                battle_objects[str(item["object_id"])] = item
    bundle["capabilities"]["battle_objects"] = list(battle_objects.values())
    bundle["runtime_selection"]["session_activation_ids"] = activation_ids
    proposal = _latest_proposal(session_id)
    settlement = _latest_settlement(session_id)
    snapshots = _as_dict(bundle.get("feature_snapshots"))
    _merge_contributions(
        _as_dict(snapshots.get("strategic_map")),
        _strategic_contributions(run_world_state),
    )
    _merge_contributions(
        _as_dict(snapshots.get("workshop")),
        _workshop_contributions(run_world_state, proposal, node_id),
    )
    _merge_contributions(
        _as_dict(snapshots.get("narrative")),
        _narrative_contributions(run_world_state),
    )
    _merge_contributions(
        _as_dict(snapshots.get("settlement")),
        _settlement_contributions(settlement),
    )
    if node_id:
        bundle["runtime_selection"]["current_node_id"] = _safe_id(node_id)
    return bundle
