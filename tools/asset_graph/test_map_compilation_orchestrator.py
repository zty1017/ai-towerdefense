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
        resumed = orchestrator.compile_map(input_path, output, resume=True)
        assert resumed["resume"]["reused"] is True
    finally:
        shutil.rmtree(output, ignore_errors=True)

