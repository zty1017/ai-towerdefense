"""Fixture-backed procedural map render plan service.

The render plan bundle is presentation-side evidence for logic-first maps:
MapRuntimePackage remains gameplay truth, while ProceduralMapRenderPlan and
SemanticVisualConsistencyReport describe how strong semantics are rendered and
checked. This service never reads `.env` and never calls providers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]

_MAP_RENDER_PLAN_BY_NODE = {
    "gray_lantern_station": {
        "map_style_pack": (
            _REPO_ROOT
            / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"
        ),
        "procedural_map_render_plan": (
            _REPO_ROOT
            / "examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json"
        ),
        "semantic_visual_consistency_report": (
            _REPO_ROOT
            / "examples/semantic_visual_consistency_reports/"
            "mvp_first_battle.semantic_visual_consistency_report.json"
        ),
    },
    "lamp_wick_store": {
        "map_style_pack": (
            _REPO_ROOT
            / "examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json"
        ),
        "procedural_map_render_plan": (
            _REPO_ROOT
            / "examples/map_render_plans/"
            "mvp_wick_store_pressure.procedural_map_render_plan.json"
        ),
        "semantic_visual_consistency_report": (
            _REPO_ROOT
            / "examples/semantic_visual_consistency_reports/"
            "mvp_wick_store_pressure.semantic_visual_consistency_report.json"
        ),
    },
    "old_signal_tower": {
        "map_style_pack": (
            _REPO_ROOT
            / "examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json"
        ),
        "procedural_map_render_plan": (
            _REPO_ROOT
            / "examples/map_render_plans/"
            "mvp_old_signal_tower_pressure.procedural_map_render_plan.json"
        ),
        "semantic_visual_consistency_report": (
            _REPO_ROOT
            / "examples/semantic_visual_consistency_reports/"
            "mvp_old_signal_tower_pressure.semantic_visual_consistency_report.json"
        ),
    },
}


class MapRenderPlanNotFoundError(LookupError):
    """Raised when a node does not have a reviewed render plan bundle."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def available_map_render_plan_node_ids() -> list[str]:
    return sorted(_MAP_RENDER_PLAN_BY_NODE)


def map_render_plan_refs(node_id: str) -> dict[str, str] | None:
    paths = _MAP_RENDER_PLAN_BY_NODE.get(node_id)
    if paths is None:
        return None
    return {key: _rel(path) for key, path in paths.items()}


def load_map_render_plan_bundle(node_id: str) -> dict[str, Any]:
    paths = _MAP_RENDER_PLAN_BY_NODE.get(node_id)
    if paths is None:
        raise MapRenderPlanNotFoundError(node_id)
    missing = [key for key, path in paths.items() if not path.exists()]
    if missing:
        raise MapRenderPlanNotFoundError(f"{node_id}: missing {', '.join(missing)}")
    return {
        "node_id": node_id,
        "refs": {key: _rel(path) for key, path in paths.items()},
        "map_style_pack": _load_json(paths["map_style_pack"]),
        "procedural_map_render_plan": _load_json(paths["procedural_map_render_plan"]),
        "semantic_visual_consistency_report": _load_json(
            paths["semantic_visual_consistency_report"]
        ),
    }


def load_map_render_plan_bundle_optional(node_id: str) -> dict[str, Any] | None:
    try:
        return load_map_render_plan_bundle(node_id)
    except MapRenderPlanNotFoundError:
        return None


def get_map_render_plan_bundle(session_id: str, node_id: str) -> dict[str, Any]:
    bundle = load_map_render_plan_bundle(node_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "node_id": node_id,
        "map_render_plan_bundle": bundle,
    }
