#!/usr/bin/env python3
"""Check current MapRenderPlan service and frontend mock contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import frontend_mock_service, map_render_plan_service  # noqa: E402


EXPECTED_ALL_NODES = {
    "gray_lantern_station": "render_plan_gray_lantern_station_v0_1",
    "lamp_wick_store": "render_plan_lamp_wick_store_v0_1",
    "old_signal_tower": "render_plan_old_signal_tower_v0_1",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_bundle(node_id: str, expected_plan_id: str | None = None) -> dict[str, Any]:
    bundle = map_render_plan_service.load_map_render_plan_bundle(node_id)
    plan = bundle.get("procedural_map_render_plan")
    report = bundle.get("semantic_visual_consistency_report")
    require(isinstance(plan, dict), f"{node_id}: procedural_map_render_plan must be object")
    require(isinstance(report, dict), f"{node_id}: semantic_visual_consistency_report must be object")
    require(plan.get("schema_version") == "procedural_map_render_plan.v0.1", f"{node_id}: schema mismatch")
    require(report.get("status") == "passed", f"{node_id}: semantic report must be passed")
    require(
        "debug_control_overlay" not in list(plan.get("player_default_layer_ids") or []),
        f"{node_id}: debug layer must not be player-default",
    )
    if expected_plan_id is not None:
        require(plan.get("plan_id") == expected_plan_id, f"{node_id}: plan_id mismatch")
    payload = frontend_mock_service.get_battle_config("smoke_session", node_id)
    payload_bundle = payload.get("map_render_plan_bundle")
    require(isinstance(payload_bundle, dict), f"{node_id}: battle config missing map_render_plan_bundle")
    payload_plan = payload_bundle.get("procedural_map_render_plan")
    require(isinstance(payload_plan, dict), f"{node_id}: payload plan must be object")
    if expected_plan_id is not None:
        require(payload_plan.get("plan_id") == expected_plan_id, f"{node_id}: payload plan_id mismatch")
    return {"node_id": node_id, "plan_id": plan.get("plan_id")}


def check_gray_node() -> dict[str, Any]:
    return {"mode": "gray-node", "nodes": [check_bundle("gray_lantern_station")]}


def check_all_nodes() -> dict[str, Any]:
    available = map_render_plan_service.available_map_render_plan_node_ids()
    require(available == sorted(EXPECTED_ALL_NODES), f"available node ids mismatch: {available}")
    return {
        "mode": "all-nodes",
        "nodes": [
            check_bundle(node_id, expected_plan_id)
            for node_id, expected_plan_id in EXPECTED_ALL_NODES.items()
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("gray-node", "all-nodes"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = check_gray_node() if args.mode == "gray-node" else check_all_nodes()
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"map render plan service contract check failed: {exc}", file=sys.stderr)
        return 1
    print(
        "map render plan service contract check passed: "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
