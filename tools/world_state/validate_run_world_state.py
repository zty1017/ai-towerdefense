#!/usr/bin/env python3
"""Validate a RunWorldState v0.1 JSON file.

Checks:
- JSON parses.
- schema_version == "run_world_state.v0.1".
- Top-level required fields present; unknown top-level fields rejected.
- Key field types correct (mirrors run_world_state.v0.1.schema.json with
  additionalProperties:false on each layer).
- jsonschema validation when jsonschema is available (preferred).
- Pure-Python fallback otherwise.
- Recursive forbidden-field scan (provider/model/raw_prompt/full_trace/
  raw_json/api_key/secret/unreviewed_content).

The validator never reads .env and never prints API keys or secrets.

Usage:
    python3 tools/world_state/validate_run_world_state.py <state_path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import (  # noqa: E402  (import after sys.path bootstrap)
    get_jsonschema_validator,
    load_json,
    scan_forbidden_fields,
)

SCHEMA_PATH = ROOT / "shared/schemas/run_world_state.v0.1.schema.json"

# Allowed top-level keys mirror shared/schemas/run_world_state.v0.1.schema.json.
# `tasks` and `random_events` are optional because older MVP snapshots predate
# explicit gameplay-object compilation and must remain valid.
TOP_LEVEL_REQUIRED: frozenset[str] = frozenset(
    {
        "schema_version",
        "run_id",
        "worldbook_id",
        "progress",
        "global_state",
        "resources",
        "map_nodes",
        "npcs",
        "unlocked_facts",
        "event_log",
        "research",
        "flags",
    }
)
TOP_LEVEL_ALLOWED: frozenset[str] = TOP_LEVEL_REQUIRED | frozenset(
    {"tasks", "random_events"}
)
PROGRESS_ALLOWED: frozenset[str] = frozenset({"chapter", "turn", "phase"})
GLOBAL_STATE_ALLOWED: frozenset[str] = frozenset({"pressure", "hope", "visibility"})
RESOURCE_ALLOWED: frozenset[str] = frozenset({"resource_id", "amount"})
MAP_NODE_ALLOWED: frozenset[str] = frozenset(
    {"node_id", "status", "threat_level", "visibility", "available_actions"}
)
NPC_ALLOWED: frozenset[str] = frozenset(
    {
        "npc_id",
        "location_node_id",
        "narrative_roles",
        "gameplay_roles",
        "relationship",
        "availability",
    }
)
NPC_RELATIONSHIP_ALLOWED: frozenset[str] = frozenset({"trust"})
FACT_ALLOWED: frozenset[str] = frozenset({"fact_id", "source", "visibility", "summary"})
EVENT_ALLOWED: frozenset[str] = frozenset({"event_id", "turn", "kind", "summary"})
RESEARCH_ALLOWED: frozenset[str] = frozenset(
    {"active_jobs", "known_blueprints", "temporary_samples"}
)
ACTIVE_JOB_ALLOWED: frozenset[str] = frozenset(
    {
        "job_id",
        "status",
        "started_turn",
        "source_task_id",
        "source_sample_id",
        "expected_turns",
        "expected_output",
    }
)
BLUEPRINT_ALLOWED: frozenset[str] = frozenset(
    {"blueprint_id", "unlocked_turn", "source"}
)
SAMPLE_ALLOWED: frozenset[str] = frozenset(
    {"sample_id", "display_name", "source_delta_id", "summary"}
)

MAP_NODE_STATUS_ALLOWED: frozenset[str] = frozenset(
    {"unknown", "known", "contested", "secured", "lost", "locked"}
)
MAP_NODE_VISIBILITY_ALLOWED: frozenset[str] = frozenset(
    {"hidden", "known", "scouted", "visible"}
)
FACT_VISIBILITY_ALLOWED: frozenset[str] = frozenset(
    {"player_known", "system_only", "npc_known", "hinted"}
)
EVENT_KIND_ALLOWED: frozenset[str] = frozenset(
    {"story", "battle", "research", "resource", "npc", "system", "world"}
)
NPC_AVAILABILITY_ALLOWED: frozenset[str] = frozenset(
    {"present", "absent", "busy", "injured", "missing"}
)
JOB_STATUS_ALLOWED: frozenset[str] = frozenset(
    {"queued", "running", "completed", "failed"}
)
TASK_ALLOWED: frozenset[str] = frozenset(
    {
        "task_id",
        "kind",
        "status",
        "title",
        "summary",
        "node_id",
        "npc_id",
        "objective_refs",
        "reward_refs",
    }
)
TASK_KIND_ALLOWED: frozenset[str] = frozenset(
    {"main", "side", "research", "scouting", "defense", "resource"}
)
TASK_STATUS_ALLOWED: frozenset[str] = frozenset(
    {"available", "active", "completed", "failed", "expired"}
)
RANDOM_EVENT_ALLOWED: frozenset[str] = frozenset(
    {
        "random_event_id",
        "event_type",
        "status",
        "summary",
        "node_id",
        "trigger_turn",
        "related_task_id",
    }
)
RANDOM_EVENT_TYPE_ALLOWED: frozenset[str] = frozenset(
    {
        "map_pressure",
        "resource_shift",
        "npc_visit",
        "research_opportunity",
        "threat_warning",
    }
)
RANDOM_EVENT_STATUS_ALLOWED: frozenset[str] = frozenset(
    {"pending", "available", "resolved", "expired"}
)


def _reject_unknown_keys(
    obj: dict[str, Any], allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    for key in obj.keys():
        if key not in allowed:
            loc = f"{path}.{key}" if path else key
            errors.append(
                f"unknown field '{loc}' is not allowed (allowed: {sorted(allowed)})"
            )


def _require_str(value: Any, path: str, errors: list[str], min_len: int = 1) -> None:
    if not isinstance(value, str) or len(value) < min_len:
        errors.append(f"{path} must be a string with length>={min_len}")


def _require_int(value: Any, path: str, errors: list[str], minimum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{path} must be an integer")
        return
    if minimum is not None and value < minimum:
        errors.append(f"{path} must be >= {minimum} (got {value})")


def _require_number(value: Any, path: str, errors: list[str], lo: float | None = None, hi: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path} must be a number")
        return
    if lo is not None and value < lo:
        errors.append(f"{path} must be >= {lo} (got {value})")
    if hi is not None and value > hi:
        errors.append(f"{path} must be <= {hi} (got {value})")


def _require_enum(value: Any, allowed: frozenset[str], path: str, errors: list[str]) -> None:
    if value not in allowed:
        errors.append(f"{path}={value!r} must be one of {sorted(allowed)}")


def _validate_progress(progress: Any, path: str, errors: list[str]) -> None:
    if not isinstance(progress, dict):
        errors.append(f"{path} must be an object")
        return
    _reject_unknown_keys(progress, PROGRESS_ALLOWED, path, errors)
    for key in ("chapter", "turn", "phase"):
        if key not in progress:
            errors.append(f"{path}.{key} is required")
    if "chapter" in progress:
        _require_int(progress["chapter"], f"{path}.chapter", errors, minimum=1)
    if "turn" in progress:
        _require_int(progress["turn"], f"{path}.turn", errors, minimum=1)
    if "phase" in progress:
        _require_str(progress["phase"], f"{path}.phase", errors)


def _validate_global_state(gs: Any, path: str, errors: list[str]) -> None:
    if not isinstance(gs, dict):
        errors.append(f"{path} must be an object")
        return
    _reject_unknown_keys(gs, GLOBAL_STATE_ALLOWED, path, errors)
    for key in ("pressure", "hope", "visibility"):
        if key not in gs:
            errors.append(f"{path}.{key} is required")
    for key in ("pressure", "hope", "visibility"):
        if key in gs:
            _require_number(gs[key], f"{path}.{key}", errors, lo=0.0, hi=1.0)


def _validate_resources(resources: Any, path: str, errors: list[str]) -> None:
    if not isinstance(resources, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(resources):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, RESOURCE_ALLOWED, ipath, errors)
        if "resource_id" in item:
            _require_str(item["resource_id"], f"{ipath}.resource_id", errors)
        else:
            errors.append(f"{ipath}.resource_id is required")
        if "amount" in item:
            _require_number(item["amount"], f"{ipath}.amount", errors, lo=0.0)
        else:
            errors.append(f"{ipath}.amount is required")


def _validate_map_nodes(nodes: Any, path: str, errors: list[str]) -> None:
    if not isinstance(nodes, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(nodes):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, MAP_NODE_ALLOWED, ipath, errors)
        if "node_id" in item:
            _require_str(item["node_id"], f"{ipath}.node_id", errors)
        else:
            errors.append(f"{ipath}.node_id is required")
        if "status" in item:
            _require_enum(item["status"], MAP_NODE_STATUS_ALLOWED, f"{ipath}.status", errors)
        else:
            errors.append(f"{ipath}.status is required")
        if "threat_level" in item:
            _require_int(item["threat_level"], f"{ipath}.threat_level", errors, minimum=0)
        else:
            errors.append(f"{ipath}.threat_level is required")
        if "visibility" in item:
            _require_enum(item["visibility"], MAP_NODE_VISIBILITY_ALLOWED, f"{ipath}.visibility", errors)
        else:
            errors.append(f"{ipath}.visibility is required")
        if "available_actions" in item:
            aa = item["available_actions"]
            if not isinstance(aa, list) or not all(isinstance(a, str) and a for a in aa):
                errors.append(f"{ipath}.available_actions must be an array of non-empty strings")
        else:
            errors.append(f"{ipath}.available_actions is required")


def _validate_npcs(npcs: Any, path: str, errors: list[str]) -> None:
    if not isinstance(npcs, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(npcs):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, NPC_ALLOWED, ipath, errors)
        if "npc_id" in item:
            _require_str(item["npc_id"], f"{ipath}.npc_id", errors)
        else:
            errors.append(f"{ipath}.npc_id is required")
        if "location_node_id" in item:
            loc = item["location_node_id"]
            if not (loc is None or isinstance(loc, str)):
                errors.append(f"{ipath}.location_node_id must be a string or null")
        else:
            errors.append(f"{ipath}.location_node_id is required")
        for key in ("narrative_roles", "gameplay_roles"):
            if key in item:
                roles = item[key]
                if not isinstance(roles, list) or not all(isinstance(r, str) and r for r in roles):
                    errors.append(f"{ipath}.{key} must be an array of non-empty strings")
            else:
                errors.append(f"{ipath}.{key} is required")
        if "relationship" in item:
            rel = item["relationship"]
            if not isinstance(rel, dict):
                errors.append(f"{ipath}.relationship must be an object")
            else:
                _reject_unknown_keys(rel, NPC_RELATIONSHIP_ALLOWED, f"{ipath}.relationship", errors)
                if "trust" in rel:
                    _require_number(rel["trust"], f"{ipath}.relationship.trust", errors, lo=0.0, hi=1.0)
                else:
                    errors.append(f"{ipath}.relationship.trust is required")
        else:
            errors.append(f"{ipath}.relationship is required")
        if "availability" in item:
            _require_enum(item["availability"], NPC_AVAILABILITY_ALLOWED, f"{ipath}.availability", errors)
        else:
            errors.append(f"{ipath}.availability is required")


def _validate_facts(facts: Any, path: str, errors: list[str]) -> None:
    if not isinstance(facts, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(facts):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, FACT_ALLOWED, ipath, errors)
        if "fact_id" in item:
            _require_str(item["fact_id"], f"{ipath}.fact_id", errors)
        else:
            errors.append(f"{ipath}.fact_id is required")
        if "source" in item:
            _require_str(item["source"], f"{ipath}.source", errors)
        else:
            errors.append(f"{ipath}.source is required")
        if "visibility" in item:
            _require_enum(item["visibility"], FACT_VISIBILITY_ALLOWED, f"{ipath}.visibility", errors)
        else:
            errors.append(f"{ipath}.visibility is required")
        if "summary" in item and item["summary"] is not None:
            _require_str(item["summary"], f"{ipath}.summary", errors)


def _validate_events(events: Any, path: str, errors: list[str]) -> None:
    if not isinstance(events, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(events):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, EVENT_ALLOWED, ipath, errors)
        if "event_id" in item:
            _require_str(item["event_id"], f"{ipath}.event_id", errors)
        else:
            errors.append(f"{ipath}.event_id is required")
        if "turn" in item:
            _require_int(item["turn"], f"{ipath}.turn", errors, minimum=1)
        else:
            errors.append(f"{ipath}.turn is required")
        if "kind" in item:
            _require_enum(item["kind"], EVENT_KIND_ALLOWED, f"{ipath}.kind", errors)
        else:
            errors.append(f"{ipath}.kind is required")
        if "summary" in item:
            _require_str(item["summary"], f"{ipath}.summary", errors)
        else:
            errors.append(f"{ipath}.summary is required")


def _require_string_array(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        errors.append(f"{path} must be an array of non-empty strings")


def _validate_tasks(tasks: Any, path: str, errors: list[str]) -> None:
    if not isinstance(tasks, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(tasks):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, TASK_ALLOWED, ipath, errors)
        for key in ("task_id", "kind", "status", "title", "summary"):
            if key not in item:
                errors.append(f"{ipath}.{key} is required")
        if "task_id" in item:
            _require_str(item["task_id"], f"{ipath}.task_id", errors)
        if "kind" in item:
            _require_enum(item["kind"], TASK_KIND_ALLOWED, f"{ipath}.kind", errors)
        if "status" in item:
            _require_enum(item["status"], TASK_STATUS_ALLOWED, f"{ipath}.status", errors)
        for key in ("title", "summary"):
            if key in item:
                _require_str(item[key], f"{ipath}.{key}", errors)
        for key in ("node_id", "npc_id"):
            if key in item and item[key] is not None:
                _require_str(item[key], f"{ipath}.{key}", errors)
        for key in ("objective_refs", "reward_refs"):
            if key in item:
                _require_string_array(item[key], f"{ipath}.{key}", errors)


def _validate_random_events(random_events: Any, path: str, errors: list[str]) -> None:
    if not isinstance(random_events, list):
        errors.append(f"{path} must be an array")
        return
    for i, item in enumerate(random_events):
        ipath = f"{path}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{ipath} must be an object")
            continue
        _reject_unknown_keys(item, RANDOM_EVENT_ALLOWED, ipath, errors)
        for key in ("random_event_id", "event_type", "status", "summary"):
            if key not in item:
                errors.append(f"{ipath}.{key} is required")
        if "random_event_id" in item:
            _require_str(item["random_event_id"], f"{ipath}.random_event_id", errors)
        if "event_type" in item:
            _require_enum(item["event_type"], RANDOM_EVENT_TYPE_ALLOWED, f"{ipath}.event_type", errors)
        if "status" in item:
            _require_enum(item["status"], RANDOM_EVENT_STATUS_ALLOWED, f"{ipath}.status", errors)
        if "summary" in item:
            _require_str(item["summary"], f"{ipath}.summary", errors)
        if "node_id" in item and item["node_id"] is not None:
            _require_str(item["node_id"], f"{ipath}.node_id", errors)
        if "trigger_turn" in item:
            _require_int(item["trigger_turn"], f"{ipath}.trigger_turn", errors, minimum=1)
        if "related_task_id" in item:
            _require_str(item["related_task_id"], f"{ipath}.related_task_id", errors)


def _validate_research(research: Any, path: str, errors: list[str]) -> None:
    if not isinstance(research, dict):
        errors.append(f"{path} must be an object")
        return
    _reject_unknown_keys(research, RESEARCH_ALLOWED, path, errors)
    for key in ("active_jobs", "known_blueprints", "temporary_samples"):
        if key not in research:
            errors.append(f"{path}.{key} is required")
    jobs = research.get("active_jobs")
    if isinstance(jobs, list):
        for i, job in enumerate(jobs):
            ipath = f"{path}.active_jobs[{i}]"
            if not isinstance(job, dict):
                errors.append(f"{ipath} must be an object")
                continue
            _reject_unknown_keys(job, ACTIVE_JOB_ALLOWED, ipath, errors)
            if "job_id" in job:
                _require_str(job["job_id"], f"{ipath}.job_id", errors)
            else:
                errors.append(f"{ipath}.job_id is required")
            if "status" in job:
                _require_enum(job["status"], JOB_STATUS_ALLOWED, f"{ipath}.status", errors)
            else:
                errors.append(f"{ipath}.status is required")
            for key in ("started_turn", "expected_turns"):
                if key in job:
                    _require_int(job[key], f"{ipath}.{key}", errors, minimum=1)
            for key in ("source_task_id", "source_sample_id", "expected_output"):
                if key in job and job[key] is not None:
                    _require_str(job[key], f"{ipath}.{key}", errors)
    elif jobs is not None:
        errors.append(f"{path}.active_jobs must be an array")
    bps = research.get("known_blueprints")
    if isinstance(bps, list):
        for i, bp in enumerate(bps):
            ipath = f"{path}.known_blueprints[{i}]"
            if not isinstance(bp, dict):
                errors.append(f"{ipath} must be an object")
                continue
            _reject_unknown_keys(bp, BLUEPRINT_ALLOWED, ipath, errors)
            if "blueprint_id" in bp:
                _require_str(bp["blueprint_id"], f"{ipath}.blueprint_id", errors)
            else:
                errors.append(f"{ipath}.blueprint_id is required")
            if "unlocked_turn" in bp:
                _require_int(bp["unlocked_turn"], f"{ipath}.unlocked_turn", errors, minimum=1)
            if "source" in bp and bp["source"] is not None:
                _require_str(bp["source"], f"{ipath}.source", errors)
    elif bps is not None:
        errors.append(f"{path}.known_blueprints must be an array")
    samples = research.get("temporary_samples")
    if isinstance(samples, list):
        for i, s in enumerate(samples):
            ipath = f"{path}.temporary_samples[{i}]"
            if not isinstance(s, dict):
                errors.append(f"{ipath} must be an object")
                continue
            _reject_unknown_keys(s, SAMPLE_ALLOWED, ipath, errors)
            if "sample_id" in s:
                _require_str(s["sample_id"], f"{ipath}.sample_id", errors)
            else:
                errors.append(f"{ipath}.sample_id is required")
            if "display_name" in s:
                _require_str(s["display_name"], f"{ipath}.display_name", errors)
            else:
                errors.append(f"{ipath}.display_name is required")
            if "source_delta_id" in s:
                _require_str(s["source_delta_id"], f"{ipath}.source_delta_id", errors)
            else:
                errors.append(f"{ipath}.source_delta_id is required")
            if "summary" in s and s["summary"] is not None:
                _require_str(s["summary"], f"{ipath}.summary", errors)
    elif samples is not None:
        errors.append(f"{path}.temporary_samples must be an array")


def _validate_flags(flags: Any, path: str, errors: list[str]) -> None:
    if not isinstance(flags, dict):
        errors.append(f"{path} must be an object")
        return
    # flags values restricted to primitives (bool/string/number/null) to
    # prevent nested provider/trace payloads.
    for key, val in flags.items():
        if isinstance(val, (dict, list)):
            errors.append(
                f"{path}.{key} must be a primitive (bool/string/number/null); "
                f"nested objects/arrays are not allowed in flags"
            )


def validate_run_world_state(state: dict[str, Any]) -> list[str]:
    """Return a list of human-readable error strings; empty list means valid."""
    errors: list[str] = []

    if not isinstance(state, dict):
        return ["state root must be an object"]

    _reject_unknown_keys(state, TOP_LEVEL_ALLOWED, "", errors)

    # required top-level fields
    for key in TOP_LEVEL_REQUIRED:
        if key not in state:
            errors.append(f"{key} is required at top level")

    if state.get("schema_version") != "run_world_state.v0.1":
        errors.append(
            f"schema_version must be 'run_world_state.v0.1' "
            f"(got {state.get('schema_version')!r})"
        )
    if "run_id" in state:
        _require_str(state["run_id"], "run_id", errors)
    if "worldbook_id" in state:
        _require_str(state["worldbook_id"], "worldbook_id", errors)

    if "progress" in state:
        _validate_progress(state["progress"], "progress", errors)
    if "global_state" in state:
        _validate_global_state(state["global_state"], "global_state", errors)
    if "resources" in state:
        _validate_resources(state["resources"], "resources", errors)
    if "map_nodes" in state:
        _validate_map_nodes(state["map_nodes"], "map_nodes", errors)
    if "npcs" in state:
        _validate_npcs(state["npcs"], "npcs", errors)
    if "unlocked_facts" in state:
        _validate_facts(state["unlocked_facts"], "unlocked_facts", errors)
    if "event_log" in state:
        _validate_events(state["event_log"], "event_log", errors)
    if "research" in state:
        _validate_research(state["research"], "research", errors)
    if "tasks" in state:
        _validate_tasks(state["tasks"], "tasks", errors)
    if "random_events" in state:
        _validate_random_events(state["random_events"], "random_events", errors)
    if "flags" in state:
        _validate_flags(state["flags"], "flags", errors)

    # --- recursive forbidden-field scan (defense in depth) ---
    scan_forbidden_fields(state, "", errors)

    return errors


def validate_with_jsonschema(state: dict[str, Any]) -> list[str]:
    """Validate against the JSON Schema using jsonschema if available.

    Returns a list of error strings (empty if valid or if jsonschema is not
    available — in which case the pure-Python validator does the work).
    """
    try:
        schema = load_json(SCHEMA_PATH)
    except FileNotFoundError:
        return []  # schema missing; pure-Python path handles validation
    validator = get_jsonschema_validator(schema)
    if validator is None:
        return []
    errors: list[str] = []
    for err in validator.iter_errors(state):
        loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"schema: {loc}: {err.message}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a RunWorldState v0.1 JSON file."
    )
    parser.add_argument("state", help="Path to a RunWorldState JSON file.")
    args = parser.parse_args()

    state_path = Path(args.state)
    try:
        state = load_json(state_path)
    except FileNotFoundError:
        print("INVALID RunWorldState")
        print(f"- state file not found: {state_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID RunWorldState")
        print(f"- state is not valid JSON: {exc}")
        return 1

    if not isinstance(state, dict):
        print("INVALID RunWorldState")
        print("- state root must be an object")
        return 1

    errors: list[str] = []
    # Prefer jsonschema when available; always also run pure-Python checks for
    # custom policies (forbidden fields, flags primitive-only) that the schema
    # cannot fully express.
    errors.extend(validate_with_jsonschema(state))
    errors.extend(validate_run_world_state(state))
    # de-duplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    if deduped:
        print("INVALID RunWorldState")
        for error in deduped:
            print(f"- {error}")
        return 1

    print(f"OK: {state_path}")
    print(f"- schema_version: {state.get('schema_version')}")
    print(f"- run_id: {state.get('run_id')}")
    print(f"- worldbook_id: {state.get('worldbook_id')}")
    print(f"- map_nodes: {len(state.get('map_nodes', []))}")
    print(f"- npcs: {len(state.get('npcs', []))}")
    print(f"- events: {len(state.get('event_log', []))}")
    print(f"- tasks: {len(state.get('tasks', []))}")
    print(f"- random_events: {len(state.get('random_events', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
