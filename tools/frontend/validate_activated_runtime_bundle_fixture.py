#!/usr/bin/env python3
"""Validate the MVP activated runtime bundle frontend fixture."""

from __future__ import annotations

import argparse
import json
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

from report_io import load_json_object


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "activated_runtime_bundle.mvp.v0.1"
FORBIDDEN_TERMS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    ".env",
    "executor_request",
    "authorization_header",
    "bearer_token",
}
ABI_FIELDS = {
    "placement",
    "cost",
    "cooldown",
    "targeting",
    "effect_blocks",
    "ui_surfaces",
    "simulation_hooks",
}
PROJECTION_FIELDS = {
    "map_projection",
    "package_projection",
    "media_projection",
    "effects_projection",
    "narrative_projection",
    "world_projection",
}
HASH_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")
REQUIRED_BATTLE_ASSET_KINDS = {
    "tower_blueprint",
    "temporary_trap_sample",
    "support_item",
}
REQUIRED_FEATURE_SNAPSHOTS = {
    "strategic_map",
    "workshop",
    "battle",
    "narrative",
    "settlement",
}
BATTLE_OBJECT_SCHEMA = ROOT / "shared/schemas/battle_object_capability.v0.1.schema.json"
STRATEGIC_CONTRIBUTION_SLOTS = {
    "objective_card": "objective_overlay",
    "node_participant": "node_panel",
    "node_badge": "node_marker",
    "map_notice": "objective_overlay",
}
FORBIDDEN_CONTRIBUTION_KEYS = {
    "html",
    "script",
    "javascript",
    "css",
    "style",
    "component_code",
    "event_handler",
}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def path_text(path: tuple[str, ...]) -> str:
    return "$" + "".join(f".{part}" for part in path)


