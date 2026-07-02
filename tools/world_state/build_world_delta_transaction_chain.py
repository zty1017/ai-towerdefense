#!/usr/bin/env python3
"""Build the reviewed MVP WorldStateDeltaTransaction chain.

This helper is deterministic and offline. It replays the reviewed MVP
WorldStateDelta chain from the initial RunWorldState snapshot, writes the
per-stage after-state snapshots, and wraps each delta in a
WorldStateDeltaTransaction v0.1 artifact.

It never reads .env and never calls providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import load_json  # noqa: E402
from apply_world_delta import apply_delta  # noqa: E402
from validate_run_world_state import (  # noqa: E402
    validate_run_world_state,
    validate_with_jsonschema as validate_state_with_jsonschema,
)
from validate_world_delta import (  # noqa: E402
    validate_world_delta,
    validate_with_jsonschema as validate_delta_with_jsonschema,
)
from validate_world_delta_semantics import (  # noqa: E402
    DEFAULT_REVIEW_PACK,
    build_reference_registry,
    validate_world_delta_semantics,
)
from validate_world_delta_transaction import validate_transaction  # noqa: E402


CREATED_AT = "2026-07-02T00:00:00Z"
CONTEXT_PACKAGE_PATH = ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
INITIAL_STATE_PATH = ROOT / "examples/run_world_states/demo_initial.run_world_state.json"

STAGES = [
    {
        "stage": 1,
        "slug": "gray_lantern_first_defense",
        "delta": ROOT / "examples/world_deltas/stage_01_gray_lantern_first_defense.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_01_gray_lantern.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_01_gray_lantern_first_defense.world_delta_transaction.json",
    },
    {
        "stage": 2,
        "slug": "dawn_review_supply_line",
        "delta": ROOT / "examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_02_dawn_review.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_02_dawn_review_supply_line.world_delta_transaction.json",
    },
    {
        "stage": 3,
        "slug": "northern_road_scouting",
        "delta": ROOT / "examples/world_deltas/stage_03_northern_road_scouting.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_03_northern_road.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_03_northern_road_scouting.world_delta_transaction.json",
    },
    {
        "stage": 4,
        "slug": "wick_store_pressure_battle",
        "delta": ROOT / "examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_04_wick_store_pressure_battle.world_delta_transaction.json",
    },
    {
        "stage": 5,
        "slug": "old_signal_tower_pressure",
        "delta": ROOT / "examples/world_deltas/stage_05_old_signal_tower_pressure.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_05_old_signal_tower.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_05_old_signal_tower_pressure.world_delta_transaction.json",
    },
    {
        "stage": 6,
        "slug": "signal_resonance_trial",
        "delta": ROOT / "examples/world_deltas/stage_06_signal_resonance_trial.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_06_signal_resonance.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_06_signal_resonance_trial.world_delta_transaction.json",
    },
    {
        "stage": 7,
        "slug": "split_tide_containment",
        "delta": ROOT / "examples/world_deltas/stage_07_split_tide_containment.world_delta.json",
        "after_state": ROOT
        / "examples/run_world_states/demo_after_stage_07_split_tide.run_world_state.json",
        "transaction": ROOT
        / "examples/world_delta_transactions/stage_07_split_tide_containment.world_delta_transaction.json",
    },
]

EFFECT_KIND_BY_OP = {
    "append_event": "event_append",
    "set_map_node_state": "map_node_patch",
    "adjust_resource": "resource_delta",
    "adjust_global_state": "global_state_delta",
    "update_npc_relationship": "npc_relationship_delta",
    "unlock_fact": "fact_unlock",
    "add_temporary_sample": "sample_registration",
    "set_flag": "flag_set",
    "upsert_task": "task_upsert",
    "set_task_status": "task_upsert",
    "schedule_random_event": "random_event_schedule",
    "set_random_event_status": "random_event_schedule",
    "upsert_research_job": "research_job_upsert",
    "unlock_blueprint": "blueprint_unlock",
    "introduce_npc": "npc_introduction",
    "introduce_map_node": "map_node_introduction",
    "set_progress_phase": "phase_change",
}

SCOPE_KIND_BY_SOURCE = {
    "battle_result": "battle_result_commit",
    "research_job": "research_commit",
    "narrative_event": "narrative_stage_commit",
    "system": "system_commit",
}


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def full_state_validation(state: dict[str, Any]) -> list[str]:
    return dedupe([*validate_state_with_jsonschema(state), *validate_run_world_state(state)])


def full_delta_validation(delta: dict[str, Any]) -> list[str]:
    return dedupe([*validate_delta_with_jsonschema(delta), *validate_world_delta(delta)])


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def append_ref(refs: list[str], prefix: str, value: Any) -> None:
    if isinstance(value, str) and value:
        refs.append(f"{prefix}:{value}")


def append_node_id(node_ids: list[str], value: Any) -> None:
    if isinstance(value, str) and value:
        node_ids.append(value)


def target_ref_for_operation(operation: dict[str, Any]) -> str:
    op = operation.get("op")
    if op == "append_event":
        return f"events.{as_obj(operation.get('event')).get('event_id')}"
    if op == "set_map_node_state":
        return f"map_nodes.{operation.get('node_id')}"
    if op == "introduce_map_node":
        return f"map_nodes.{as_obj(operation.get('node')).get('node_id')}"
    if op == "adjust_resource":
        return f"resources.{operation.get('resource_id')}"
    if op == "adjust_global_state":
        return f"global_state.{operation.get('field')}"
    if op == "update_npc_relationship":
        return f"npcs.{operation.get('npc_id')}.relationship"
    if op == "introduce_npc":
        return f"npcs.{as_obj(operation.get('npc')).get('npc_id')}"
    if op == "unlock_fact":
        return f"facts.{as_obj(operation.get('fact')).get('fact_id')}"
    if op == "add_temporary_sample":
        return f"research.temporary_samples.{as_obj(operation.get('sample')).get('sample_id')}"
    if op == "set_flag":
        return f"flags.{operation.get('flag')}"
    if op == "upsert_task":
        return f"tasks.{as_obj(operation.get('task')).get('task_id')}"
    if op == "set_task_status":
        return f"tasks.{operation.get('task_id')}"
    if op == "schedule_random_event":
        return f"random_events.{as_obj(operation.get('random_event')).get('random_event_id')}"
    if op == "set_random_event_status":
        return f"random_events.{operation.get('random_event_id')}"
    if op == "upsert_research_job":
        return f"research.jobs.{as_obj(operation.get('job')).get('job_id')}"
    if op == "unlock_blueprint":
        return f"research.blueprints.{as_obj(operation.get('blueprint')).get('blueprint_id')}"
    if op == "set_progress_phase":
        return "progress_phase"
    return f"operations.{op or 'unknown'}"


def collect_scope(delta: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    node_ids: list[str] = []
    object_refs: list[str] = []
    state_fields: list[str] = []
    for operation in delta.get("operations", []):
        if not isinstance(operation, dict):
            continue
        op = operation.get("op")
        target = target_ref_for_operation(operation)
        state_fields.append(target)

        append_node_id(node_ids, operation.get("node_id"))
        node = as_obj(operation.get("node"))
        append_node_id(node_ids, node.get("node_id"))
        task = as_obj(operation.get("task"))
        append_node_id(node_ids, task.get("node_id"))
        random_event = as_obj(operation.get("random_event"))
        append_node_id(node_ids, random_event.get("node_id"))
        job = as_obj(operation.get("job"))
        append_node_id(node_ids, job.get("node_id"))
        npc = as_obj(operation.get("npc"))
        append_node_id(node_ids, npc.get("location_node_id"))

        append_ref(object_refs, "event", as_obj(operation.get("event")).get("event_id"))
        append_ref(object_refs, "map_node", operation.get("node_id"))
        append_ref(object_refs, "map_node", node.get("node_id"))
        append_ref(object_refs, "resource", operation.get("resource_id"))
        append_ref(object_refs, "npc", operation.get("npc_id"))
        append_ref(object_refs, "npc", npc.get("npc_id"))
        append_ref(object_refs, "fact", as_obj(operation.get("fact")).get("fact_id"))
        append_ref(object_refs, "sample", as_obj(operation.get("sample")).get("sample_id"))
        append_ref(object_refs, "flag", operation.get("flag"))
        append_ref(object_refs, "task", task.get("task_id"))
        append_ref(object_refs, "task", operation.get("task_id"))
        append_ref(object_refs, "random_event", random_event.get("random_event_id"))
        append_ref(object_refs, "random_event", operation.get("random_event_id"))
        append_ref(object_refs, "research_job", job.get("job_id"))
        append_ref(object_refs, "blueprint", as_obj(operation.get("blueprint")).get("blueprint_id"))

        if op == "set_progress_phase":
            append_ref(object_refs, "phase", operation.get("phase"))
    return dedupe(node_ids), dedupe(object_refs), dedupe(state_fields)


def build_operation_mapping(delta: dict[str, Any]) -> list[dict[str, Any]]:
    mapping: list[dict[str, Any]] = []
    for index, operation in enumerate(delta.get("operations", [])):
        if not isinstance(operation, dict):
            continue
        op = str(operation.get("op") or "unknown")
        mapping.append(
            {
                "operation_index": index,
                "op": op,
                "target_ref": target_ref_for_operation(operation),
                "effect_kind": EFFECT_KIND_BY_OP[op],
                "summary": f"将 {op} 提交到受控运行态字段。",
            }
        )
    return mapping


def build_preconditions(
    *,
    stage_index: int,
    before_state_path: Path,
    delta: dict[str, Any],
    source_artifact_path: Path,
    state_fields: list[str],
) -> list[dict[str, str]]:
    preconditions = [
        {
            "kind": "run_state_version",
            "ref": f"{delta.get('run_id')}:before_stage_{stage_index:02d}",
            "summary": f"提交前使用 {rel(before_state_path)} 快照。",
        },
        {
            "kind": "artifact_available",
            "ref": rel(source_artifact_path),
            "summary": "来源产物已经生成并通过白名单 delta gate。",
        },
    ]
    node_ref = next((field for field in state_fields if field.startswith("map_nodes.")), None)
    if node_ref:
        preconditions.append(
            {
                "kind": "node_state",
                "ref": node_ref,
                "summary": "相关地图节点存在于提交前运行态或本次受控引入范围。",
            }
        )
    return preconditions


def build_transaction(
    *,
    stage_config: dict[str, Any],
    before_state_path: Path,
    after_state_path: Path,
    delta: dict[str, Any],
) -> dict[str, Any]:
    stage_index = int(stage_config["stage"])
    delta_path = Path(stage_config["delta"])
    source = str(delta["source"])
    node_ids, object_refs, state_fields = collect_scope(delta)
    mapping = build_operation_mapping(delta)
    source_artifact_path = delta_path
    return {
        "schema_version": "world_state_delta_transaction.v0.1",
        "transaction_id": f"tx_stage_{stage_index:02d}_{stage_config['slug']}_001",
        "run_id": delta["run_id"],
        "worldbook_id": delta["worldbook_id"],
        "actor": "system",
        "source": source,
        "created_turn": delta["created_turn"],
        "created_at": CREATED_AT,
        "base_world_version": f"{delta['run_id']}:before_stage_{stage_index:02d}",
        "idempotency_key": f"{delta['run_id']}:{delta['delta_id']}",
        "scope": {
            "kind": SCOPE_KIND_BY_SOURCE[source],
            "node_ids": node_ids,
            "object_refs": object_refs,
            "state_fields": state_fields,
        },
        "source_refs": {
            "context_package_path": rel(CONTEXT_PACKAGE_PATH),
            "battle_result_path": rel(source_artifact_path),
            "run_state_before_path": rel(before_state_path),
            "run_state_after_path": rel(after_state_path),
        },
        "world_state_delta_ref": {
            "path": rel(delta_path),
            "schema_version": delta["schema_version"],
            "delta_id": delta["delta_id"],
            "sha256": sha256_file(delta_path),
        },
        "preconditions": build_preconditions(
            stage_index=stage_index,
            before_state_path=before_state_path,
            delta=delta,
            source_artifact_path=source_artifact_path,
            state_fields=state_fields,
        ),
        "operation_effects_mapping": mapping,
        "conflict_policy": {
            "mode": "reject_on_conflict",
            "conflict_keys": state_fields,
        },
        "rollback_policy": {
            "mode": "required_snapshot",
            "inverse_operations_required": False,
            "notes": "v0.1 事务壳依赖提交前 RunWorldState 快照回滚，不生成通用逆向操作 DSL。",
        },
        "validation_report": {
            "gate_status": "passed",
            "world_delta_structure": "passed",
            "world_delta_semantics": "passed",
            "operation_mapping": "passed",
            "runtime_apply_checked": True,
            "warnings": [
                "source_refs.battle_result_path 是 v0.1 兼容字段；非战斗来源时指向对应来源 delta 产物。"
            ]
            if source != "battle_result"
            else [],
        },
        "status": "committed",
    }


def validate_stage(
    *,
    stage_config: dict[str, Any],
    before_state: dict[str, Any],
    delta: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    errors.extend(full_state_validation(before_state))
    errors.extend(full_delta_validation(delta))
    registry = build_reference_registry(before_state, DEFAULT_REVIEW_PACK)
    errors.extend(validate_world_delta_semantics(delta, before_state, registry))
    if errors:
        return [f"stage {stage_config['stage']}: {error}" for error in dedupe(errors)]
    return []


def build_chain(*, validate: bool) -> tuple[list[Path], list[str]]:
    errors: list[str] = []
    written: list[Path] = []
    state = load_json(INITIAL_STATE_PATH)
    if not isinstance(state, dict):
        return [], ["initial state root must be an object"]

    before_state_path = INITIAL_STATE_PATH
    for stage_config in STAGES:
        delta_path = Path(stage_config["delta"])
        after_state_path = Path(stage_config["after_state"])
        transaction_path = Path(stage_config["transaction"])
        delta = load_json(delta_path)
        if not isinstance(delta, dict):
            return written, [f"{rel(delta_path)} root must be an object"]

        errors.extend(validate_stage(stage_config=stage_config, before_state=state, delta=delta))
        if errors:
            return written, errors

        next_state, apply_errors = apply_delta(state, delta)
        if apply_errors:
            return written, [f"stage {stage_config['stage']}: {error}" for error in apply_errors]
        next_state_errors = full_state_validation(next_state)
        if next_state_errors:
            return written, [
                f"stage {stage_config['stage']}: output state invalid: {error}"
                for error in next_state_errors
            ]

        write_json(after_state_path, next_state)
        written.append(after_state_path)

        transaction = build_transaction(
            stage_config=stage_config,
            before_state_path=before_state_path,
            after_state_path=after_state_path,
            delta=delta,
        )
        write_json(transaction_path, transaction)
        written.append(transaction_path)

        if validate:
            transaction_errors = validate_transaction(transaction)
            if transaction_errors:
                return written, [
                    f"{rel(transaction_path)}: {error}" for error in transaction_errors
                ]

        state = next_state
        before_state_path = after_state_path

    return written, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build reviewed MVP WorldStateDeltaTransaction chain."
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate each generated transaction after writing it.",
    )
    args = parser.parse_args()

    written, errors = build_chain(validate=args.validate)
    if errors:
        print("INVALID WorldStateDeltaTransaction chain")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: built {len(STAGES)} WorldStateDeltaTransaction artifacts")
    for path in written:
        print(f"- {rel(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
