"""Fixture-backed frontend mock service.

This service exposes the reviewed MVP content through backend APIs without
calling LLMs, image providers, or reading `.env`. It is the stable demo mode
for frontend development: the UI can exercise the full player flow while all
content comes from existing JSON packages and generated media manifests.
"""

from __future__ import annotations

import json
import secrets
from collections import Counter
from pathlib import Path
from typing import Any

from ..db import db_cursor, now_iso


_REPO_ROOT = Path(__file__).resolve().parents[3]

_WORLD_INSTANCE_CONFIG = (
    _REPO_ROOT / "content/worldbooks/long_night_lanterns/world_instance_config.json"
)
_OPENING = _REPO_ROOT / "content/worldbooks/long_night_lanterns/opening.json"
_INITIAL_RUN_STATE = _REPO_ROOT / "examples/run_world_states/demo_initial.run_world_state.json"
_INITIAL_MAP = _REPO_ROOT / "game_data/demo/initial_map.json"
_FIRST_CRISIS_NODE = _REPO_ROOT / "game_data/demo/first_crisis_node.json"
_FIRST_BATTLE_CONFIG = _REPO_ROOT / "game_data/demo/first_battle_config.json"
_FIRST_BATTLE_DELTA = (
    _REPO_ROOT / "examples/world_deltas/repaired_first_battle_semantic_pass.world_delta.json"
)
_FIRST_BATTLE_TRANSACTION = (
    _REPO_ROOT
    / "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json"
)
_FRONTEND_MOCK_PACK = _REPO_ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json"
_FRONTEND_RUNTIME_ART_KIT = (
    _REPO_ROOT / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json"
)
_MEDIA_MANIFEST = (
    _REPO_ROOT / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json"
)
_ANIMATION_SEED_MANIFEST = (
    _REPO_ROOT / "game_data/media/frontend_mock/frontend_animation_seed_manifest.v0.1.json"
)
_MEDIA_ATLAS_MANIFEST = (
    _REPO_ROOT / "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json"
)
_RUNTIME_ART_MEDIA_MANIFEST = (
    _REPO_ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json"
)
_RUNTIME_ART_ANIMATION_SEED_MANIFEST = (
    _REPO_ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_animation_seed_manifest.v0.1.json"
)
_RUNTIME_ART_ATLAS_MANIFEST = (
    _REPO_ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json"
)
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
_GENERATION_SCHEDULE_PLAN = (
    _REPO_ROOT / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json"
)
_GENERATION_SCHEDULE_RUN_REPORT = (
    _REPO_ROOT / "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json"
)

_BATTLE_CONFIG_BY_NODE = {
    "gray_lantern_station": _FIRST_BATTLE_CONFIG,
    "lamp_wick_store": _REPO_ROOT / "game_data/demo/wick_store_pressure_battle_config.json",
    "old_signal_tower": _REPO_ROOT / "game_data/demo/old_signal_tower_pressure_battle_config.json",
}

_RUNTIME_PACKAGE_BY_NODE = {
    "gray_lantern_station": _REPO_ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json",
    "lamp_wick_store": _REPO_ROOT / "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json",
    "old_signal_tower": _REPO_ROOT / "examples/runtime_packages/mvp_old_signal_tower.runtime_package.json",
}

_MAP_RUNTIME_PACKAGE_BY_NODE = {
    "gray_lantern_station": (
        _REPO_ROOT / "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"
    ),
    "lamp_wick_store": (
        _REPO_ROOT
        / "examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json"
    ),
    "old_signal_tower": (
        _REPO_ROOT
        / "examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json"
    ),
}


class FixtureNotFoundError(LookupError):
    """Raised when a mock fixture cannot satisfy the requested node."""