def normalized_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def scan_forbidden_terms(
    value: Any,
    path: tuple[str, ...] = (),
) -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            key_normalized = normalized_token(key_text)
            for term in FORBIDDEN_TERMS:
                if term in key_lower or normalized_token(term) in key_normalized:
                    hits.append(f"{path_text(path + (key_text,))} key contains {term!r}")
            hits.extend(scan_forbidden_terms(child, path + (key_text,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(scan_forbidden_terms(child, path + (str(index),)))
    elif isinstance(value, str):
        lower = value.lower()
        normalized = normalized_token(value)
        for term in FORBIDDEN_TERMS:
            if term in lower or normalized_token(term) in normalized:
                hits.append(f"{path_text(path)} contains {term!r}")
    return hits


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_package_refs(value: Any, failures: list[str], path: tuple[str, ...] = ()) -> int:
    count = 0
    if isinstance(value, dict):
        if "ref" in value:
            count += 1
            label = path_text(path)
            require(bool(value.get("schema_version")), f"{label}.schema_version missing", failures)
            ref = str(value.get("ref") or "")
            require(bool(ref), f"{label}.ref missing", failures)
            digest = str(value.get("hash") or "")
            require(bool(HASH_RE.match(digest)), f"{label}.hash must be sha256", failures)
            ref_path = ROOT / ref
            require(ref_path.exists(), f"{label}.ref file missing: {ref}", failures)
            if ref_path.exists() and HASH_RE.match(digest):
                expected = digest.removeprefix("sha256:")
                actual = sha256_digest(ref_path)
                require(actual == expected, f"{label}.hash mismatch for {ref}", failures)
        for key, child in value.items():
            count += validate_package_refs(child, failures, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            count += validate_package_refs(child, failures, path + (str(index),))
    return count


def find_abi_fields(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(ABI_FIELDS & set(map(str, value.keys())))
        for child in value.values():
            found.update(find_abi_fields(child))
    elif isinstance(value, list):
        for child in value:
            found.update(find_abi_fields(child))
    return found


def validate_battle_objects(battle_objects: list[Any], failures: list[str]) -> None:
    schema = json.loads(BATTLE_OBJECT_SCHEMA.read_text(encoding="utf-8"))
    try:
        import jsonschema  # type: ignore
    except ImportError:
        validator = None
    else:
        validator_cls = getattr(jsonschema, "Draft202012Validator", None) or getattr(
            jsonschema, "Draft7Validator"
        )
        validator = validator_cls(schema)
    observed_kinds: set[str] = set()
    for index, item in enumerate(battle_objects):
        if not isinstance(item, dict):
            failures.append(f"capabilities.battle_objects[{index}] must be an object")
            continue
        label = f"capabilities.battle_objects[{index}]"
        require(
            item.get("schema_version") == "battle_object_capability.v0.1",
            f"{label}.schema_version mismatch",
            failures,
        )
        if validator is not None:
            for error in sorted(validator.iter_errors(item), key=lambda entry: list(entry.path)):
                location = ".".join(map(str, error.path)) or "$"
                failures.append(f"{label}.{location}: {error.message}")
        asset_kind = str(item.get("asset_kind") or "")
        observed_kinds.add(asset_kind)
        require(bool(item.get("object_id")), f"{label}.object_id missing", failures)
        require(bool(asset_kind), f"{label}.asset_kind missing", failures)
        require(bool(as_obj(item.get("lifecycle"))), f"{label}.lifecycle missing", failures)
        behavior = as_obj(item.get("behavior_abi"))
        require(bool(behavior), f"{label}.behavior_abi missing", failures)
        missing = ABI_FIELDS - set(behavior.keys())
        require(not missing, f"{label}.behavior_abi missing fields: {sorted(missing)}", failures)
        require(bool(as_list(behavior.get("effect_blocks"))), f"{label}.effect_blocks must not be empty", failures)
        require(bool(as_list(behavior.get("ui_surfaces"))), f"{label}.ui_surfaces must not be empty", failures)
        require(bool(as_list(behavior.get("simulation_hooks"))), f"{label}.simulation_hooks must not be empty", failures)
    require(
        REQUIRED_BATTLE_ASSET_KINDS <= observed_kinds,
        f"capabilities.battle_objects missing asset kinds: {sorted(REQUIRED_BATTLE_ASSET_KINDS - observed_kinds)}",
        failures,
    )


def validate_strategic_contributions(snapshot: dict[str, Any], gates: dict[str, Any], failures: list[str]) -> None:
    require(snapshot.get("surface") == "strategic_map", "strategic_map.surface mismatch", failures)
    require(snapshot.get("status") == "active", "strategic_map.status must be active", failures)
    required_gates = list(map(str, as_list(snapshot.get("required_gates"))))
    require(bool(required_gates), "strategic_map.required_gates must not be empty", failures)
    for gate_id in required_gates:
        require(
            as_obj(gates.get(gate_id)).get("enabled") is True,
            f"strategic_map required gate is not enabled: {gate_id}",
            failures,
        )
    contributions = as_list(snapshot.get("contributions"))
    require(bool(contributions), "strategic_map.contributions must not be empty", failures)
    ids: set[str] = set()
    for index, item in enumerate(contributions):
        contribution = as_obj(item)
        label = f"feature_snapshots.strategic_map.contributions[{index}]"
        contribution_id = str(contribution.get("contribution_id") or "")
        require(bool(contribution_id), f"{label}.contribution_id missing", failures)
        require(contribution_id not in ids, f"{label}.contribution_id duplicated", failures)
        ids.add(contribution_id)
        kind = str(contribution.get("kind") or "")
        require(kind in STRATEGIC_CONTRIBUTION_SLOTS, f"{label}.kind is not allowlisted", failures)
        expected_slot = STRATEGIC_CONTRIBUTION_SLOTS.get(kind)
        require(contribution.get("slot") == expected_slot, f"{label}.slot must be {expected_slot}", failures)
        require(
            contribution.get("visibility") == "player_visible",
            f"{label}.visibility must be player_visible",
            failures,
        )
        payload = as_obj(contribution.get("payload"))
        require(bool(payload), f"{label}.payload missing", failures)
        forbidden = FORBIDDEN_CONTRIBUTION_KEYS & {str(key).lower() for key in payload}
        require(not forbidden, f"{label}.payload contains executable presentation fields: {sorted(forbidden)}", failures)


def validate(fixture: dict[str, Any]) -> None:
    failures: list[str] = []
    require(fixture.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch", failures)
    for field in (
        "fixture_scope",
        "activation_authority",
        "frontend_role",
        "activation_receipt",
        "runtime_selection",
        "package_refs",
        "capabilities",
        "feature_gates",
        "feature_snapshots",
        "disabled_policy",
        "rollback",
        "quarantine",
        "projections",
    ):
        require(field in fixture, f"missing top-level field: {field}", failures)
    require(fixture.get("runtime_type") == "ActivatedRuntimeBundle", "runtime_type must be ActivatedRuntimeBundle", failures)
    require(fixture.get("frontend_role") == "consume_only", "frontend_role must be consume_only", failures)
    require(
        fixture.get("activation_authority") == "backend_or_published_artifact",
        "activation_authority must be backend_or_published_artifact",
        failures,
    )

    receipt = as_obj(fixture.get("activation_receipt"))
    require(bool(receipt.get("activation_id")), "activation_receipt.activation_id missing", failures)
    require(
        receipt.get("status") in {"activated_fixture", "activated", "active"},
        f"activation_receipt.status invalid: {receipt.get('status')!r}",
        failures,
    )
    require(
        receipt.get("runtime_safe_scan") == "passed",
        "activation_receipt.runtime_safe_scan must be passed",
        failures,
    )
    require(
        receipt.get("player_visible_default") is True,
        "activation_receipt.player_visible_default must be true",
        failures,
    )

    selection = as_obj(fixture.get("runtime_selection"))
    require(selection.get("activation_applied") is True, "runtime_selection.activation_applied must be true", failures)
    require(bool(selection.get("selected_schema_version")), "runtime_selection.selected_schema_version missing", failures)
    selected_nodes = set(map(str, as_list(selection.get("selected_node_ids"))))
    require(
        {"gray_lantern_station", "lamp_wick_store", "old_signal_tower"} <= selected_nodes,
        f"runtime_selection missing MVP nodes: {sorted({'gray_lantern_station', 'lamp_wick_store', 'old_signal_tower'} - selected_nodes)}",
        failures,
    )
    require(bool(selection.get("default_node_id")), "runtime_selection.default_node_id missing", failures)

    package_ref_count = validate_package_refs(fixture.get("package_refs"), failures, ("package_refs",))
    require(package_ref_count >= 3, "package_refs must include package refs with hashes", failures)

    capabilities = as_obj(fixture.get("capabilities"))
    battle_objects = as_list(capabilities.get("battle_objects"))
    require(bool(battle_objects), "capabilities.battle_objects must not be empty", failures)
    validate_battle_objects(battle_objects, failures)
    abi_fields = find_abi_fields(capabilities)
    require(
        ABI_FIELDS <= abi_fields,
        f"capabilities must include all battle object ABI fields: {sorted(ABI_FIELDS - abi_fields)}",
        failures,
    )

    feature_gates = as_obj(fixture.get("feature_gates"))
    require(bool(feature_gates), "feature_gates must be an object", failures)
    feature_snapshots = as_obj(fixture.get("feature_snapshots"))
    require(
        REQUIRED_FEATURE_SNAPSHOTS <= set(feature_snapshots.keys()),
        f"feature_snapshots missing fields: {sorted(REQUIRED_FEATURE_SNAPSHOTS - set(feature_snapshots.keys()))}",
        failures,
    )
    validate_strategic_contributions(as_obj(feature_snapshots.get("strategic_map")), feature_gates, failures)
    require(bool(as_obj(fixture.get("disabled_policy"))), "disabled_policy must be an object", failures)
    require(bool(as_obj(fixture.get("rollback"))), "rollback must be an object", failures)
    require(bool(as_obj(fixture.get("quarantine"))), "quarantine must be an object", failures)

    projections = as_obj(fixture.get("projections"))
    require(
        PROJECTION_FIELDS <= set(projections.keys()),
        f"missing projection placeholders: {sorted(PROJECTION_FIELDS - set(projections.keys()))}",
        failures,
    )
    for field in PROJECTION_FIELDS:
        require(bool(as_obj(projections.get(field))), f"{field} must be an object", failures)

    forbidden_hits = scan_forbidden_terms(fixture)
    require(
        not forbidden_hits,
        "forbidden runtime terms found: " + "; ".join(forbidden_hits[:12]),
        failures,
    )

    if failures:
        raise ValueError("\n- ".join(["activated runtime bundle fixture validation failed", *failures]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(load_json_object(args.fixture, label="fixture root"))
    except Exception as exc:  # noqa: BLE001 - CLI validator should stay concise.
        print(f"activated runtime bundle fixture validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"activated runtime bundle fixture validation passed: {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
