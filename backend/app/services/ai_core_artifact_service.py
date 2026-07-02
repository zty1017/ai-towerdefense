"""Fixture-backed AI compilation core artifact service.

This service owns the MVP references for ContextPackage, FactEntry, CGOP, and
WorldStateDeltaTransaction examples. These artifacts are evidence and schema
boundary fixtures, not player-facing text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]

_CONTEXT_PACKAGE_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
)
_FACT_ENTRY_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_gray_lantern.fact_entry.json"
)
_CGOP_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json"
)
_WORLD_DELTA_TRANSACTION_EXAMPLE = (
    _REPO_ROOT
    / "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json"
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def core_artifact_refs() -> dict[str, str]:
    return {
        "context_package": _rel(_CONTEXT_PACKAGE_EXAMPLE),
        "fact_entry": _rel(_FACT_ENTRY_EXAMPLE),
        "compiled_game_object_package": _rel(_CGOP_EXAMPLE),
        "world_delta_transaction": _rel(_WORLD_DELTA_TRANSACTION_EXAMPLE),
    }


def load_world_delta_transaction() -> dict[str, Any]:
    return _load_json(_WORLD_DELTA_TRANSACTION_EXAMPLE)


def core_artifact_payload() -> dict[str, Any]:
    return {
        "status": "field_boundary_examples_ready",
        "refs": core_artifact_refs(),
        "context_package": _load_json(_CONTEXT_PACKAGE_EXAMPLE),
        "fact_entry": _load_json(_FACT_ENTRY_EXAMPLE),
        "compiled_game_object_package": _load_json(_CGOP_EXAMPLE),
        "world_delta_transaction": load_world_delta_transaction(),
    }