class InvalidQueueTransitionError(ValueError):
    """Raised when a scheduler queue transition violates the current state."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _new_generation_schedule_run_id() -> str:
    return f"gsrun_{secrets.token_urlsafe(12)}"


def _load_frontend_pack() -> dict[str, Any]:
    return _load_json(_FRONTEND_MOCK_PACK)


def _load_runtime_art_kit() -> dict[str, Any]:
    return _load_json(_FRONTEND_RUNTIME_ART_KIT)


def _load_media_manifest() -> dict[str, Any]:
    return _load_json(_MEDIA_MANIFEST)


def _load_animation_seed_manifest() -> dict[str, Any]:
    return _load_json(_ANIMATION_SEED_MANIFEST)


def _load_media_atlas_manifest() -> dict[str, Any]:
    return _load_json(_MEDIA_ATLAS_MANIFEST)


def _load_runtime_art_media_manifest() -> dict[str, Any]:
    return _load_json(_RUNTIME_ART_MEDIA_MANIFEST)


def _load_runtime_art_animation_seed_manifest() -> dict[str, Any]:
    return _load_json(_RUNTIME_ART_ANIMATION_SEED_MANIFEST)


def _load_runtime_art_atlas_manifest() -> dict[str, Any]:
    return _load_json(_RUNTIME_ART_ATLAS_MANIFEST)


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


def _generation_schedule_refs() -> dict[str, str]:
    return {
        "plan": _rel(_GENERATION_SCHEDULE_PLAN),
        "run_report": _rel(_GENERATION_SCHEDULE_RUN_REPORT),
    }


def _load_generation_schedule_plan() -> dict[str, Any]:
    return _load_json(_GENERATION_SCHEDULE_PLAN)


def _load_generation_schedule_run_report() -> dict[str, Any]:
    return _load_json(_GENERATION_SCHEDULE_RUN_REPORT)


def _build_generation_schedule_buffer(
    plan: dict[str, Any], run_report: dict[str, Any]
) -> dict[str, Any]:
    plan_items = [item for item in plan.get("items", []) if isinstance(item, dict)]
    report_items = [
        item for item in run_report.get("items", []) if isinstance(item, dict)
    ]
    report_by_item_id = {
        str(item.get("schedule_item_id")): item
        for item in report_items
        if item.get("schedule_item_id")
    }
    latency_counts = Counter(
        str(item.get("latency_class", "unknown")) for item in plan_items
    )
    result_counts = Counter(
        str(item.get("result_status", "unknown")) for item in report_items
    )
    provider_review_required_count = sum(
        1 for item in report_items if item.get("provider_review_required") is True
    )
    world_commit_candidate_count = sum(
        1
        for item in plan_items
        if isinstance(item.get("commit_policy"), dict)
        and item["commit_policy"].get("world_commit") not in (None, "none")
    )
    buffer_items = []
    for item in plan_items:
        item_id = str(item.get("schedule_item_id", ""))
        report_item = report_by_item_id.get(item_id, {})
        buffer_items.append(
            {
                "schedule_item_id": item_id,
                "object_kind": item.get("object_kind"),
                "object_ref": item.get("object_ref"),
                "latency_class": item.get("latency_class"),
                "plan_status": item.get("status"),
                "dry_run_action": report_item.get("action"),
                "dry_run_status": report_item.get("result_status"),
                "provider_review_required": (
                    report_item.get("provider_review_required") is True
                ),
                "player_visible": item.get("player_visible") is True,
                "fallback_ref": item.get("fallback_ref"),
                "revalidate_before_activation": (
                    isinstance(item.get("commit_policy"), dict)
                    and item["commit_policy"].get("revalidate_before_activation") is True
                ),
            }
        )
    summary = run_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "status": "fixture_backed_scheduler_buffer_ready",
        "control_plane_mode": "review_only_dry_run",
        "plan_id": plan.get("plan_id"),
        "report_id": run_report.get("report_id"),
        "item_count": len(plan_items),
        "latency_class_counts": dict(sorted(latency_counts.items())),
        "result_status_counts": dict(sorted(result_counts.items())),
        "ready_reused_count": int(summary.get("ready_reused_count", 0)),
        "fallback_selected_count": int(summary.get("fallback_selected_count", 0)),
        "scheduled_count": int(summary.get("scheduled_count", 0)),
        "provider_call_count": int(summary.get("provider_call_count", 0)),
        "world_mutation_count": int(summary.get("world_mutation_count", 0)),
        "provider_review_required_count": provider_review_required_count,
        "world_commit_candidate_count": world_commit_candidate_count,
        "activation_requires_revalidation": (
            isinstance(plan.get("authority"), dict)
            and plan["authority"].get("activation_requires_revalidation") is True
        ),
        "items": buffer_items,
    }


def _build_generation_schedule_payload(
    plan: dict[str, Any], run_report: dict[str, Any]
) -> dict[str, Any]:
    return {
        "refs": _generation_schedule_refs(),
        "buffer": _build_generation_schedule_buffer(plan, run_report),
        "plan": plan,
        "run_report": run_report,
    }


def _build_generation_schedule_run_payload(
    session_id: str, run_id: str, ts: str
) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    return {
        "run_id": run_id,
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "status": "completed",
        "scheduler_mode": "fixture_backed_dry_run",
        "created_at": ts,
        "updated_at": ts,
        "completed_at": ts,
        "generation_schedule": {
            "refs": _generation_schedule_refs(),
            "buffer": _build_generation_schedule_buffer(plan, run_report),
        },
        "execution_policy": run_report.get("execution_policy", {}),
        "source_report_summary": run_report.get("summary", {}),
        "notes": [
            "本次运行只复用已审 fixture、静态 fallback 与 dry-run 报告。",
            "本次运行不调用外部模型，不写入世界状态，不激活预生成候选。",
        ],
    }


def _generation_queue_status(item: dict[str, Any]) -> str:
    dry_run_status = item.get("dry_run_status")
    if dry_run_status == "passed":
        return "completed"
    if dry_run_status == "fallback":
        return "fallback_ready"
    if dry_run_status == "scheduled":
        return "queued"
    return "blocked"


def _build_generation_queue_item_payload(
    session_id: str, run_id: str, item: dict[str, Any], position: int, ts: str
) -> dict[str, Any]:
    status = _generation_queue_status(item)
    return {
        "queue_item_id": f"gq_{run_id}_{position:02d}",
        "run_id": run_id,
        "session_id": session_id,
        "schedule_item_id": item.get("schedule_item_id"),
        "object_kind": item.get("object_kind"),
        "object_ref": item.get("object_ref"),
        "latency_class": item.get("latency_class"),
        "status": status,
        "action": item.get("dry_run_action"),
        "dry_run_status": item.get("dry_run_status"),
        "provider_review_required": item.get("provider_review_required") is True,
        "player_visible": item.get("player_visible") is True,
        "fallback_ref": item.get("fallback_ref"),
        "revalidate_before_activation": item.get("revalidate_before_activation") is True,
        "created_at": ts,
        "updated_at": ts,
    }


def _build_generation_queue_items_from_run(
    run_payload: dict[str, Any], ts: str
) -> list[dict[str, Any]]:
    schedule = run_payload.get("generation_schedule", {})
    buffer = schedule.get("buffer", {}) if isinstance(schedule, dict) else {}
    items = buffer.get("items", []) if isinstance(buffer, dict) else []
    if not isinstance(items, list):
        return []
    return [
        _build_generation_queue_item_payload(
            str(run_payload["session_id"]),
            str(run_payload["run_id"]),
            item,
            position,
            ts,
        )
        for position, item in enumerate(items, start=1)
        if isinstance(item, dict)
    ]


def _insert_generation_queue_items(items: list[dict[str, Any]]) -> None:
    with db_cursor() as cur:
        for item in items:
            cur.execute(
                "INSERT INTO generation_schedule_queue_items "
                "(run_id, session_id, schedule_item_id, latency_class, status, action, "
                "payload, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["run_id"],
                    item["session_id"],
                    item["schedule_item_id"],
                    item["latency_class"],
                    item["status"],
                    item.get("action"),
                    _dump_payload(item),
                    item["created_at"],
                    item["updated_at"],
                ),
            )


def _load_latest_generation_schedule_run(session_id: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM generation_schedule_runs WHERE session_id = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if row is None or not row.get("payload"):
        return None
    return json.loads(row["payload"])


def _load_generation_queue_items(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    if run_id is None:
        latest = _load_latest_generation_schedule_run(session_id)
        if latest is None:
            return []
        run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? ORDER BY id ASC",
            (session_id, run_id),
        )
        rows = cur.fetchall()
    items = []
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if payload:
            items.append(json.loads(payload))
    return items


def _generation_queue_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    latency_counts = Counter(str(item.get("latency_class", "unknown")) for item in items)
    return {
        "item_count": len(items),
        "status_counts": dict(sorted(status_counts.items())),
        "latency_class_counts": dict(sorted(latency_counts.items())),
        "claimable_count": sum(1 for item in items if item.get("status") == "queued"),
        "completed_count": sum(1 for item in items if item.get("status") == "completed"),
        "fallback_ready_count": sum(
            1 for item in items if item.get("status") == "fallback_ready"
        ),
        "waiting_review_count": sum(
            1 for item in items if item.get("status") == "waiting_review"
        ),
        "failed_count": sum(1 for item in items if item.get("status") == "failed"),
        "provider_review_required_count": sum(
            1 for item in items if item.get("provider_review_required") is True
        ),
    }


def _compact_generation_schedule_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if run is None:
        return None
    schedule = run.get("generation_schedule", {})
    buffer = schedule.get("buffer", {}) if isinstance(schedule, dict) else {}
    return {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "scheduler_mode": run.get("scheduler_mode"),
        "created_at": run.get("created_at"),
        "completed_at": run.get("completed_at"),
        "provider_call_count": buffer.get("provider_call_count"),
        "world_mutation_count": buffer.get("world_mutation_count"),
        "scheduled_count": buffer.get("scheduled_count"),
        "fallback_selected_count": buffer.get("fallback_selected_count"),
    }


def _compact_generation_queue(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": _generation_queue_summary(items),
        "items": items,
    }


def _load_generation_queue_item_row(
    session_id: str, schedule_item_id: str
) -> dict[str, Any]:
    latest = _load_latest_generation_schedule_run(session_id)
    if latest is None:
        raise FixtureNotFoundError("generation_schedule_queue")
    run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, run_id, schedule_item_id, status, payload FROM "
            "generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? AND schedule_item_id = ?",
            (session_id, run_id, schedule_item_id),
        )
        row = cur.fetchone()
    if row is None or not row.get("payload"):
        raise FixtureNotFoundError(schedule_item_id)
    payload = json.loads(row["payload"])
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "schedule_item_id": row["schedule_item_id"],
        "status": row["status"],
        "payload": payload,
    }


def _next_generation_queue_status(current_status: str, transition: str) -> str:
    if transition == "claim":
        if current_status != "queued":
            raise InvalidQueueTransitionError(
                f"cannot claim scheduler item in status {current_status}"
            )
        return "claimed"
    if transition == "complete":
        if current_status not in ("queued", "claimed", "waiting_review"):
            raise InvalidQueueTransitionError(
                f"cannot complete scheduler item in status {current_status}"
            )
        return "completed"
    if transition == "fail":
        if current_status not in ("queued", "claimed", "waiting_review"):
            raise InvalidQueueTransitionError(
                f"cannot fail scheduler item in status {current_status}"
            )
        return "failed"
    raise InvalidQueueTransitionError(f"unknown scheduler queue transition {transition}")


def _transition_generation_queue_item(
    session_id: str,
    schedule_item_id: str,
    transition: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = _load_generation_queue_item_row(session_id, schedule_item_id)
    payload = row["payload"]
    current_status = str(row["status"])
    next_status = _next_generation_queue_status(current_status, transition)
    ts = now_iso()
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    transition_entry = {
        "transition": transition,
        "from_status": current_status,
        "to_status": next_status,
        "worker_id": safe_metadata.get("worker_id") or "frontend_mock_scheduler",
        "note": safe_metadata.get("note"),
        "created_at": ts,
    }
    transitions = payload.setdefault("transitions", [])
    if isinstance(transitions, list):
        transitions.append(transition_entry)
    payload["status"] = next_status
    payload["updated_at"] = ts
    if transition == "claim":
        payload["claimed_at"] = ts
        payload["claimed_by"] = transition_entry["worker_id"]
    elif transition == "complete":
        payload["completed_at"] = ts
    elif transition == "fail":
        payload["failed_at"] = ts
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET status = ?, payload = ?, updated_at = ? WHERE id = ?",
            (next_status, _dump_payload(payload), ts, row["id"]),
        )
    return payload


def _load_next_queued_generation_item_row(session_id: str) -> dict[str, Any] | None:
    latest = _load_latest_generation_schedule_run(session_id)
    if latest is None:
        return None
    run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, run_id, schedule_item_id, status, payload FROM "
            "generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? AND status = ? "
            "ORDER BY id ASC LIMIT 1",
            (session_id, run_id, "queued"),
        )
        row = cur.fetchone()
    if row is None or not row.get("payload"):
        return None
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "schedule_item_id": row["schedule_item_id"],
        "status": row["status"],
        "payload": json.loads(row["payload"]),
    }


def _run_generation_dry_worker_step(
    session_id: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    row = _load_next_queued_generation_item_row(session_id)
    if row is None:
        return None
    payload = row["payload"]
    current_status = str(row["status"])
    ts = now_iso()
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    worker_id = safe_metadata.get("worker_id") or "frontend_mock_dry_worker"
    requires_review = payload.get("provider_review_required") is True
    next_status = "waiting_review" if requires_review else "completed"
    transition_entry = {
        "transition": "dry_run_worker_step",
        "from_status": current_status,
        "to_status": next_status,
        "worker_id": worker_id,
        "note": safe_metadata.get("note"),
        "created_at": ts,
    }
    transitions = payload.setdefault("transitions", [])
    if isinstance(transitions, list):
        transitions.append(transition_entry)
    payload["status"] = next_status
    payload["updated_at"] = ts
    payload["worker_step_at"] = ts
    payload["worker_id"] = worker_id
    payload["provider_call_performed"] = False
    payload["world_mutation_performed"] = False
    if next_status == "waiting_review":
        payload["waiting_review_since"] = ts
        payload["review_reason"] = "provider_or_manual_review_required_before_activation"
    else:
        payload["completed_at"] = ts
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET status = ?, payload = ?, updated_at = ? WHERE id = ?",
            (next_status, _dump_payload(payload), ts, row["id"]),
        )
    return payload


def _runtime_art_payload() -> dict[str, Any]:
    return {
        "runtime_art_kit": _load_runtime_art_kit(),
        "runtime_art_media_manifest": _load_runtime_art_media_manifest(),
        "runtime_art_animation_seed_manifest": _load_runtime_art_animation_seed_manifest(),
        "runtime_art_atlas_manifest": _load_runtime_art_atlas_manifest(),
        "runtime_art_pipeline_status": (
            "developer_compiled_virtual_atlas_ready_video_frames_not_generated"
        ),
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
        "media_manifest": _load_media_manifest(),
        "animation_seed_manifest": _load_animation_seed_manifest(),
        "media_atlas_manifest": _load_media_atlas_manifest(),
        "animation_pipeline_status": "virtual_atlas_ready_video_frames_not_generated",
        **_runtime_art_payload(),
    }


def get_runtime_art_kit(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        **_runtime_art_payload(),
    }


def get_generation_schedule(session_id: str) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule": _build_generation_schedule_payload(plan, run_report),
        "latest_generation_schedule_run": _load_latest_generation_schedule_run(session_id),
    }


def create_generation_schedule_run(session_id: str) -> dict[str, Any]:
    run_id = _new_generation_schedule_run_id()
    ts = now_iso()
    payload = _build_generation_schedule_run_payload(session_id, run_id, ts)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO generation_schedule_runs "
            "(run_id, session_id, status, payload, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                payload["status"],
                _dump_payload(payload),
                ts,
                ts,
                ts,
            ),
        )
    queue_items = _build_generation_queue_items_from_run(payload, ts)
    _insert_generation_queue_items(queue_items)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": payload,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def get_latest_generation_schedule_run(session_id: str) -> dict[str, Any]:
    run = _load_latest_generation_schedule_run(session_id)
    queue_items = _load_generation_queue_items(session_id) if run is not None else []
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": run,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def get_generation_schedule_queue(session_id: str) -> dict[str, Any]:
    run = _load_latest_generation_schedule_run(session_id)
    queue_items = _load_generation_queue_items(session_id) if run is not None else []
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": _compact_generation_schedule_run(run),
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def transition_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    transition: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = _transition_generation_queue_item(
        session_id,
        schedule_item_id,
        transition,
        metadata,
    )
    queue_items = _load_generation_queue_items(session_id, str(item["run_id"]))
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_queue_item": item,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def run_generation_schedule_dry_worker_step(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = _run_generation_dry_worker_step(session_id, metadata)
    queue_items = _load_generation_queue_items(session_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "idle" if item is None else "processed",
            "worker_mode": "fixture_backed_dry_worker",
            "provider_call_count": 0,
            "world_mutation_count": 0,
        },
        "generation_schedule_queue_item": item,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
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
        "animation_seed_manifest": _load_animation_seed_manifest(),
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
    path = _BATTLE_CONFIG_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise FixtureNotFoundError(node_id)
    pack = _load_frontend_pack()
    config = _load_json(path)
    map_runtime_package = _load_map_runtime_package_optional(node_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "battle_config": config,
        "map_runtime_package": map_runtime_package,
        "toolbar_assets": _battle_toolbar_assets(pack),
        "sample_delivery_asset": _asset_for_sample_delivery(pack),
        "media_manifest": _load_media_manifest(),
        "animation_seed_manifest": _load_animation_seed_manifest(),
        "media_atlas_manifest": _load_media_atlas_manifest(),
        "animation_pipeline_status": "virtual_atlas_ready_video_frames_not_generated",
        **_runtime_art_payload(),
    }


def get_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    path = _RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise FixtureNotFoundError(node_id)
    pack = _load_frontend_pack()
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "runtime_package": _load_json(path),
        "map_runtime_package": _load_map_runtime_package_optional(node_id),
        "sample_delivery_asset": _asset_for_sample_delivery(pack),
        "media_manifest": _load_media_manifest(),
        "animation_seed_manifest": _load_animation_seed_manifest(),
        "media_atlas_manifest": _load_media_atlas_manifest(),
        "animation_pipeline_status": "virtual_atlas_ready_video_frames_not_generated",
        **_runtime_art_payload(),
    }


def _load_map_runtime_package(node_id: str) -> dict[str, Any]:
    path = _MAP_RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise FixtureNotFoundError(node_id)
    return _load_json(path)


def _load_map_runtime_package_optional(node_id: str) -> dict[str, Any] | None:
    path = _MAP_RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None or not path.exists():
        return None
    return _load_json(path)


def get_map_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "map_runtime_package": _load_map_runtime_package(node_id),
    }


def record_battle_result(
    session_id: str,
    node_id: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if node_id != "gray_lantern_station":
        raise FixtureNotFoundError(node_id)
    battle_config = _load_json(_FIRST_BATTLE_CONFIG)
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
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    latest_schedule_run = _load_latest_generation_schedule_run(session_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "studio_surface": "simple_evidence",
        "ai_compile_core_artifacts": {
            "status": "field_boundary_examples_ready",
            "refs": _core_artifact_refs(),
        },
        "generation_scheduler": {
            "refs": _generation_schedule_refs(),
            "buffer": _build_generation_schedule_buffer(plan, run_report),
            "latest_run": _compact_generation_schedule_run(latest_schedule_run),
            "latest_queue": _compact_generation_queue(
                _load_generation_queue_items(session_id)
                if latest_schedule_run is not None
                else []
            ),
        },
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
