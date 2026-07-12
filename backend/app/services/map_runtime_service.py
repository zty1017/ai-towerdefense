"""Fixture-backed MapRuntimePackage service.

MapRuntimePackage is the battle map runtime contract. This service owns the
node -> reviewed package mapping and keeps map package loading separate from
the broader frontend fixture service.

Node registration is driven by a strict Map Runtime Catalog (see
``map_runtime_catalog.py``) instead of hardcoded Python constants, so future
AI-compiled maps can register without editing this module. The public function
surface is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .map_runtime_catalog import (
    MapRuntimeCatalogError,
    build_package_index,
    discover_catalog_paths,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MAP_RUNTIME_ACTIVATION_AUTHORIZATION_REPORT = (
    _REPO_ROOT
    / "examples/review_packs/map_runtime_activation_authorization_report.v0.1.json"
)

try:
    _MAP_RUNTIME_PACKAGE_BY_NODE, _MAP_RUNTIME_PACKAGE_V02_BY_NODE = build_package_index(
        discover_catalog_paths(_REPO_ROOT), _REPO_ROOT
    )
except MapRuntimeCatalogError as exc:
    raise RuntimeError(f"map runtime catalog validation failed: {exc}") from exc


class MapRuntimePackageNotFoundError(LookupError):
    """Raised when a node does not have a reviewed runtime map package."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _semantic_counts(map_package: dict[str, Any]) -> dict[str, int]:
    return {
        "resource_node_count": len(map_package.get("resource_nodes") or []),
        "hazard_zone_count": len(map_package.get("hazard_zones") or []),
        "defense_anchor_count": len(map_package.get("defense_anchors") or []),
        "blocked_area_count": len(map_package.get("blocked_areas") or []),
    }


def _authorization_for_node(
    node_id: str, authorization_report_path: Path | None = None
) -> dict[str, Any] | None:
    path = authorization_report_path or _MAP_RUNTIME_ACTIVATION_AUTHORIZATION_REPORT
    if not path.exists():
        return None
    report = _load_json(path)
    for node in report.get("nodes") or []:
        if isinstance(node, dict) and node.get("node_id") == node_id:
            return node
    return None


def _runtime_summary(map_package: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": map_package.get("package_id"),
        "schema_version": map_package.get("schema_version"),
        "node_id": map_package.get("node_id"),
        "path_route_count": len(map_package.get("path_routes") or []),
        "build_slot_count": len(map_package.get("build_slots") or []),
        "spawn_point_count": len(map_package.get("spawn_points") or []),
        "objective_count": len(map_package.get("objectives") or []),
        "strong_semantic_counts": _semantic_counts(map_package),
    }


def _path_ref(path: Path) -> str:
    return (
        path.relative_to(_REPO_ROOT).as_posix()
        if path.is_relative_to(_REPO_ROOT)
        else str(path)
    )


def _authorization_report_ref(authorization_report_path: Path | None = None) -> str:
    return _path_ref(authorization_report_path or _MAP_RUNTIME_ACTIVATION_AUTHORIZATION_REPORT)


def _authorization_matches_candidate(
    authorization: dict[str, Any] | None,
    candidate_package: dict[str, Any] | None,
) -> bool:
    if not authorization or not candidate_package:
        return False
    candidate_target = authorization.get("target_candidate") or {}
    if not isinstance(candidate_target, dict):
        return False
    return (
        candidate_target.get("to_package_id") == candidate_package.get("package_id")
        and candidate_target.get("to_schema_version") == candidate_package.get("schema_version")
    )


def _authorization_activates_candidate(
    authorization: dict[str, Any] | None,
    candidate_package: dict[str, Any] | None,
) -> bool:
    return (
        _authorization_matches_candidate(authorization, candidate_package)
        and authorization is not None
        and authorization.get("authorization_status") == "approved_for_gate_review"
        and authorization.get("activation_authorized_for_gate") is True
    )


def map_runtime_activation_selection(
    node_id: str,
    authorization_report_path: Path | None = None,
) -> dict[str, Any]:
    """Return the developer-controlled default runtime selection for a node."""
    default_package = load_map_runtime_package(node_id)
    candidate_package = load_map_runtime_package_v02_optional(node_id)
    authorization = _authorization_for_node(node_id, authorization_report_path)
    target_matches = _authorization_matches_candidate(authorization, candidate_package)
    use_v02 = _authorization_activates_candidate(authorization, candidate_package)
    selected_package = candidate_package if use_v02 and candidate_package else default_package
    fallback_reasons: list[str] = []
    if not candidate_package:
        fallback_reasons.append("v02_candidate_missing")
    if authorization is None:
        fallback_reasons.append("developer_authorization_record_missing")
    elif authorization.get("authorization_status") != "approved_for_gate_review":
        fallback_reasons.append("developer_authorization_not_approved")
    elif not target_matches:
        fallback_reasons.append("developer_authorization_target_mismatch")

    return {
        "node_id": node_id,
        "selection_mode": "developer_authorization_selector",
        "selected_schema_version": selected_package.get("schema_version"),
        "selected_package_id": selected_package.get("package_id"),
        "selected_runtime_family": "v0.2"
        if selected_package.get("schema_version") == "map_runtime_package.v0.2"
        else "v0.1",
        "activation_applied": bool(use_v02),
        "fallback_reasons": fallback_reasons,
        "authorization": {
            "report_path": _authorization_report_ref(authorization_report_path),
            "record_present": authorization is not None,
            "authorization_status": (authorization or {}).get("authorization_status"),
            "authorization_decision": (authorization or {}).get("authorization_decision"),
            "activation_authorized_for_gate": (authorization or {}).get(
                "activation_authorized_for_gate"
            )
            is True,
            "target_matches_candidate": target_matches,
        },
        "selected_runtime_summary": _runtime_summary(selected_package),
        "candidate_runtime_summary": _runtime_summary(candidate_package)
        if candidate_package
        else None,
        "safety": {
            "reads_env": False,
            "provider_call_count": 0,
            "world_state_mutation": False,
            "review_only_visual_candidate_consumed": False,
            "strong_semantic_source": "MapRuntimePackage"
            if use_v02
            else "MapRuntimePackage v0.1",
        },
    }


