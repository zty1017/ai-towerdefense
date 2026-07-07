#!/usr/bin/env python3
"""Build the deterministic MapTemplateCatalog v0.1 example."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.asset_graph.validate_map_template_catalog import validate


DEFAULT_OUTPUT = ROOT / "examples/map_template_catalogs/mvp_map_template_catalog.v0.1.json"
GENERATED_AT = "2026-07-07T00:00:00+00:00"
REQUIRED_TEMPLATE_IDS = [
    "s_curve_single_path",
    "two_lane_merge",
    "zigzag_long_path",
    "short_pressure_path",
    "central_loop",
]


def semantic_hooks(
    *,
    resource: str,
    hazard: str,
    defense: str,
    blocking: str,
    blocking_allowed: bool = False,
) -> dict[str, Any]:
    return {
        "resource": {"allowed": True, "rules_summary": resource},
        "hazard": {"allowed": True, "rules_summary": hazard},
        "defense": {"allowed": True, "rules_summary": defense},
        "blocking": {"allowed": blocking_allowed, "rules_summary": blocking},
    }


def template(
    *,
    template_id: str,
    label: str,
    description: str,
    topology_kind: str,
    uses: list[str],
    min_width: int,
    min_height: int,
    aspect: str,
    grid_notes: str,
    road_width: float,
    routes: list[dict[str, Any]],
    route_notes: str,
    slot_summary: str,
    preferred_zones: list[str],
    avoid_zones: list[str],
    hooks: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": template_id,
        "display_label": label,
        "description": description,
        "topology_kind": topology_kind,
        "recommended_node_uses": uses,
        "grid_constraints": {
            "min_width_cells": min_width,
            "min_height_cells": min_height,
            "preferred_aspect": aspect,
            "notes": grid_notes,
        },
        "route_blueprint": {
            "coordinate_space": "normalized_0_1",
            "suggested_road_width_normalized": road_width,
            "routes": routes,
            "notes": route_notes,
        },
        "slot_strategy": {
            "summary": slot_summary,
            "preferred_zones": preferred_zones,
            "avoid_zones": avoid_zones,
        },
        "semantic_hooks": hooks,
        "usage_policy": [
            "developer_side_candidate_only",
            "not_runtime_fact_source",
            "requires_map_runtime_package_build_and_review",
            "no_image_to_logic_inference",
        ],
    }


def route(route_id: str, role: str, points: list[tuple[float, float]]) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "role": role,
        "normalized_control_points": [{"x": x, "y": y} for x, y in points],
    }


def build_catalog() -> dict[str, Any]:
    templates = [
        template(
            template_id="s_curve_single_path",
            label="S 形单路推进",
            description="一条从左到右缓慢摆动的主路，适合教学、首战或低压节点。",
            topology_kind="single_path",
            uses=["tutorial_battle", "early_campaign_node", "readability_first"],
            min_width=10,
            min_height=7,
            aspect="wide_16_9_or_4_3",
            grid_notes="需要横向空间表达两次缓弯，入口和目标端保留安全边。",
            road_width=0.09,
            routes=[
                route(
                    "main",
                    "single_enemy_route",
                    [(0.05, 0.72), (0.22, 0.62), (0.38, 0.32), (0.58, 0.38), (0.78, 0.68), (0.95, 0.48)],
                )
            ],
            route_notes="控制点只表达候选形状；正式 waypoints 必须由 MapRuntimePackage builder/review 生成。",
            slot_summary="塔位沿两个外侧弯道错开布置，让玩家学习覆盖转角和直道。",
            preferred_zones=["outer_curve_shoulders", "midfield_crossfire", "late_route_hold"],
            avoid_zones=["route_band", "spawn_clearance", "objective_clearance"],
            hooks=semantic_hooks(
                resource="允许在第二个弯道外侧放小型资源点，但不得压住主路。",
                hazard="允许低强度沿路减速或雾潮提示，需保持教学可读性。",
                defense="允许在弯道外侧和终点前设置防守锚点。",
                blocking="默认禁止阻挡区改变单路可读性；任何阻挡必须在 runtime 包中显式审核。",
            ),
        ),
        template(
            template_id="two_lane_merge",
            label="双路汇合压力",
            description="上下两条入口线在中段汇合为一条主压路线，适合制造选择和汇火点。",
            topology_kind="merge_path",
            uses=["mid_campaign_pressure", "split_spawn_intro", "merge_crossfire_test"],
            min_width=12,
            min_height=8,
            aspect="wide",
            grid_notes="需要上下入口留白，中段汇合点不能贴近目标区。",
            road_width=0.075,
            routes=[
                route("upper_lane", "upper_entry_to_merge", [(0.04, 0.25), (0.22, 0.26), (0.38, 0.42), (0.52, 0.50)]),
                route("lower_lane", "lower_entry_to_merge", [(0.04, 0.78), (0.24, 0.74), (0.40, 0.58), (0.52, 0.50)]),
                route("merged_lane", "merged_route_to_objective", [(0.52, 0.50), (0.68, 0.48), (0.82, 0.38), (0.96, 0.48)]),
            ],
            route_notes="多 route 只表达拓扑候选；正式 spawn、route id 和合流语义必须由 runtime package 审核。",
            slot_summary="汇合点两侧布置高价值塔位，入口段布置低价值早期减压位。",
            preferred_zones=["merge_crossfire", "upper_lower_balanced_shoulders", "post_merge_hold"],
            avoid_zones=["merge_center", "dual_spawn_clearance", "objective_clearance"],
            hooks=semantic_hooks(
                resource="允许在较弱入口侧放资源诱因，但不得让资源点阻断合流读取。",
                hazard="允许在合流后短段放 hazard，避免上下入口同时被遮挡。",
                defense="允许合流点外圈有核心防守锚点。",
                blocking="禁止在合流点中心放阻挡；阻挡只可作为 runtime 审核后的边缘地形。",
            ),
        ),
        template(
            template_id="zigzag_long_path",
            label="长折线路径",
            description="长距离折线路径提供更多转角和持续输出窗口，适合耐久战或资源管理节点。",
            topology_kind="zigzag_path",
            uses=["attrition_battle", "resource_management", "long_lane_mastery"],
            min_width=11,
            min_height=9,
            aspect="wide_or_square",
            grid_notes="需要足够纵深，折线之间至少留出一格以上的非道路区域。",
            road_width=0.07,
            routes=[
                route(
                    "main",
                    "long_zigzag_route",
                    [(0.05, 0.18), (0.28, 0.18), (0.28, 0.78), (0.50, 0.78), (0.50, 0.28), (0.72, 0.28), (0.72, 0.70), (0.95, 0.70)],
                )
            ],
            route_notes="折线数量应在正式构建时按 grid 和塔位 footprint 复核，避免道路相互贴边。",
            slot_summary="每个折角外侧给一个中价值平台，长直道旁给低价值持续输出位。",
            preferred_zones=["outer_elbows", "long_straight_shoulders", "late_turn_focus"],
            avoid_zones=["parallel_road_gap", "tight_inner_corners", "spawn_clearance"],
            hooks=semantic_hooks(
                resource="允许把资源点放在长直道外侧，要求与塔位、道路留出明确间距。",
                hazard="允许在单个折角绑定机关，禁止全路段高压堆叠。",
                defense="允许多个防守锚点分段出现，避免所有锚点集中在终点。",
                blocking="禁止在折线间缝隙放会误读成可建造平台的阻挡物。",
            ),
        ),
        template(
            template_id="short_pressure_path",
            label="短线高压推进",
            description="入口到目标距离短，留给玩家的反应窗口少，适合精英波或限时压力节点。",
            topology_kind="pressure_path",
            uses=["elite_wave", "timer_pressure", "compact_arena"],
            min_width=8,
            min_height=6,
            aspect="compact_wide",
            grid_notes="目标区、出生点和道路宽度要被强制分离，避免短线变成不可读直冲。",
            road_width=0.1,
            routes=[
                route("main", "short_pressure_route", [(0.06, 0.58), (0.24, 0.50), (0.45, 0.43), (0.68, 0.46), (0.94, 0.40)])
            ],
            route_notes="适合少量控制点；正式 runtime 应额外检查目标区安全距离。",
            slot_summary="塔位数量少但价值高，优先放在中段和目标前的侧翼。",
            preferred_zones=["midline_flanks", "objective_approach_shoulders"],
            avoid_zones=["spawn_to_mid_choke", "objective_core", "route_band"],
            hooks=semantic_hooks(
                resource="通常不建议资源点；若需要，只允许放在远离目标的一侧。",
                hazard="允许小范围高压机关，但必须保留清晰反制塔位。",
                defense="允许目标前防守锚点，作为短线压迫的主要解法。",
                blocking="禁止阻挡缩短或遮蔽本已很短的路线。",
            ),
        ),
        template(
            template_id="central_loop",
            label="中央环绕路线",
            description="路线围绕中央区域形成环形压力，适合表现据点防守或多方向包围感。",
            topology_kind="loop_path",
            uses=["hold_the_center", "encirclement_battle", "boss_or_event_node"],
            min_width=12,
            min_height=9,
            aspect="wide_or_square",
            grid_notes="中央区必须足够大以容纳目标、资源或防守主题，但不得让路线闭环成为 runtime 隐式循环。",
            road_width=0.08,
            routes=[
                route(
                    "main",
                    "looping_route_to_objective",
                    [(0.05, 0.52), (0.22, 0.24), (0.50, 0.18), (0.78, 0.28), (0.84, 0.62), (0.62, 0.82), (0.34, 0.72), (0.92, 0.50)],
                )
            ],
            route_notes="这是环绕式候选，不表示敌人可无限循环；正式 runtime 仍必须有明确终点。",
            slot_summary="中央外缘少量强塔位，环外侧放补充塔位，避免目标被完全包围不可见。",
            preferred_zones=["central_outer_ring", "late_loop_exit", "entry_arc_shoulders"],
            avoid_zones=["central_objective_core", "route_overlap", "loop_exit_choke"],
            hooks=semantic_hooks(
                resource="允许中央区资源或目标主题，但必须由 runtime package 明确语义和 footprint。",
                hazard="允许在环路一段设置事件 hazard，不允许整圈持续遮挡。",
                defense="允许中央防守锚点和环外补位，要求目标可读。",
                blocking="允许边缘装饰性阻挡候选，但不得把环路视觉误导为碰撞事实。",
                blocking_allowed=True,
            ),
        ),
    ]
    return {
        "schema_version": "map_template_catalog.v0.1",
        "catalog_id": "mvp_map_template_catalog_v0_1",
        "generated_at": GENERATED_AT,
        "source_policy": {
            "catalog_role": "developer_side_template_candidate_seed_catalog",
            "runtime_fact_source": False,
            "player_default_runtime": False,
            "image_to_logic_inference_allowed": False,
            "may_modify_map_runtime_package": False,
        },
        "summary": {
            "template_count": len(templates),
            "required_template_ids": REQUIRED_TEMPLATE_IDS,
        },
        "templates": templates,
        "usage_policy": [
            "developer_side_candidate_only",
            "not_runtime_fact_source",
            "requires_map_runtime_package_build_and_review",
            "cannot_replace_map_runtime_package",
            "no_image_to_logic_inference",
        ],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate", action="store_true", help="Validate the built catalog before exiting.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = build_catalog()
    if args.validate:
        validate(catalog)
    write_json(args.output, catalog)
    print(f"map template catalog written: {args.output}")
    if args.validate:
        print("map template catalog validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
