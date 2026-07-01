#!/usr/bin/env python3
"""Validate a WorldStateDelta v0.1 JSON file.

Checks:
- JSON parses.
- schema_version == "world_state_delta.v0.1".
- Top-level required fields present; unknown top-level fields rejected.
- operation op whitelist: only the 11 allowed ops may appear.
- operation forbidden-op blacklist: mutate_base_worldbook / set_worldbook /
  replace_worldbook / raw_json_patch / arbitrary_patch / eval / script /
  provider_call are explicitly rejected with a clear error.
- jsonschema validation when jsonschema is available (preferred).
- Pure-Python fallback otherwise.
- Player-visible text banned-word scan (word-boundary, case-insensitive) on
  delta.summary, append_event.event.summary, unlock_fact.fact.summary,
  add_temporary_sample.sample.display_name / summary.
- Recursive forbidden-field scan (provider/model/raw_prompt/full_trace/
  raw_json/api_key/secret/unreviewed_content).

The validator never reads .env and never prints API keys or secrets.

Usage:
    python3 tools/world_state/validate_world_delta.py <delta_path>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import (  # noqa: E402  (import after sys.path bootstrap)
    BANNED_PLAYER_WORDS,
    get_jsonschema_validator,
    load_json,
    scan_forbidden_fields,
)

SCHEMA_PATH = ROOT / "shared/schemas/world_state_delta.v0.1.schema.json"

# Whitelist of allowed operation op values (only these 11).
OPERATION_WHITELIST: frozenset[str] = frozenset(
    {
        "append_event",
        "set_map_node_state",
        "adjust_resource",
        "introduce_map_node",
        "set_flag",
        "unlock_fact",
        "update_npc_relationship",
        "introduce_npc",
        "add_temporary_sample",
        "set_progress_phase",
        "adjust_global_state",
    }
)

# Explicitly forbidden operations (must be rejected even if the schema oneOf
# already rejects them — defense in depth, and the error message is clearer).
OPERATION_BLACKLIST: frozenset[str] = frozenset(
    {
        "mutate_base_worldbook",
        "set_worldbook",
        "replace_worldbook",
        "raw_json_patch",
        "arbitrary_patch",
        "eval",
        "script",
        "provider_call",
    }
)

TOP_LEVEL_ALLOWED: frozenset[str] = frozenset(
    {
        "schema_version",
        "delta_id",
        "run_id",
        "worldbook_id",
        "source",
        "created_turn",
        "summary",
        "operations",
    }
)
SOURCE_ALLOWED: frozenset[str] = frozenset(
    {"battle_result", "research_job", "narrative_event", "system"}
)
EVENT_KIND_ALLOWED: frozenset[str] = frozenset(
    {"story", "battle", "research", "resource", "npc", "system", "world"}
)
NODE_STATUS_ALLOWED: frozenset[str] = frozenset(
    {"unknown", "known", "contested", "secured", "lost", "locked"}
)
NODE_VISIBILITY_ALLOWED: frozenset[str] = frozenset(
    {"hidden", "known", "scouted", "visible"}
)
FACT_VISIBILITY_ALLOWED: frozenset[str] = frozenset(
    {"player_known", "system_only", "npc_known", "hinted"}
)
GLOBAL_STATE_FIELDS_ALLOWED: frozenset[str] = frozenset(
    {"pressure", "hope", "visibility"}
)
NPC_AVAILABILITY_ALLOWED: frozenset[str] = frozenset(
    {"present", "absent", "busy", "injured", "missing"}
)

# Per-operation allowed keys (beyond "op"). Used for the pure-Python fallback's
# additionalProperties:false enforcement on each operation branch.
OP_ALLOWED_KEYS: dict[str, frozenset[str]] = {
    "append_event": frozenset({"op", "event"}),
    "set_map_node_state": frozenset({"op", "node_id", "patch"}),
    "adjust_resource": frozenset({"op", "resource_id", "amount_delta"}),
    "introduce_map_node": frozenset({"op", "node"}),
    "set_flag": frozenset({"op", "flag", "value"}),
    "unlock_fact": frozenset({"op", "fact"}),
    "update_npc_relationship": frozenset({"op", "npc_id", "relationship_delta"}),
    "introduce_npc": frozenset({"op", "npc"}),
    "add_temporary_sample": frozenset({"op", "sample"}),
    "set_progress_phase": frozenset({"op", "phase"}),
    "adjust_global_state": frozenset({"op", "field", "amount_delta"}),
}
EVENT_ALLOWED: frozenset[str] = frozenset({"event_id", "turn", "kind", "summary"})
FACT_ALLOWED: frozenset[str] = frozenset({"fact_id", "source", "visibility", "summary"})
SAMPLE_ALLOWED: frozenset[str] = frozenset(
    {"sample_id", "display_name", "source_delta_id", "summary"}
)
PATCH_ALLOWED: frozenset[str] = frozenset(
    {"status", "threat_level", "visibility", "available_actions"}
)
RELATIONSHIP_DELTA_ALLOWED: frozenset[str] = frozenset({"trust"})
RUN_MAP_NODE_ALLOWED: frozenset[str] = frozenset(
    {"node_id", "status", "threat_level", "visibility", "available_actions"}
)
RUN_NPC_ALLOWED: frozenset[str] = frozenset(
    {
        "npc_id",
        "location_node_id",
        "narrative_roles",
        "gameplay_roles",
        "relationship",
        "availability",
    }
)
RUN_NPC_RELATIONSHIP_ALLOWED: frozenset[str] = frozenset({"trust"})


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


def _require_number(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{path} must be a number")


def _require_enum(value: Any, allowed: frozenset[str], path: str, errors: list[str]) -> None:
    if value not in allowed:
        errors.append(f"{path}={value!r} must be one of {sorted(allowed)}")


# --- player-visible text banned-word scan ---

def _word_boundary_regex(word: str) -> re.Pattern[str]:
    # Word-boundary, case-insensitive. \b works for ASCII; the banned words
    # are all ASCII so this is sufficient. We escape the word for safety.
    return re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)


_BANNED_WORD_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    (w, _word_boundary_regex(w)) for w in sorted(BANNED_PLAYER_WORDS)
]


def _scan_text_for_banned_words(text: str, path: str, errors: list[str]) -> None:
    if not isinstance(text, str) or not text:
        return
    for word, pattern in _BANNED_WORD_REGEXES:
        if pattern.search(text):
            errors.append(
                f"{path}: player-visible text contains banned word '{word}' "
                f"(must not leak studio/technical terms to the player side)"
            )


def _scan_player_visible_text(delta: dict[str, Any], errors: list[str]) -> None:
    """Scan all player-visible text fields for banned words."""
    summary = delta.get("summary")
    if isinstance(summary, str):
        _scan_text_for_banned_words(summary, "summary", errors)

    for i, op in enumerate(delta.get("operations", []) or []):
        if not isinstance(op, dict):
            continue
        op_name = op.get("op")
        op_path = f"operations[{i}]"
        if op_name == "append_event":
            event = op.get("event")
            if isinstance(event, dict):
                s = event.get("summary")
                if isinstance(s, str):
                    _scan_text_for_banned_words(s, f"{op_path}.event.summary", errors)
        elif op_name == "unlock_fact":
            fact = op.get("fact")
            if isinstance(fact, dict):
                s = fact.get("summary")
                if isinstance(s, str):
                    _scan_text_for_banned_words(s, f"{op_path}.fact.summary", errors)
        elif op_name == "add_temporary_sample":
            sample = op.get("sample")
            if isinstance(sample, dict):
                dn = sample.get("display_name")
                if isinstance(dn, str):
                    _scan_text_for_banned_words(
                        dn, f"{op_path}.sample.display_name", errors
                    )
                s = sample.get("summary")
                if isinstance(s, str):
                    _scan_text_for_banned_words(s, f"{op_path}.sample.summary", errors)


# --- per-operation validation ---

def _validate_append_event(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["append_event"], path, errors)
    event = op.get("event")
    epath = f"{path}.event"
    if not isinstance(event, dict):
        errors.append(f"{epath} must be an object")
        return
    _reject_unknown_keys(event, EVENT_ALLOWED, epath, errors)
    for key in ("event_id", "turn", "kind", "summary"):
        if key not in event:
            errors.append(f"{epath}.{key} is required")
    if "event_id" in event:
        _require_str(event["event_id"], f"{epath}.event_id", errors)
    if "turn" in event:
        _require_int(event["turn"], f"{epath}.turn", errors, minimum=1)
    if "kind" in event:
        _require_enum(event["kind"], EVENT_KIND_ALLOWED, f"{epath}.kind", errors)
    if "summary" in event:
        _require_str(event["summary"], f"{epath}.summary", errors)


def _validate_set_map_node_state(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["set_map_node_state"], path, errors)
    if "node_id" in op:
        _require_str(op["node_id"], f"{path}.node_id", errors)
    else:
        errors.append(f"{path}.node_id is required")
    patch = op.get("patch")
    ppath = f"{path}.patch"
    if not isinstance(patch, dict):
        errors.append(f"{ppath} must be an object")
        return
    if not patch:
        errors.append(f"{ppath} must have at least one property")
    _reject_unknown_keys(patch, PATCH_ALLOWED, ppath, errors)
    if "status" in patch:
        _require_enum(patch["status"], NODE_STATUS_ALLOWED, f"{ppath}.status", errors)
    if "threat_level" in patch:
        _require_int(patch["threat_level"], f"{ppath}.threat_level", errors, minimum=0)
    if "visibility" in patch:
        _require_enum(patch["visibility"], NODE_VISIBILITY_ALLOWED, f"{ppath}.visibility", errors)
    if "available_actions" in patch:
        aa = patch["available_actions"]
        if not isinstance(aa, list) or not all(isinstance(a, str) and a for a in aa):
            errors.append(f"{ppath}.available_actions must be an array of non-empty strings")


def _validate_adjust_resource(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["adjust_resource"], path, errors)
    if "resource_id" in op:
        _require_str(op["resource_id"], f"{path}.resource_id", errors)
    else:
        errors.append(f"{path}.resource_id is required")
    if "amount_delta" in op:
        _require_number(op["amount_delta"], f"{path}.amount_delta", errors)
    else:
        errors.append(f"{path}.amount_delta is required")


def _validate_run_map_node_obj(node: Any, path: str, errors: list[str]) -> None:
    if not isinstance(node, dict):
        errors.append(f"{path} must be an object")
        return
    _reject_unknown_keys(node, RUN_MAP_NODE_ALLOWED, path, errors)
    for key in ("node_id", "status", "threat_level", "visibility", "available_actions"):
        if key not in node:
            errors.append(f"{path}.{key} is required")
    if "node_id" in node:
        _require_str(node["node_id"], f"{path}.node_id", errors)
    if "status" in node:
        _require_enum(node["status"], NODE_STATUS_ALLOWED, f"{path}.status", errors)
    if "threat_level" in node:
        _require_int(node["threat_level"], f"{path}.threat_level", errors, minimum=0)
    if "visibility" in node:
        _require_enum(node["visibility"], NODE_VISIBILITY_ALLOWED, f"{path}.visibility", errors)
    if "available_actions" in node:
        aa = node["available_actions"]
        if not isinstance(aa, list) or not all(isinstance(a, str) and a for a in aa):
            errors.append(f"{path}.available_actions must be an array of non-empty strings")


def _validate_introduce_map_node(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["introduce_map_node"], path, errors)
    _validate_run_map_node_obj(op.get("node"), f"{path}.node", errors)


def _validate_set_flag(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["set_flag"], path, errors)
    if "flag" in op:
        _require_str(op["flag"], f"{path}.flag", errors)
    else:
        errors.append(f"{path}.flag is required")
    if "value" not in op:
        errors.append(f"{path}.value is required")
    else:
        val = op["value"]
        if not (val is None or isinstance(val, (bool, str, int, float))):
            errors.append(
                f"{path}.value must be a primitive (bool/string/number/null)"
            )


def _validate_unlock_fact(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["unlock_fact"], path, errors)
    fact = op.get("fact")
    fpath = f"{path}.fact"
    if not isinstance(fact, dict):
        errors.append(f"{fpath} must be an object")
        return
    _reject_unknown_keys(fact, FACT_ALLOWED, fpath, errors)
    for key in ("fact_id", "source", "visibility"):
        if key not in fact:
            errors.append(f"{fpath}.{key} is required")
    if "fact_id" in fact:
        _require_str(fact["fact_id"], f"{fpath}.fact_id", errors)
    if "source" in fact:
        _require_str(fact["source"], f"{fpath}.source", errors)
    if "visibility" in fact:
        _require_enum(fact["visibility"], FACT_VISIBILITY_ALLOWED, f"{fpath}.visibility", errors)
    if "summary" in fact and fact["summary"] is not None:
        _require_str(fact["summary"], f"{fpath}.summary", errors)


def _validate_update_npc_relationship(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["update_npc_relationship"], path, errors)
    if "npc_id" in op:
        _require_str(op["npc_id"], f"{path}.npc_id", errors)
    else:
        errors.append(f"{path}.npc_id is required")
    rd = op.get("relationship_delta")
    rpath = f"{path}.relationship_delta"
    if not isinstance(rd, dict):
        errors.append(f"{rpath} must be an object")
        return
    if not rd:
        errors.append(f"{rpath} must have at least one property")
    _reject_unknown_keys(rd, RELATIONSHIP_DELTA_ALLOWED, rpath, errors)
    if "trust" in rd:
        _require_number(rd["trust"], f"{rpath}.trust", errors)


def _validate_run_npc_obj(npc: Any, path: str, errors: list[str]) -> None:
    if not isinstance(npc, dict):
        errors.append(f"{path} must be an object")
        return
    _reject_unknown_keys(npc, RUN_NPC_ALLOWED, path, errors)
    for key in (
        "npc_id",
        "location_node_id",
        "narrative_roles",
        "gameplay_roles",
        "relationship",
        "availability",
    ):
        if key not in npc:
            errors.append(f"{path}.{key} is required")
    if "npc_id" in npc:
        _require_str(npc["npc_id"], f"{path}.npc_id", errors)
    if "location_node_id" in npc:
        loc = npc["location_node_id"]
        if loc is not None and not isinstance(loc, str):
            errors.append(f"{path}.location_node_id must be a string or null")
        elif isinstance(loc, str) and not loc:
            errors.append(f"{path}.location_node_id must be non-empty when string")
    for key in ("narrative_roles", "gameplay_roles"):
        if key in npc:
            roles = npc[key]
            if not isinstance(roles, list) or not all(isinstance(role, str) and role for role in roles):
                errors.append(f"{path}.{key} must be an array of non-empty strings")
    relationship = npc.get("relationship")
    rpath = f"{path}.relationship"
    if not isinstance(relationship, dict):
        errors.append(f"{rpath} must be an object")
    else:
        _reject_unknown_keys(relationship, RUN_NPC_RELATIONSHIP_ALLOWED, rpath, errors)
        if "trust" not in relationship:
            errors.append(f"{rpath}.trust is required")
        else:
            _require_number(relationship["trust"], f"{rpath}.trust", errors)
            if isinstance(relationship["trust"], (int, float)) and not isinstance(relationship["trust"], bool):
                if relationship["trust"] < 0 or relationship["trust"] > 1:
                    errors.append(f"{rpath}.trust must be between 0 and 1")
    if "availability" in npc:
        _require_enum(npc["availability"], NPC_AVAILABILITY_ALLOWED, f"{path}.availability", errors)


def _validate_introduce_npc(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["introduce_npc"], path, errors)
    _validate_run_npc_obj(op.get("npc"), f"{path}.npc", errors)


def _validate_add_temporary_sample(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["add_temporary_sample"], path, errors)
    sample = op.get("sample")
    spath = f"{path}.sample"
    if not isinstance(sample, dict):
        errors.append(f"{spath} must be an object")
        return
    _reject_unknown_keys(sample, SAMPLE_ALLOWED, spath, errors)
    for key in ("sample_id", "display_name", "source_delta_id"):
        if key not in sample:
            errors.append(f"{spath}.{key} is required")
    if "sample_id" in sample:
        _require_str(sample["sample_id"], f"{spath}.sample_id", errors)
    if "display_name" in sample:
        _require_str(sample["display_name"], f"{spath}.display_name", errors)
    if "source_delta_id" in sample:
        _require_str(sample["source_delta_id"], f"{spath}.source_delta_id", errors)
    if "summary" in sample and sample["summary"] is not None:
        _require_str(sample["summary"], f"{spath}.summary", errors)


def _validate_set_progress_phase(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["set_progress_phase"], path, errors)
    if "phase" in op:
        _require_str(op["phase"], f"{path}.phase", errors)
    else:
        errors.append(f"{path}.phase is required")


def _validate_adjust_global_state(op: dict[str, Any], path: str, errors: list[str]) -> None:
    _reject_unknown_keys(op, OP_ALLOWED_KEYS["adjust_global_state"], path, errors)
    if "field" in op:
        _require_enum(op["field"], GLOBAL_STATE_FIELDS_ALLOWED, f"{path}.field", errors)
    else:
        errors.append(f"{path}.field is required")
    if "amount_delta" in op:
        _require_number(op["amount_delta"], f"{path}.amount_delta", errors)
    else:
        errors.append(f"{path}.amount_delta is required")


_OP_VALIDATORS = {
    "append_event": _validate_append_event,
    "set_map_node_state": _validate_set_map_node_state,
    "adjust_resource": _validate_adjust_resource,
    "introduce_map_node": _validate_introduce_map_node,
    "set_flag": _validate_set_flag,
    "unlock_fact": _validate_unlock_fact,
    "update_npc_relationship": _validate_update_npc_relationship,
    "introduce_npc": _validate_introduce_npc,
    "add_temporary_sample": _validate_add_temporary_sample,
    "set_progress_phase": _validate_set_progress_phase,
    "adjust_global_state": _validate_adjust_global_state,
}


def validate_world_delta(delta: dict[str, Any]) -> list[str]:
    """Return a list of human-readable error strings; empty list means valid."""
    errors: list[str] = []

    if not isinstance(delta, dict):
        return ["delta root must be an object"]

    _reject_unknown_keys(delta, TOP_LEVEL_ALLOWED, "", errors)
    for key in TOP_LEVEL_ALLOWED:
        if key not in delta:
            errors.append(f"{key} is required at top level")

    if delta.get("schema_version") != "world_state_delta.v0.1":
        errors.append(
            f"schema_version must be 'world_state_delta.v0.1' "
            f"(got {delta.get('schema_version')!r})"
        )
    if "delta_id" in delta:
        _require_str(delta["delta_id"], "delta_id", errors)
    if "run_id" in delta:
        _require_str(delta["run_id"], "run_id", errors)
    if "worldbook_id" in delta:
        _require_str(delta["worldbook_id"], "worldbook_id", errors)
    if "source" in delta:
        _require_enum(delta["source"], SOURCE_ALLOWED, "source", errors)
    if "created_turn" in delta:
        _require_int(delta["created_turn"], "created_turn", errors, minimum=1)
    if "summary" in delta:
        _require_str(delta["summary"], "summary", errors)

    operations = delta.get("operations")
    if not isinstance(operations, list):
        errors.append("operations must be an array")
        operations = []
    if isinstance(operations, list) and len(operations) == 0:
        errors.append("operations must be a non-empty array")

    for i, op in enumerate(operations):
        opath = f"operations[{i}]"
        if not isinstance(op, dict):
            errors.append(f"{opath} must be an object")
            continue
        op_name = op.get("op")
        if not isinstance(op_name, str) or not op_name:
            errors.append(f"{opath}.op must be a non-empty string")
            continue
        # Explicit forbidden-op check (clear error message; defense in depth
        # even though the schema oneOf already rejects these).
        if op_name in OPERATION_BLACKLIST:
            errors.append(
                f"{opath}.op={op_name!r} is a forbidden operation: it would "
                f"mutate the BaseWorldbook or bypass the controlled Delta "
                f"mechanism (blacklist: {sorted(OPERATION_BLACKLIST)})"
            )
            continue
        if op_name not in OPERATION_WHITELIST:
            errors.append(
                f"{opath}.op={op_name!r} is not in the operation whitelist "
                f"(allowed: {sorted(OPERATION_WHITELIST)})"
            )
            continue
        validator_fn = _OP_VALIDATORS[op_name]
        validator_fn(op, opath, errors)

    # --- player-visible text banned-word scan ---
    _scan_player_visible_text(delta, errors)

    # --- recursive forbidden-field scan (defense in depth) ---
    scan_forbidden_fields(delta, "", errors)

    return errors


def validate_with_jsonschema(delta: dict[str, Any]) -> list[str]:
    """Validate against the JSON Schema using jsonschema if available."""
    try:
        schema = load_json(SCHEMA_PATH)
    except FileNotFoundError:
        return []
    validator = get_jsonschema_validator(schema)
    if validator is None:
        return []
    errors: list[str] = []
    for err in validator.iter_errors(delta):
        loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"schema: {loc}: {err.message}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a WorldStateDelta v0.1 JSON file."
    )
    parser.add_argument("delta", help="Path to a WorldStateDelta JSON file.")
    args = parser.parse_args()

    delta_path = Path(args.delta)
    try:
        delta = load_json(delta_path)
    except FileNotFoundError:
        print("INVALID WorldStateDelta")
        print(f"- delta file not found: {delta_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID WorldStateDelta")
        print(f"- delta is not valid JSON: {exc}")
        return 1

    if not isinstance(delta, dict):
        print("INVALID WorldStateDelta")
        print("- delta root must be an object")
        return 1

    errors: list[str] = []
    errors.extend(validate_with_jsonschema(delta))
    errors.extend(validate_world_delta(delta))
    # de-duplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    if deduped:
        print("INVALID WorldStateDelta")
        for error in deduped:
            print(f"- {error}")
        return 1

    print(f"OK: {delta_path}")
    print(f"- schema_version: {delta.get('schema_version')}")
    print(f"- delta_id: {delta.get('delta_id')}")
    print(f"- run_id: {delta.get('run_id')}")
    print(f"- worldbook_id: {delta.get('worldbook_id')}")
    print(f"- source: {delta.get('source')}")
    print(f"- operations: {len(delta.get('operations', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
