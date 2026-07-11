"""Validate and apply compiled battle objects to one anonymous session.

Activation is an explicit final gate. Generated artifacts remain inert until
this service validates their package, promotion evidence, behavior ABI, and
published media. The stored patch is declarative data; generated code is never
executed by the backend or browser.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from ..db import db_cursor, now_iso


_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUNS_ROOT = Path("/tmp/ai_compiled_td_backend_runs")
_SCHEMA_ROOT = _REPO_ROOT / "shared" / "schemas"
_RUNTIME_PACKAGE_SCHEMA = _SCHEMA_ROOT / "runtime_package.v0.1.schema.json"
_CAPABILITY_SCHEMA = _SCHEMA_ROOT / "battle_object_capability.v0.1.schema.json"
_PROMOTION_SCHEMA = _SCHEMA_ROOT / "provider_artifact_promotion_report.v0.1.schema.json"
_MEDIA_MANIFEST = _REPO_ROOT / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json"
_TRUSTED_WORKFLOWS = {"mvp_mock_asset_compile", "mvp_temporary_trap_delivery"}
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


class RuntimeActivationNotFoundError(LookupError):
    pass


class RuntimeActivationConflictError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _load_hashed_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value, hashlib.sha256(payload).hexdigest()


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_id(value: Any, fallback: str) -> str:
    result = _SAFE_ID_RE.sub("_", str(value or ""))[:128]
    return result or fallback


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _schema_errors(value: dict[str, Any], schema_path: Path) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None) or getattr(
        jsonschema, "Draft7Validator", None
    )
    if validator_cls is None:
        return []
    validator = validator_cls(_load_json(schema_path))
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
        for error in sorted(
            validator.iter_errors(value), key=lambda item: list(item.absolute_path)
        )
    ]


def _runtime_package_errors(package: dict[str, Any]) -> list[str]:
    asset_graph = str(_REPO_ROOT / "tools" / "asset_graph")
    if asset_graph not in sys.path:
        sys.path.insert(0, asset_graph)
    from runtime_package import validate_package  # type: ignore

    return validate_package(package, _load_json(_RUNTIME_PACKAGE_SCHEMA))


def _job_row(session_id: str, job_id: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT job_id, session_id, status, runtime_package_path, trace_paths, "
            "payload, created_at, updated_at FROM research_jobs "
            "WHERE job_id = ? AND session_id = ?",
            (job_id, session_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _job_metadata(row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(row.get("payload") or "{}"))
    except json.JSONDecodeError:
        return {}
    return _json_object(_json_object(payload).get("compiler_metadata"))


def _trace_paths(row: dict[str, Any]) -> list[Path]:
    try:
        values = json.loads(str(row.get("trace_paths") or "[]"))
    except json.JSONDecodeError:
        return []
    return [Path(str(value)) for value in _json_list(values)]


def _trusted_workflow_gate(
    row: dict[str, Any], job_root: Path
) -> tuple[bool, str | None, list[str]]:
    workflow_ids: set[str] = set()
    warnings: list[str] = []
    paths = _trace_paths(row)
    if len(paths) != len(_TRUSTED_WORKFLOWS):
        return False, None, ["trusted workflow trace set is incomplete"]
    for path in paths:
        if not _within(path, job_root) or not path.is_file():
            return False, None, ["trusted workflow trace escaped the job artifact root"]
        try:
            trace = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False, None, ["trusted workflow trace is unreadable"]
        if trace.get("schema_version") != "execution_trace.v0.1":
            return False, None, ["trusted workflow trace schema is not accepted"]
        if trace.get("status") != "passed":
            return False, None, ["trusted workflow trace did not pass"]
        if any(run.get("status") != "passed" for run in _json_list(trace.get("node_runs"))):
            return False, None, ["trusted workflow contains a non-passing node"]
        workflow_ids.add(str(trace.get("workflow_id") or ""))
    if workflow_ids != _TRUSTED_WORKFLOWS:
        return False, None, ["workflow identity does not match the trusted MVP pair"]
    evidence = hashlib.sha256("|".join(sorted(workflow_ids)).encode()).hexdigest()[:24]
    return True, f"trusted_workflows_{evidence}", warnings


def _provider_promotion_gate(
    metadata: dict[str, Any], package_path: Path, package_hash: str, job_root: Path
) -> tuple[bool, str | None, list[str]]:
    runtime_refs = _json_object(metadata.get("runtime_refs"))
    raw_path = runtime_refs.get("promotion_report_path")
    if not raw_path:
        return False, None, ["provider-backed artifact has no promotion report"]
    report_path = Path(str(raw_path))
    if not _within(report_path, job_root) or not report_path.is_file():
        return False, None, ["promotion report is outside the job artifact root"]
    try:
        report = _load_json(report_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False, None, ["promotion report is unreadable"]
    errors = _schema_errors(report, _PROMOTION_SCHEMA)
    if errors:
        return False, None, [f"promotion report schema failed: {errors[0]}"]
    decision = _json_object(report.get("decision"))
    if decision.get("promotion_allowed") is not True:
        return False, None, ["promotion report did not authorize runtime build"]
    target = _json_object(report.get("promotion_targets"))
    if target.get("target_kind") not in {"runtime_package", "runtime_and_world"}:
        return False, None, ["promotion report does not target a runtime package"]
    matched_ref = False
    for ref in _json_list(target.get("runtime_package_refs")):
        ref = _json_object(ref)
        ref_path = Path(str(ref.get("path") or ""))
        if not ref_path.is_absolute():
            ref_path = job_root / ref_path
        if ref_path.resolve() == package_path.resolve() and ref.get("sha256") == package_hash:
            matched_ref = True
            break
    if not matched_ref:
        return False, None, ["promotion report runtime package hash does not match"]
    for gate_name, gate in _json_object(report.get("gate_results")).items():
        gate = _json_object(gate)
        if gate.get("required_before_promotion") and gate.get("status") != "passed":
            return False, None, [f"required promotion gate did not pass: {gate_name}"]
    return True, str(report.get("report_id") or "provider_promotion_report"), []


def _clamp(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))


def _fallback_behavior(asset_kind: str) -> dict[str, Any]:
    if asset_kind == "tower_blueprint":
        return {
            "placement": {"mode": "build_slot", "slot_source": "map_runtime_package.build_slots"},
            "cost": {"resource": "materials", "amount": 18},
            "cooldown": {"milliseconds": 1400},
            "targeting": {"mode": "nearest_path_enemy", "range_cells": 2.8, "line_of_sight": False},
            "effect_blocks": [
                {"effect_id": "compiled_light_damage", "kind": "damage", "amount": 10, "damage_type": "light"},
                {"effect_id": "compiled_light_slow", "kind": "slow", "duration_ms": 1000, "strength": 0.18},
            ],
            "ui_surfaces": ["battle_hotbar", "battle_tooltip", "slot_inspector"],
            "simulation_hooks": ["on_place", "on_attack_tick", "on_wave_end"],
        }
    if asset_kind in {"temporary_trap_sample", "field_device"}:
        return {
            "placement": {"mode": "path_adjacent_or_slot", "slot_source": "map_runtime_package.build_slots"},
            "cost": {"resource": "light", "amount": 10},
            "cooldown": {"milliseconds": 1600},
            "targeting": {"mode": "path_area", "radius_cells": 1.2},
            "effect_blocks": [
                {"effect_id": "compiled_snare_slow", "kind": "slow", "duration_ms": 1800, "strength": 0.32}
            ],
            "ui_surfaces": ["battle_hotbar", "battle_tooltip"],
            "simulation_hooks": ["on_place", "on_enemy_enter_radius", "on_expire"],
        }
    return {
        "placement": {"mode": "free_point", "slot_source": "battle_canvas", "allowed_area": "visible_battlefield"},
        "cost": {"resource": "materials", "amount": 12},
        "cooldown": {"milliseconds": 6000},
        "targeting": {"mode": "area_point", "radius_cells": 2},
        "effect_blocks": [
            {"effect_id": "compiled_support_aura", "kind": "aura", "duration_ms": 4500, "strength": 0.22}
        ],
        "ui_surfaces": ["battle_hotbar", "battle_tooltip"],
        "simulation_hooks": ["on_use", "on_tick", "on_expire"],
        "active_duration_ms": 4500,
    }


def _normalize_behavior(value: dict[str, Any], asset_kind: str) -> dict[str, Any]:
    if value.get("schema_version") == "battle_behavior_abi.v0.1":
        value = _json_object(value.get("behavior_abi"))
    if all(key in value for key in ("placement", "cost", "cooldown", "targeting", "effect_blocks")):
        placement = _json_object(value.get("placement"))
        placement_mode = str(placement.get("mode") or "")
        if placement_mode not in {
            "build_slot", "path_adjacent_or_slot", "free_point", "path_area", "area_point"
        }:
            raise ValueError("behavior ABI placement mode is not allowlisted")
        default_slot_source = (
            "battle_canvas" if placement_mode in {"free_point", "area_point"}
            else "map_runtime_package.build_slots"
        )
        slot_source = str(placement.get("slot_source") or default_slot_source)
        if slot_source not in {"map_runtime_package.build_slots", "battle_canvas"}:
            raise ValueError("behavior ABI slot source is not allowlisted")
        normalized_placement: dict[str, Any] = {
            "mode": placement_mode,
            "slot_source": slot_source,
        }
        required_tags = [
            _safe_id(item, "tag")[:64]
            for item in _json_list(placement.get("required_tags"))[:8]
        ]
        if required_tags:
            normalized_placement["required_tags"] = list(dict.fromkeys(required_tags))
        allowed_area = placement.get("allowed_area")
        if allowed_area is not None:
            if allowed_area not in {"visible_battlefield", "path_adjacent", "build_slots"}:
                raise ValueError("behavior ABI allowed area is not allowlisted")
            normalized_placement["allowed_area"] = allowed_area

        cost = _json_object(value.get("cost"))
        resource = str(cost.get("resource") or "materials")
        if resource not in {"materials", "light", "power", "electricity"}:
            raise ValueError("behavior ABI resource is not allowlisted")
        cooldown = _json_object(value.get("cooldown"))
        targeting = _json_object(value.get("targeting"))
        targeting_mode = str(targeting.get("mode") or "none")
        if targeting_mode not in {"nearest_path_enemy", "path_area", "area_point", "none"}:
            raise ValueError("behavior ABI targeting mode is not allowlisted")
        normalized_targeting: dict[str, Any] = {"mode": targeting_mode}
        for field in ("range_cells", "radius_cells"):
            if targeting.get(field) is not None:
                normalized_targeting[field] = _clamp(targeting[field], 1, 0.3, 8)
        if targeting.get("line_of_sight") is not None:
            normalized_targeting["line_of_sight"] = bool(targeting["line_of_sight"])

        effects: list[dict[str, Any]] = []
        for index, raw_effect in enumerate(_json_list(value.get("effect_blocks"))[:8]):
            raw_effect = _json_object(raw_effect)
            kind = str(raw_effect.get("kind") or "")
            if kind not in {"damage", "slow", "aura", "reveal"}:
                raise ValueError("behavior ABI effect kind is not allowlisted")
            effect: dict[str, Any] = {
                "effect_id": _safe_id(raw_effect.get("effect_id"), f"compiled_effect_{index}"),
                "kind": kind,
            }
            if kind == "damage":
                effect["amount"] = _clamp(raw_effect.get("amount"), 8, 0, 320)
                damage_type = str(raw_effect.get("damage_type") or "light")
                effect["damage_type"] = damage_type if damage_type in {"light", "physical", "arcane"} else "light"
            if kind == "slow":
                effect["duration_ms"] = int(_clamp(raw_effect.get("duration_ms"), 1200, 0, 15000))
                effect["strength"] = _clamp(raw_effect.get("strength"), 0.2, 0, 1)
            if kind in {"aura", "reveal"}:
                if raw_effect.get("duration_ms") is not None:
                    effect["duration_ms"] = int(_clamp(raw_effect["duration_ms"], 1000, 0, 15000))
                if raw_effect.get("strength") is not None:
                    effect["strength"] = _clamp(raw_effect["strength"], 0.2, 0, 1)
            if raw_effect.get("radius_cells") is not None:
                effect["radius_cells"] = _clamp(raw_effect["radius_cells"], 1, 0.3, 8)
            effects.append(effect)
        if not effects:
            raise ValueError("behavior ABI has no executable effect block")

        allowed_surfaces = {"battle_hotbar", "battle_tooltip", "slot_inspector"}
        raw_surfaces = _json_list(value.get("ui_surfaces")) or ["battle_hotbar", "battle_tooltip"]
        if any(surface not in allowed_surfaces for surface in raw_surfaces):
            raise ValueError("behavior ABI UI surface is not allowlisted")
        allowed_hooks = {
            "on_place", "on_attack_tick", "on_wave_end", "on_enemy_enter_radius",
            "on_tick", "on_expire", "on_use",
        }
        raw_hooks = _json_list(value.get("simulation_hooks")) or ["on_place", "on_tick"]
        if any(hook not in allowed_hooks for hook in raw_hooks):
            raise ValueError("behavior ABI simulation hook is not allowlisted")
        result = {
            "placement": normalized_placement,
            "cost": {
                "resource": resource,
                "amount": _clamp(cost.get("amount"), 0, 0, 999),
            },
            "cooldown": {
                "milliseconds": int(_clamp(cooldown.get("milliseconds"), 0, 0, 120000)),
            },
            "targeting": normalized_targeting,
            "effect_blocks": effects,
            "ui_surfaces": list(dict.fromkeys(map(str, raw_surfaces))),
            "simulation_hooks": list(dict.fromkeys(map(str, raw_hooks))),
        }
        if value.get("active_duration_ms") is not None:
            result["active_duration_ms"] = int(
                _clamp(value["active_duration_ms"], 0, 0, 15000)
            )
        return result

    gameplay = _json_object(value.get("gameplay")) or value
    stats = _json_object(gameplay.get("base_stats"))
    effects: list[dict[str, Any]] = []
    for index, raw in enumerate(_json_list(gameplay.get("effect_blocks"))):
        raw = _json_object(raw)
        kind = str(raw.get("kind") or raw.get("effect_type") or raw.get("type") or "")
        if kind in {"area_damage", "damage"}:
            effects.append({
                "effect_id": _safe_id(raw.get("effect_id"), f"compiled_damage_{index}"),
                "kind": "damage",
                "amount": _clamp(raw.get("amount", raw.get("damage")), 8, 0, 320),
                "damage_type": str(raw.get("damage_type") or "light") if str(raw.get("damage_type") or "light") in {"light", "physical", "arcane"} else "light",
            })
        elif kind == "slow":
            effects.append({
                "effect_id": _safe_id(raw.get("effect_id"), f"compiled_slow_{index}"),
                "kind": "slow",
                "duration_ms": int(_clamp(raw.get("duration_ms"), 1200, 0, 15000)),
                "strength": _clamp(raw.get("strength", raw.get("ratio")), 0.2, 0, 1),
            })
        elif kind in {"aura", "aura_buff"}:
            effects.append({
                "effect_id": _safe_id(raw.get("effect_id"), f"compiled_aura_{index}"),
                "kind": "aura",
                "duration_ms": int(_clamp(raw.get("duration_ms"), 4000, 0, 15000)),
                "strength": _clamp(raw.get("strength", raw.get("ratio")), 0.2, 0, 1),
            })
    if not effects:
        raise ValueError("compiled gameplay has no supported effect block")
    fallback = _fallback_behavior(asset_kind)
    fallback["effect_blocks"] = effects
    cost = stats.get("cost", stats.get("build_cost", stats.get("deploy_cost")))
    fallback["cost"]["amount"] = _clamp(cost, fallback["cost"]["amount"], 0, 999)
    fallback["cooldown"]["milliseconds"] = int(
        _clamp(stats.get("cooldown_ms"), fallback["cooldown"]["milliseconds"], 0, 120000)
    )
    if "range" in stats:
        fallback["targeting"]["range_cells"] = _clamp(stats.get("range"), 2.5, 0.3, 8)
    return fallback


def _gameplay_behavior(asset: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    ref = _json_object(asset.get("gameplay_ref"))
    raw_path = str(ref.get("path") or "")
    if not raw_path:
        raise ValueError("gameplay ref path is missing")
    raw = Path(raw_path)
    candidates = [raw] if raw.is_absolute() else [artifact_root / raw, _REPO_ROOT / raw]
    allowed_roots = (
        artifact_root,
        _REPO_ROOT / "game_data/compiled_assets",
        _REPO_ROOT / "examples/compiled_assets",
    )
    path = next(
        (
            candidate.resolve()
            for candidate in candidates
            if candidate.is_file()
            and any(_within(candidate, allowed_root) for allowed_root in allowed_roots)
        ),
        None,
    )
    if path is None:
        raise ValueError("gameplay ref is not a local file")
    expected = str(ref.get("sha256") or "")
    behavior_payload, behavior_hash = _load_hashed_json(path)
    if expected != behavior_hash:
        raise ValueError("gameplay ref hash mismatch")
    return _normalize_behavior(
        behavior_payload, str(asset.get("asset_kind") or "")
    )


def _media_item(asset_id: str, roles: tuple[str, ...]) -> dict[str, Any] | None:
    for item in _json_list(_load_json(_MEDIA_MANIFEST).get("items")):
        item = _json_object(item)
        if item.get("asset_id") == asset_id and item.get("media_role") in roles:
            return item
    return None


def _fallback_media(asset_kind: str) -> dict[str, Any]:
    if asset_kind == "tower_blueprint":
        asset_id, sprite_roles = "asset_light_slow_tower_001", ("tower_sprite",)
    elif asset_kind in {"temporary_trap_sample", "field_device"}:
        asset_id, sprite_roles = "asset_mirror_lure_trap_001", ("item_sprite", "icon")
    else:
        asset_id, sprite_roles = "asset_signal_wick_decoy", ("item_sprite", "ui_card", "icon")
    icon = _media_item(asset_id, ("icon", "ui_card"))
    sprite = _media_item(asset_id, sprite_roles)
    if icon is None or sprite is None:
        raise ValueError("reviewed fallback media is unavailable")
    return {
        "icon": {
            "url": icon["url"],
            "width": int(icon["width"]),
            "height": int(icon["height"]),
            "sha256": icon["sha256"],
        },
        "sprite": {
            "texture_key": f"activated_{asset_id}",
            "image": sprite["url"],
        },
    }


def _published_path(url: str) -> Path | None:
    prefixes = {
        "/assets/frontend_mock/processed/": _REPO_ROOT / "game_data/media/frontend_mock/processed",
        "/assets/frontend_runtime_mock/processed/": _REPO_ROOT / "game_data/media/frontend_runtime_mock/processed",
    }
    for prefix, root in prefixes.items():
        if url.startswith(prefix):
            candidate = root / url.removeprefix(prefix)
            return candidate if _within(candidate, root) else None
    return None


def _package_media(asset: dict[str, Any]) -> dict[str, Any]:
    media = _json_object(asset.get("media_refs"))
    icon = _json_object(media.get("icon"))
    sprite = _json_object(media.get("sprite"))
    icon_path = _published_path(str(icon.get("url") or ""))
    sprite_path = _published_path(str(sprite.get("image") or ""))
    if not icon_path or not icon_path.is_file() or _sha256_file(icon_path) != icon.get("sha256"):
        raise ValueError("runtime icon is not a hash-matched published asset")
    if not sprite_path or not sprite_path.is_file():
        raise ValueError("runtime sprite is not a published asset")
    return {"icon": icon, "sprite": sprite}


def _build_capability(
    asset: dict[str, Any], *, activation_id: str, package: dict[str, Any],
    package_hash: str, artifact_root: Path, allow_reviewed_fallback: bool,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    warnings: list[str] = []
    gate_status = {"behavior": "passed", "media": "passed"}
    asset_kind = str(asset.get("asset_kind") or "")
    if asset_kind not in {
        "tower_blueprint", "temporary_trap_sample", "support_item", "field_device"
    }:
        raise ValueError("runtime asset kind is not an executable battle capability")
    try:
        behavior = _gameplay_behavior(asset, artifact_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if not allow_reviewed_fallback:
            raise ValueError(str(exc)) from exc
        behavior = _fallback_behavior(asset_kind)
        gate_status["behavior"] = "degraded"
        warnings.append("trusted MVP package used the reviewed safe behavior template")
    try:
        media = _package_media(asset)
    except (OSError, ValueError) as exc:
        if not allow_reviewed_fallback:
            raise ValueError(str(exc)) from exc
        media = _fallback_media(asset_kind)
        gate_status["media"] = "degraded"
        warnings.append("trusted MVP package used reviewed published fallback media")
    lifecycle_state = str(asset.get("lifecycle_state") or "ephemeral")
    availability = _json_object(asset.get("battle_availability"))
    uses = int(_clamp(availability.get("uses_per_battle"), 2, 1, 99))
    requires_delivery = availability.get("requires_delivery") is True
    capability: dict[str, Any] = {
        "schema_version": "battle_object_capability.v0.1",
        "object_id": _safe_id(asset.get("stable_internal_id"), "activated_object"),
        "display_name": str(_json_object(asset.get("display")).get("name") or "临时装置")[:120],
        "asset_kind": asset_kind,
        "lifecycle": {
            "deployable": True,
            "upgradeable": lifecycle_state == "stabilized_blueprint",
            "stacking": "limited_charges" if lifecycle_state == "ephemeral" else "single_per_slot",
            "expires": lifecycle_state == "ephemeral",
            **({"max_uses": uses} if lifecycle_state == "ephemeral" or requires_delivery else {}),
        },
        "behavior_abi": behavior,
        "media_refs": media,
        "source_runtime_ref": {
            "package_id": str(package.get("package_id") or "runtime_package"),
            "package_sha256": package_hash,
            "activation_id": activation_id,
        },
    }
    if requires_delivery:
        capability["tool_id"] = "sample"
    errors = _schema_errors(capability, _CAPABILITY_SCHEMA)
    if errors:
        raise ValueError(f"battle object capability failed: {errors[0]}")
    return capability, warnings, gate_status


def _activation_id(session_id: str, source_kind: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{session_id}:{source_kind}:{source_id}".encode()).hexdigest()
    return f"runtime_activation_{digest[:24]}"


def _existing_activation(session_id: str, source_kind: str, source_id: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM runtime_activations WHERE session_id = ? AND source_kind = ? AND source_id = ?",
            (session_id, source_kind, source_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _store_activation(
    *, activation_id: str, session_id: str, source_kind: str, source_id: str,
    status: str, receipt: dict[str, Any], battle_objects: list[dict[str, Any]], created_at: str,
) -> None:
    payload = json.dumps(
        {"receipt": receipt, "runtime_patch": {"battle_objects": battle_objects}},
        ensure_ascii=False,
    )
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO runtime_activations "
            "(activation_id, session_id, source_kind, source_id, status, payload, created_at, updated_at, rolled_back_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL) "
            "ON CONFLICT(session_id, source_kind, source_id) DO UPDATE SET "
            "status = excluded.status, payload = excluded.payload, updated_at = excluded.updated_at, rolled_back_at = NULL",
            (activation_id, session_id, source_kind, source_id, status, payload, created_at, receipt["updated_at"]),
        )


def _receipt_shell(
    *, activation_id: str, session_id: str, source_kind: str, source_id: str,
    package_id: str, package_hash: str, created_at: str, updated_at: str,
) -> dict[str, Any]:
    blocked = {"status": "blocked", "reason": "gate has not passed"}
    return {
        "schema_version": "runtime_activation_receipt.v0.1",
        "activation_id": activation_id,
        "session_id": session_id,
        "source": {
            "kind": source_kind,
            "source_id": source_id,
            "runtime_package_id": package_id,
            "runtime_package_sha256": package_hash,
        },
        "status": "blocked",
        "created_at": created_at,
        "updated_at": updated_at,
        "validation": {
            "package_schema": dict(blocked),
            "runtime_safety": dict(blocked),
            "semantic": dict(blocked),
            "behavior_abi": dict(blocked),
            "media": dict(blocked),
        },
        "promotion": {"mode": "trusted_deterministic_workflow", "status": "blocked", "evidence_id": None},
        "runtime_effect": {
            "applied": False,
            "scope": "anonymous_session",
            "activated_object_ids": [],
            "replaced_object_ids": [],
        },
        "warnings": [],
        "blocked_reasons": [],
        "rollback": {"supported": True, "status": "not_applicable", "rolled_back_at": None},
        "safety": {
            "reads_env_file": False,
            "calls_provider": False,
            "stores_raw_prompt": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "player_runtime_mutation_count": 0,
        },
    }


def _active_object_ids(
    session_id: str, exclude_source_kind: str, exclude_source_id: str
) -> set[str]:
    ids: set[str] = set()
    with db_cursor() as cur:
        cur.execute(
            "SELECT source_kind, source_id, payload FROM runtime_activations "
            "WHERE session_id = ? AND status = 'activated'",
            (session_id,),
        )
        rows = cur.fetchall()
    for row in rows:
        if (
            row.get("source_kind") == exclude_source_kind
            and row.get("source_id") == exclude_source_id
        ):
            continue
        try:
            payload = json.loads(row.get("payload") or "{}")
        except json.JSONDecodeError:
            continue
        for item in _json_list(_json_object(payload.get("runtime_patch")).get("battle_objects")):
            object_id = _json_object(item).get("object_id")
            if object_id:
                ids.add(str(object_id))
    return ids


def apply_runtime_package(
    session_id: str,
    *,
    source_kind: str,
    source_id: str,
    package_path: Path,
    allowed_root: Path,
    expected_package_sha256: str | None,
    promotion_mode: str,
    promotion_evidence_id: str | None,
    promotion_ok: bool,
    allow_reviewed_fallback: bool = False,
    allow_session_rebind: bool = False,
    preflight_blocked_reasons: list[str] | None = None,
    preflight_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Apply one already-authorized package through the shared final gate.

    Callers own provenance checks. This gate independently revalidates the
    immutable package hash, runtime schema, session scope, executable ABI, and
    published media before writing a session patch.
    """

    if source_kind not in {"research_job", "generation_schedule"}:
        raise ValueError("runtime activation source kind is not allowlisted")
    if promotion_mode not in {
        "trusted_deterministic_workflow",
        "provider_promotion_report",
    }:
        raise ValueError("runtime activation promotion mode is not allowlisted")

    activation_id = _activation_id(session_id, source_kind, source_id)
    existing = _existing_activation(session_id, source_kind, source_id)
    if existing and existing.get("status") == "activated":
        return _json_object(json.loads(existing["payload"])).get("receipt", {})
    timestamp = now_iso()
    created_at = str(existing.get("created_at")) if existing else timestamp
    package_path_safe = _within(package_path, allowed_root)
    package: dict[str, Any] = {}
    package_hash = "0" * 64
    package_id = "unavailable_runtime_package"
    if package_path_safe and package_path.is_file():
        try:
            package, package_hash = _load_hashed_json(package_path)
            package_id = str(package.get("package_id") or package_id)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            package = {}
    receipt = _receipt_shell(
        activation_id=activation_id,
        session_id=session_id,
        source_kind=source_kind,
        source_id=source_id,
        package_id=package_id,
        package_hash=package_hash,
        created_at=created_at,
        updated_at=timestamp,
    )
    blocked = list(preflight_blocked_reasons or [])
    warnings = list(preflight_warnings or [])
    if not package_path_safe or not package_path.is_file():
        blocked.append("runtime package is outside the authorized artifact root")
    if not package:
        blocked.append("runtime package is unreadable")
    if (
        expected_package_sha256
        and package_hash != expected_package_sha256
    ):
        blocked.append("runtime package hash changed after authorization")
    package_errors = _runtime_package_errors(package) if package else []
    if package_errors:
        blocked.append(f"runtime package validation failed: {package_errors[0]}")
    else:
        receipt["validation"]["package_schema"] = {"status": "passed", "reason": "runtime package v0.1 validated"}
        receipt["validation"]["runtime_safety"] = {"status": "passed", "reason": "runtime package safety scan passed"}

    receipt["promotion"] = {
        "mode": promotion_mode,
        "status": "passed" if promotion_ok else "blocked",
        "evidence_id": promotion_evidence_id,
    }
    capabilities: list[dict[str, Any]] = []
    gate_statuses: list[dict[str, str]] = []
    if not package_errors and package and promotion_ok:
        if allow_session_rebind and package.get("session_id") != session_id:
            warnings.append(
                "trusted MVP fixture package session was rebound by the activation gate"
            )
        elif package.get("session_id") != session_id:
            blocked.append("provider-backed runtime package session does not match")
        for raw_asset in _json_list(package.get("assets")):
            try:
                capability, item_warnings, item_gates = _build_capability(
                    _json_object(raw_asset),
                    activation_id=activation_id,
                    package=package,
                    package_hash=package_hash,
                    artifact_root=package_path.parent,
                    allow_reviewed_fallback=allow_reviewed_fallback,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                blocked.append(str(exc))
                continue
            capabilities.append(capability)
            warnings.extend(item_warnings)
            gate_statuses.append(item_gates)
    if promotion_ok and not capabilities:
        blocked.append("runtime package produced no executable battle capability")

    if blocked:
        receipt["blocked_reasons"] = list(dict.fromkeys(blocked))[:32]
        receipt["warnings"] = list(dict.fromkeys(warnings))[:32]
        receipt_errors = _schema_errors(
            receipt,
            _SCHEMA_ROOT / "runtime_activation_receipt.v0.1.schema.json",
        )
        if receipt_errors:
            raise RuntimeActivationConflictError(receipt_errors[0])
        _store_activation(
            activation_id=activation_id,
            session_id=session_id,
            source_kind=source_kind,
            source_id=source_id,
            status="blocked",
            receipt=receipt,
            battle_objects=[],
            created_at=created_at,
        )
        return receipt

    behavior_degraded = any(item["behavior"] == "degraded" for item in gate_statuses)
    media_degraded = any(item["media"] == "degraded" for item in gate_statuses)
    receipt["validation"]["semantic"] = {"status": "passed", "reason": "asset kind and runtime surface are allowlisted"}
    receipt["validation"]["behavior_abi"] = {
        "status": "degraded" if behavior_degraded else "passed",
        "reason": "reviewed safe ABI fallback applied" if behavior_degraded else "compiled behavior ABI validated",
    }
    receipt["validation"]["media"] = {
        "status": "degraded" if media_degraded else "passed",
        "reason": "reviewed published media fallback applied" if media_degraded else "published media refs validated",
    }
    object_ids = [item["object_id"] for item in capabilities]
    replaced = sorted(
        set(object_ids)
        & _active_object_ids(session_id, source_kind, source_id)
    )
    receipt["status"] = "activated"
    receipt["warnings"] = list(dict.fromkeys(warnings))[:32]
    receipt["blocked_reasons"] = []
    receipt["runtime_effect"] = {
        "applied": True,
        "scope": "anonymous_session",
        "activated_object_ids": object_ids,
        "replaced_object_ids": replaced,
    }
    receipt["rollback"] = {"supported": True, "status": "available", "rolled_back_at": None}
    receipt["safety"]["player_runtime_mutation_count"] = 1
    receipt_errors = _schema_errors(receipt, _SCHEMA_ROOT / "runtime_activation_receipt.v0.1.schema.json")
    if receipt_errors:
        raise RuntimeActivationConflictError(receipt_errors[0])
    _store_activation(
        activation_id=activation_id,
        session_id=session_id,
        source_kind=source_kind,
        source_id=source_id,
        status="activated",
        receipt=receipt,
        battle_objects=capabilities,
        created_at=created_at,
    )
    return receipt


def activate_research_job(session_id: str, job_id: str) -> dict[str, Any]:
    row = _job_row(session_id, job_id)
    if row is None:
        raise RuntimeActivationNotFoundError(job_id)
    job_root = _RUNS_ROOT / session_id / job_id
    package_path = Path(str(row.get("runtime_package_path") or ""))
    package_path_safe = _within(package_path, job_root) and package_path.is_file()
    package_hash = _sha256_file(package_path) if package_path_safe else "0" * 64
    blocked: list[str] = []
    if row.get("status") != "completed":
        blocked.append("research job is not completed")

    metadata = _job_metadata(row)
    generation = _json_object(metadata.get("generation"))
    provider_backed = generation.get("provider_call_performed") is True
    trusted, trusted_evidence, trusted_errors = _trusted_workflow_gate(row, job_root)
    if trusted and not provider_backed:
        promotion_mode = "trusted_deterministic_workflow"
        promotion_ok = True
        promotion_evidence = trusted_evidence
    else:
        promotion_mode = "provider_promotion_report"
        promotion_ok, promotion_evidence, provider_errors = _provider_promotion_gate(
            metadata, package_path, package_hash, job_root
        )
        if not promotion_ok:
            blocked.extend(trusted_errors + provider_errors)

    runtime_refs = _json_object(metadata.get("runtime_refs"))
    reviewed_fallback_allowed = (
        provider_backed
        and promotion_ok
        and runtime_refs.get("reviewed_media_fallback_allowed") is True
    )

    return apply_runtime_package(
        session_id,
        source_kind="research_job",
        source_id=job_id,
        package_path=package_path,
        allowed_root=job_root,
        expected_package_sha256=package_hash if package_path_safe else None,
        promotion_mode=promotion_mode,
        promotion_evidence_id=promotion_evidence,
        promotion_ok=promotion_ok,
        allow_reviewed_fallback=trusted or reviewed_fallback_allowed,
        allow_session_rebind=trusted and not provider_backed,
        preflight_blocked_reasons=blocked,
    )


def list_activation_receipts(session_id: str) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM runtime_activations WHERE session_id = ? ORDER BY created_at, activation_id",
            (session_id,),
        )
        rows = cur.fetchall()
    receipts: list[dict[str, Any]] = []
    for row in rows:
        try:
            receipt = _json_object(json.loads(row.get("payload") or "{}")).get("receipt")
        except json.JSONDecodeError:
            continue
        if isinstance(receipt, dict):
            receipts.append(receipt)
    return receipts


