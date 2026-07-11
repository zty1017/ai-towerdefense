from __future__ import annotations

import shutil
from pathlib import Path

from tools.asset_graph import map_compilation_orchestrator as orchestrator


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "examples/map_compilation_inputs/long_night_first_battle.map_compilation_input.json"
OUTPUT = ROOT / "game_data/media/layered_maps/gray_lantern_station"


def test_plan_is_side_effect_free():
    result = orchestrator.plan(INPUT, OUTPUT)
    assert result["node_id"] == "gray_lantern_station"
    assert result["provider_calls"] == 0
    assert result["provider_handoff_requested"] is True


def test_compile_and_resume(tmp_path):
    output = ROOT / "game_data/media/layered_maps/map_orchestrator_test_node"
    input_value = orchestrator._load(INPUT)
    battle = orchestrator._load(ROOT / "game_data/demo/first_battle_config.json")
    style = orchestrator._load(
        ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"
    )
    battle["node_id"] = "map_orchestrator_test_node"
    style["node_id"] = "map_orchestrator_test_node"
    battle_path = tmp_path / "battle.json"
    style_path = tmp_path / "style.json"
    input_path = tmp_path / "input.json"
    orchestrator._write(battle_path, battle)
    orchestrator._write(style_path, style)
    input_value["battle_config_path"] = str(battle_path)
    input_value["map_style_pack_path"] = str(style_path)
    orchestrator._write(input_path, input_value)
    shutil.rmtree(output, ignore_errors=True)
    try:
        first = orchestrator.compile_map(input_path, output)
        assert first["status"] == "completed"
        assert first["quality"]["runtime_truth_preserved"] is True
        assert first["provider_execution"]["handoff_status"] == "request_pack_ready_review_only"
        handoff_dir = output / "visual_handoff"
        request_pack = orchestrator._load(
            handoff_dir / "map_layered_visual_generation_request_pack.v0.1.json"
        )
        assert request_pack["node_id"] == "map_orchestrator_test_node"
        assert len(request_pack["requests"]) == 6
        by_role = {item["role"]: item for item in request_pack["requests"]}
        assert "old chinese post station" in by_role["terrain_base"]["prompt_brief"]
        assert "do not paint roads" in by_role["terrain_base"]["prompt_brief"]
        assert by_role["road_surface"]["output_contract"]["transparent"] is True
        assert request_pack["assembly_contract"]["semantic_authority"] == "map_runtime_package"
        assert request_pack["assembly_contract"]["forbid_image_to_semantic_inference"] is True
        resumed = orchestrator.compile_map(input_path, output, resume=True)
        assert resumed["resume"]["reused"] is True
    finally:
        shutil.rmtree(output, ignore_errors=True)
