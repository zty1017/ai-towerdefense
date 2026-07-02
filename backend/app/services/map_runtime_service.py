"""Fixture-backed MapRuntimePackage service.

MapRuntimePackage is the battle map runtime contract. This service owns the
node -> reviewed package mapping and keeps map package loading separate from
the broader frontend fixture service.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]

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


class MapRuntimePackageNotFoundError(LookupError):
    """Raised when a node does not have a reviewed runtime map package."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def available_map_runtime_node_ids() -> list[str]:
    return sorted(_MAP_RUNTIME_PACKAGE_BY_NODE)


def map_runtime_package_paths() -> dict[str, Path]:
    return dict(_MAP_RUNTIME_PACKAGE_BY_NODE)


def map_runtime_package_ref(node_id: str) -> str | None:
    path = _MAP_RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None:
        return None
    return path.relative_to(_REPO_ROOT).as_posix()


def load_map_runtime_package(node_id: str) -> dict[str, Any]:
    path = _MAP_RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise MapRuntimePackageNotFoundError(node_id)
    return _load_json(path)


def load_map_runtime_package_optional(node_id: str) -> dict[str, Any] | None:
    try:
        return load_map_runtime_package(node_id)
    except MapRuntimePackageNotFoundError:
        return None


def get_map_runtime_package(session_id: str, node_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "map_runtime_package": load_map_runtime_package(node_id),
    }