def active_runtime_patches(session_id: str) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT activation_id, payload FROM runtime_activations "
            "WHERE session_id = ? AND status = 'activated' ORDER BY created_at, activation_id",
            (session_id,),
        )
        rows = cur.fetchall()
    patches: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = _json_object(json.loads(row.get("payload") or "{}"))
        except json.JSONDecodeError:
            continue
        patch = _json_object(payload.get("runtime_patch"))
        patches.append({"activation_id": row["activation_id"], **patch})
    return patches


def rollback_activation(session_id: str, activation_id: str) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT status, payload, created_at FROM runtime_activations "
            "WHERE activation_id = ? AND session_id = ?",
            (activation_id, session_id),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeActivationNotFoundError(activation_id)
    payload = _json_object(json.loads(row.get("payload") or "{}"))
    receipt = _json_object(payload.get("receipt"))
    if row.get("status") == "rolled_back":
        return receipt
    if row.get("status") != "activated":
        raise RuntimeActivationConflictError("only an activated runtime patch can be rolled back")
    timestamp = now_iso()
    receipt["status"] = "rolled_back"
    receipt["updated_at"] = timestamp
    receipt["runtime_effect"]["applied"] = False
    receipt["safety"]["player_runtime_mutation_count"] = 1
    receipt["rollback"] = {"supported": True, "status": "applied", "rolled_back_at": timestamp}
    payload["receipt"] = receipt
    with db_cursor() as cur:
        cur.execute(
            "UPDATE runtime_activations SET status = 'rolled_back', payload = ?, "
            "updated_at = ?, rolled_back_at = ? WHERE activation_id = ? AND session_id = ?",
            (json.dumps(payload, ensure_ascii=False), timestamp, timestamp, activation_id, session_id),
        )
    return receipt