def available_map_runtime_node_ids() -> list[str]:
    return sorted(_MAP_RUNTIME_PACKAGE_BY_NODE)


def map_runtime_package_paths() -> dict[str, Path]:
    return dict(_MAP_RUNTIME_PACKAGE_BY_NODE)


def map_runtime_package_v02_paths() -> dict[str, Path]:
    return dict(_MAP_RUNTIME_PACKAGE_V02_BY_NODE)


def map_runtime_package_ref(node_id: str) -> str | None:
    path = _MAP_RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None:
        return None
    return path.relative_to(_REPO_ROOT).as_posix()


def map_runtime_package_v02_ref(node_id: str) -> str | None:
    path = _MAP_RUNTIME_PACKAGE_V02_BY_NODE.get(node_id)
    if path is None:
        return None
    return path.relative_to(_REPO_ROOT).as_posix()


def load_map_runtime_package(node_id: str) -> dict[str, Any]:
    path = _MAP_RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise MapRuntimePackageNotFoundError(node_id)
    return _load_json(path)


def load_map_runtime_package_v02(node_id: str) -> dict[str, Any]:
    path = _MAP_RUNTIME_PACKAGE_V02_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise MapRuntimePackageNotFoundError(node_id)
    return _load_json(path)


def load_map_runtime_package_optional(node_id: str) -> dict[str, Any] | None:
    try:
        return load_map_runtime_package(node_id)
    except MapRuntimePackageNotFoundError:
        return None


def load_selected_map_runtime_package(
    node_id: str,
    authorization_report_path: Path | None = None,
) -> dict[str, Any]:
    selection = map_runtime_activation_selection(node_id, authorization_report_path)
    if selection.get("selected_schema_version") == "map_runtime_package.v0.2":
        return load_map_runtime_package_v02(node_id)
    return load_map_runtime_package(node_id)


def load_selected_map_runtime_package_optional(
    node_id: str,
    authorization_report_path: Path | None = None,
) -> dict[str, Any] | None:
    try:
        return load_selected_map_runtime_package(node_id, authorization_report_path)
    except MapRuntimePackageNotFoundError:
        return None


def load_map_runtime_package_v02_optional(node_id: str) -> dict[str, Any] | None:
    try:
        return load_map_runtime_package_v02(node_id)
    except MapRuntimePackageNotFoundError:
        return None


def get_map_runtime_v02_opt_in_contract(
    session_id: str,
    node_id: str,
    authorization_report_path: Path | None = None,
) -> dict[str, Any]:
    default_package = load_map_runtime_package(node_id)
    candidate_package = load_map_runtime_package_v02(node_id)
    authorization = _authorization_for_node(node_id, authorization_report_path)
    candidate_target = (authorization or {}).get("target_candidate") or {}
    target_matches = (
        candidate_target.get("to_package_id") == candidate_package.get("package_id")
        and candidate_target.get("to_schema_version") == candidate_package.get("schema_version")
    )
    authorized_for_gate = (
        authorization is not None
        and authorization.get("authorization_status") == "approved_for_gate_review"
        and authorization.get("activation_authorized_for_gate") is True
        and target_matches
    )
    opt_in_candidate: dict[str, Any] = {
        "candidate_available": authorized_for_gate,
        "candidate_package_summary": _runtime_summary(candidate_package),
        "candidate_runtime_package_v02": candidate_package if authorized_for_gate else None,
    }
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "dry_run_mode": "review_only_map_v02_opt_in_contract",
        "review_only": True,
        "runtime_activation_allowed": False,
        "default_runtime_mutation_performed": False,
        "usage_policy": [
            "review_only",
            "not_player_runtime",
            "does_not_modify_default_map_runtime_package",
            "requires_activation_gate_before_default_runtime_use",
        ],
        "authorization": {
            "report_path": _authorization_report_ref(authorization_report_path),
            "record_present": authorization is not None,
            "authorization_status": (authorization or {}).get("authorization_status"),
            "authorization_decision": (authorization or {}).get("authorization_decision"),
            "activation_authorized_for_gate": authorized_for_gate,
            "target_matches_candidate": target_matches,
        },
        "default_runtime": {
            "preserved": default_package.get("schema_version") == "map_runtime_package.v0.1",
            "package_summary": _runtime_summary(default_package),
            "v02_field_leak_count": sum(
                1
                for key in (
                    "resource_nodes",
                    "hazard_zones",
                    "defense_anchors",
                    "blocked_areas",
                )
                if key in default_package
            ),
        },
        "opt_in_candidate": opt_in_candidate,
        "safety": {
            "reads_env": False,
            "provider_call_count": 0,
            "player_default_runtime_mutation": False,
            "world_state_mutation": False,
        },
    }


def get_map_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    selection = map_runtime_activation_selection(node_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "map_runtime_package": load_selected_map_runtime_package(node_id),
        "runtime_selection": selection,
    }
