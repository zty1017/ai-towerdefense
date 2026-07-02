"""Fixture-backed battle content service.

This service owns the reviewed battle config and runtime package lookup tables.
It keeps node -> package references in one place so frontend mock responses and
research metadata do not drift when MVP battle nodes change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]

_BATTLE_CONFIG_BY_NODE = {
    "gray_lantern_station": _REPO_ROOT / "game_data/demo/first_battle_config.json",
    "lamp_wick_store": _REPO_ROOT / "game_data/demo/wick_store_pressure_battle_config.json",
    "old_signal_tower": _REPO_ROOT / "game_data/demo/old_signal_tower_pressure_battle_config.json",
}

_RUNTIME_PACKAGE_BY_NODE = {
    "gray_lantern_station": _REPO_ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json",
    "lamp_wick_store": _REPO_ROOT / "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json",
    "old_signal_tower": _REPO_ROOT / "examples/runtime_packages/mvp_old_signal_tower.runtime_package.json",
}


class BattleContentNotFoundError(LookupError):
    """Raised when reviewed battle content does not exist for a node."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def available_battle_node_ids() -> list[str]:
    return sorted(set(_BATTLE_CONFIG_BY_NODE) | set(_RUNTIME_PACKAGE_BY_NODE))


def battle_config_paths() -> dict[str, Path]:
    return dict(_BATTLE_CONFIG_BY_NODE)


def runtime_package_paths() -> dict[str, Path]:
    return dict(_RUNTIME_PACKAGE_BY_NODE)


def battle_config_ref(node_id: str) -> str | None:
    path = _BATTLE_CONFIG_BY_NODE.get(node_id)
    if path is None:
        return None
    return _rel(path)


def runtime_package_ref(node_id: str) -> str | None:
    path = _RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None:
        return None
    return _rel(path)


def load_battle_config(node_id: str) -> dict[str, Any]:
    path = _BATTLE_CONFIG_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise BattleContentNotFoundError(node_id)
    return _load_json(path)


def load_runtime_package(node_id: str) -> dict[str, Any]:
    path = _RUNTIME_PACKAGE_BY_NODE.get(node_id)
    if path is None or not path.exists():
        raise BattleContentNotFoundError(node_id)
    return _load_json(path)
