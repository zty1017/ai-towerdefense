#!/usr/bin/env python3
"""Validate the narrative-to-gameplay contract for the MVP review pack.

This is a cross-file gate. It checks that staged NarrativeEventBundle files do
not merely describe story, but resolve into WorldStateDelta operations and into
gameplay objects visible in the final RunWorldState snapshot.

The validator never reads .env and never calls a real provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
CONTENT_PIPELINE_DIR = ROOT / "tools" / "content_pipeline"
WORLD_STATE_DIR = ROOT / "tools" / "world_state"
for path in (ASSET_GRAPH_DIR, CONTENT_PIPELINE_DIR, WORLD_STATE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validation_common import load_json  # noqa: E402
from validate_mvp_story_asset_review_pack import validate_review_pack  # noqa: E402
from validate_narrative_bundle import validate_narrative_bundle  # noqa: E402
from validate_run_world_state import (  # noqa: E402
    validate_run_world_state,
    validate_with_jsonschema as validate_state_with_jsonschema,
)
from validate_world_delta import (  # noqa: E402
    validate_world_delta,
    validate_with_jsonschema as validate_delta_with_jsonschema,
)

DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_WORLD_DELTA_DIR = ROOT / "examples/world_deltas"
DEFAULT_FINAL_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"

GAMEPLAY_OBJECT_OPS = frozenset(
    {
        "introduce_map_node",
        "introduce_npc",
        "adjust_resource",
        "add_temporary_sample",
        "upsert_task",
        "set_task_status",
        "schedule_random_event",
        "set_random_event_status",
        "upsert_research_job",
        "unlock_blueprint",
        "set_map_node_state",
        "set_flag",
        "unlock_fact",
        "adjust_global_state",
    }
)

HOOK_REQUIRED_OPS: dict[str, frozenset[str]] = {
    "unlock_battle_node": frozenset({"set_map_node_state", "introduce_map_node", "upsert_task"}),
    "modify_map_node_state": frozenset({"set_map_node_state", "introduce_map_node"}),
    "open_resource_route": frozenset({"introduce_map_node", "set_map_node_state", "upsert_task"}),
    "advance_main_pressure": frozenset(
        {"adjust_global_state", "set_map_node_state", "schedule_random_event", "append_event"}
    ),
    "increase_threat": frozenset(
        {"adjust_global_state", "set_map_node_state", "schedule_random_event", "append_event"}
    ),
    "teach_mechanic": frozenset({"unlock_fact", "append_event", "set_flag"}),
    "explain_battle_result": frozenset({"append_event", "unlock_fact", "set_flag"}),
    "reward_player_choice": frozenset(
        {"add_temporary_sample", "adjust_resource", "unlock_blueprint", "set_flag", "append_event"}
    ),
    "create_research_need": frozenset(
        {"upsert_research_job", "add_temporary_sample", "unlock_fact", "upsert_task"}
    ),
    "offer_workshop_hook": frozenset(
        {"upsert_research_job", "add_temporary_sample", "unlock_fact", "upsert_task"}
    ),
    "introduce_material": frozenset({"adjust_resource", "unlock_fact"}),
    "introduce_functional_npc": frozenset({"introduce_npc", "update_npc_relationship", "upsert_task"}),
    "introduce_generic_npc": frozenset({"introduce_npc", "update_npc_relationship", "upsert_task"}),
    "create_quest_hook": frozenset({"upsert_task", "unlock_fact", "append_event"}),
    "trigger_random_event": frozenset({"schedule_random_event", "set_random_event_status"}),
}


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _repo_path(path_ref: str | Path) -> Path:
    path = Path(path_ref)
    return path if path.is_absolute() else ROOT / path


def _collect_strings(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key:
                out.add(key)
            out.update(_collect_strings(child))
    elif isinstance(value, list):
        for child in value:
            out.update(_collect_strings(child))
    elif isinstance(value, str) and value:
        out.add(value)
    return out


def _collect_support_file_strings(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"fixture", "source_file"} and isinstance(child, str):
                target = _repo_path(child)
                if target.is_file() and target.suffix == ".json":
                    try:
                        out.update(_collect_strings(load_json(target)))
                    except Exception:
                        pass
            out.update(_collect_support_file_strings(child))
    elif isinstance(value, list):
        for child in value:
            out.update(_collect_support_file_strings(child))
    return out


def _full_delta_validation(delta: dict[str, Any]) -> list[str]:
    return _dedupe([*validate_delta_with_jsonschema(delta), *validate_world_delta(delta)])


def _full_state_validation(state: dict[str, Any]) -> list[str]:
    return _dedupe([*validate_state_with_jsonschema(state), *validate_run_world_state(state)])


def _index_world_deltas(delta_dir: Path) -> tuple[dict[str, tuple[Path, dict[str, Any]]], list[str]]:
    errors: list[str] = []
    index: dict[str, tuple[Path, dict[str, Any]]] = {}
    if not delta_dir.is_dir():
        return index, [f"world delta dir not found: {delta_dir}"]

    for path in sorted(delta_dir.glob("*.world_delta.json")):
        try:
            delta = load_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        except Exception as exc:
            errors.append(f"{path}: cannot load: {exc}")
            continue
        if not isinstance(delta, dict):
            errors.append(f"{path}: delta root must be an object")
            continue
        delta_id = delta.get("delta_id")
        if not isinstance(delta_id, str) or not delta_id:
            continue
        if delta_id in index:
            errors.append(f"duplicate delta_id {delta_id!r}: {index[delta_id][0]} and {path}")
            continue
        index[delta_id] = (path, delta)
    return index, errors


def _final_state_ids(state: dict[str, Any]) -> dict[str, set[str]]:
    research = state.get("research", {}) if isinstance(state.get("research"), dict) else {}
    flags = state.get("flags", {}) if isinstance(state.get("flags"), dict) else {}
    return {
        "map_node": {
            item.get("node_id")
            for item in state.get("map_nodes", []) or []
            if isinstance(item, dict) and isinstance(item.get("node_id"), str)
        },
        "npc": {
            item.get("npc_id")
            for item in state.get("npcs", []) or []
            if isinstance(item, dict) and isinstance(item.get("npc_id"), str)
        },
        "resource": {
            item.get("resource_id")
            for item in state.get("resources", []) or []
            if isinstance(item, dict) and isinstance(item.get("resource_id"), str)
        },
        "fact": {
            item.get("fact_id")
            for item in state.get("unlocked_facts", []) or []
            if isinstance(item, dict) and isinstance(item.get("fact_id"), str)
        },
        "event": {
            item.get("event_id")
            for item in state.get("event_log", []) or []
            if isinstance(item, dict) and isinstance(item.get("event_id"), str)
        },
        "sample": {
            item.get("sample_id")
            for item in research.get("temporary_samples", []) or []
            if isinstance(item, dict) and isinstance(item.get("sample_id"), str)
        },
        "task": {
            item.get("task_id")
            for item in state.get("tasks", []) or []
            if isinstance(item, dict) and isinstance(item.get("task_id"), str)
        },
        "random_event": {
            item.get("random_event_id")
            for item in state.get("random_events", []) or []
            if isinstance(item, dict) and isinstance(item.get("random_event_id"), str)
        },
        "research_job": {
            item.get("job_id")
            for item in research.get("active_jobs", []) or []
            if isinstance(item, dict) and isinstance(item.get("job_id"), str)
        },
        "blueprint": {
            item.get("blueprint_id")
            for item in research.get("known_blueprints", []) or []
            if isinstance(item, dict) and isinstance(item.get("blueprint_id"), str)
        },
        "flag": {key for key in flags if isinstance(key, str)},
    }


def _validate_delta_final_state_projection(
    *,
    delta: dict[str, Any],
    delta_path: Path,
    ids: dict[str, set[str]],
    errors: list[str],
) -> None:
    for index, op in enumerate(delta.get("operations", []) or []):
        if not isinstance(op, dict):
            continue
        op_name = op.get("op")
        path = f"{delta_path}: operations[{index}]"
        if op_name == "introduce_map_node" and isinstance(op.get("node"), dict):
            node_id = op["node"].get("node_id")
            if node_id not in ids["map_node"]:
                errors.append(f"{path}.node.node_id={node_id!r} is not in final map_nodes")
        elif op_name == "introduce_npc" and isinstance(op.get("npc"), dict):
            npc_id = op["npc"].get("npc_id")
            if npc_id not in ids["npc"]:
                errors.append(f"{path}.npc.npc_id={npc_id!r} is not in final npcs")
        elif op_name == "adjust_resource":
            resource_id = op.get("resource_id")
            if resource_id not in ids["resource"]:
                errors.append(f"{path}.resource_id={resource_id!r} is not in final resources")
        elif op_name == "unlock_fact" and isinstance(op.get("fact"), dict):
            fact_id = op["fact"].get("fact_id")
            if fact_id not in ids["fact"]:
                errors.append(f"{path}.fact.fact_id={fact_id!r} is not in final facts")
        elif op_name == "append_event" and isinstance(op.get("event"), dict):
            event_id = op["event"].get("event_id")
            if event_id not in ids["event"]:
                errors.append(f"{path}.event.event_id={event_id!r} is not in final event_log")
        elif op_name == "add_temporary_sample" and isinstance(op.get("sample"), dict):
            sample_id = op["sample"].get("sample_id")
            if sample_id not in ids["sample"]:
                errors.append(f"{path}.sample.sample_id={sample_id!r} is not in final samples")
        elif op_name == "upsert_task" and isinstance(op.get("task"), dict):
            task_id = op["task"].get("task_id")
            if task_id not in ids["task"]:
                errors.append(f"{path}.task.task_id={task_id!r} is not in final tasks")
        elif op_name == "schedule_random_event" and isinstance(op.get("random_event"), dict):
            event_id = op["random_event"].get("random_event_id")
            if event_id not in ids["random_event"]:
                errors.append(
                    f"{path}.random_event.random_event_id={event_id!r} is not in final random_events"
                )
        elif op_name == "upsert_research_job" and isinstance(op.get("job"), dict):
            job_id = op["job"].get("job_id")
            if job_id not in ids["research_job"]:
                errors.append(f"{path}.job.job_id={job_id!r} is not in final research jobs")
        elif op_name == "unlock_blueprint" and isinstance(op.get("blueprint"), dict):
            blueprint_id = op["blueprint"].get("blueprint_id")
            if blueprint_id not in ids["blueprint"]:
                errors.append(
                    f"{path}.blueprint.blueprint_id={blueprint_id!r} is not in final blueprints"
                )
        elif op_name == "set_flag":
            flag = op.get("flag")
            if flag not in ids["flag"]:
                errors.append(f"{path}.flag={flag!r} is not in final flags")


def validate_contract(
    *,
    review_pack_path: Path,
    world_delta_dir: Path,
    final_state_path: Path,
) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    stats: Counter[str] = Counter()

    try:
        pack = load_json(review_pack_path)
    except Exception as exc:
        return [f"cannot load review pack {review_pack_path}: {exc}"], [], {}
    if not isinstance(pack, dict):
        return ["review pack root must be an object"], [], {}

    errors.extend(f"review_pack: {error}" for error in validate_review_pack(pack))

    delta_index, delta_index_errors = _index_world_deltas(world_delta_dir)
    errors.extend(delta_index_errors)

    try:
        final_state = load_json(final_state_path)
    except Exception as exc:
        return [*errors, f"cannot load final state {final_state_path}: {exc}"], warnings, {}
    if not isinstance(final_state, dict):
        errors.append("final state root must be an object")
        return errors, warnings, {}
    errors.extend(f"final_state: {error}" for error in _full_state_validation(final_state))
    final_ids = _final_state_ids(final_state)
    final_strings = _collect_strings(final_state)

    referenced_delta_ids: set[str] = set()
    validated_delta_ids: set[str] = set()
    stage_count = 0
    node_count = 0
    gameplay_object_op_count = 0

    for stage_index, stage in enumerate(pack.get("stages", []) or []):
        if not isinstance(stage, dict):
            continue
        stage_count += 1
        stage_path = f"stages[{stage_index}]"
        stage_id = str(stage.get("stage_id") or "")
        stage_strings = _collect_strings(stage) | _collect_support_file_strings(stage)
        bundle_file = stage.get("bundle_file")
        if not isinstance(bundle_file, str) or not bundle_file:
            continue
        bundle_path = _repo_path(bundle_file)
        try:
            bundle = load_json(bundle_path)
        except Exception as exc:
            errors.append(f"{stage_path}.bundle_file cannot be loaded: {exc}")
            continue
        if not isinstance(bundle, dict):
            errors.append(f"{stage_path}.bundle_file root must be an object")
            continue
        bundle_errors = validate_narrative_bundle(bundle)
        errors.extend(f"{stage_path}.bundle_file: {error}" for error in bundle_errors)

        for node_index, node in enumerate(bundle.get("nodes", []) or []):
            if not isinstance(node, dict):
                continue
            node_count += 1
            node_path = f"{stage_path}.bundle.nodes[{node_index}]"
            if node.get("stage") != stage_id:
                errors.append(
                    f"{node_path}.stage={node.get('stage')!r} does not match stage_id={stage_id!r}"
                )
            delta_id = node.get("proposed_world_delta_ref")
            if not isinstance(delta_id, str) or not delta_id:
                errors.append(f"{node_path}.proposed_world_delta_ref must be non-empty")
                continue
            referenced_delta_ids.add(delta_id)
            indexed = delta_index.get(delta_id)
            if not indexed:
                errors.append(f"{node_path}.proposed_world_delta_ref={delta_id!r} has no delta file")
                continue
            delta_path, delta = indexed
            delta_ops = {
                op.get("op")
                for op in delta.get("operations", []) or []
                if isinstance(op, dict) and isinstance(op.get("op"), str)
            }
            gameplay_ops = delta_ops & GAMEPLAY_OBJECT_OPS
            if not gameplay_ops:
                errors.append(
                    f"{node_path} delta {delta_id!r} has no gameplay object/state operations"
                )
            if delta_id not in validated_delta_ids:
                validated_delta_ids.add(delta_id)
                errors.extend(
                    f"{delta_path}: {error}" for error in _full_delta_validation(delta)
                )
                gameplay_object_op_count += sum(
                    1
                    for op in delta.get("operations", []) or []
                    if isinstance(op, dict) and op.get("op") in GAMEPLAY_OBJECT_OPS
                )
                _validate_delta_final_state_projection(
                    delta=delta,
                    delta_path=delta_path,
                    ids=final_ids,
                    errors=errors,
                )

            expected_ops = node.get("proposed_delta_summary", {}).get("expected_operations", [])
            if isinstance(expected_ops, list):
                missing = sorted(
                    str(op)
                    for op in expected_ops
                    if isinstance(op, str) and op not in delta_ops
                )
                if missing and not (set(expected_ops) & delta_ops):
                    errors.append(
                        f"{node_path}.proposed_delta_summary.expected_operations have no overlap "
                        f"with actual delta ops in {delta_id!r}: missing {missing}"
                    )
                elif missing:
                    warnings.append(
                        f"{node_path}: expected ops not directly present in {delta_id!r}: {missing}"
                    )

            delta_strings = _collect_strings(delta)
            for hook_index, hook in enumerate(node.get("gameplay_hooks", []) or []):
                if not isinstance(hook, dict):
                    continue
                hook_name = hook.get("hook")
                target_ref = hook.get("target_ref")
                required_ops = HOOK_REQUIRED_OPS.get(str(hook_name))
                if not required_ops:
                    errors.append(f"{node_path}.gameplay_hooks[{hook_index}].hook={hook_name!r} unknown")
                    continue
                if not (required_ops & delta_ops):
                    errors.append(
                        f"{node_path}.gameplay_hooks[{hook_index}] hook {hook_name!r} "
                        f"requires one of {sorted(required_ops)}, but delta {delta_id!r} "
                        f"has ops {sorted(delta_ops)}"
                    )
                if isinstance(target_ref, str) and target_ref:
                    if (
                        target_ref not in delta_strings
                        and target_ref not in final_strings
                        and target_ref not in stage_strings
                    ):
                        warnings.append(
                            f"{node_path}.gameplay_hooks[{hook_index}].target_ref={target_ref!r} "
                            "is not directly present in the delta, final state, or stage review refs"
                        )

    if stage_count == 0:
        errors.append("review pack has no stages")
    if node_count == 0:
        errors.append("review pack has no narrative nodes")
    if not referenced_delta_ids:
        errors.append("no narrative node references a WorldStateDelta")

    stats.update(
        {
            "stages": stage_count,
            "narrative_nodes": node_count,
            "referenced_world_deltas": len(referenced_delta_ids),
            "validated_world_deltas": len(validated_delta_ids),
            "gameplay_object_ops": gameplay_object_op_count,
            "warnings": len(warnings),
        }
    )
    return _dedupe(errors), _dedupe(warnings), dict(stats)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate NarrativeEventBundle -> WorldStateDelta -> RunWorldState gameplay contract."
    )
    parser.add_argument("review_pack", nargs="?", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--world-delta-dir", default=str(DEFAULT_WORLD_DELTA_DIR))
    parser.add_argument("--final-state", default=str(DEFAULT_FINAL_STATE))
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Fail when soft contract warnings are present.",
    )
    args = parser.parse_args()

    errors, warnings, stats = validate_contract(
        review_pack_path=Path(args.review_pack),
        world_delta_dir=Path(args.world_delta_dir),
        final_state_path=Path(args.final_state),
    )
    if args.warnings_as_errors:
        errors.extend(f"warning escalated to error: {warning}" for warning in warnings)

    if errors:
        print("INVALID NarrativeGameplayContract")
        for error in errors:
            print(f"- {error}")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 1

    print("OK NarrativeGameplayContract")
    for key in (
        "stages",
        "narrative_nodes",
        "referenced_world_deltas",
        "validated_world_deltas",
        "gameplay_object_ops",
        "warnings",
    ):
        print(f"- {key}: {stats.get(key, 0)}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
