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
        assert "old Chinese courier-station" in by_role["terrain_base"]["prompt_brief"]
        assert by_role["terrain_base"]["prompt_brief"].startswith("Subject:")
        assert "central seventy percent open" in by_role["terrain_base"]["prompt_brief"]
        assert set(by_role["terrain_base"]["prompt_sections"]) == {
            "subject", "environment", "style", "lighting", "composition", "quality"
        }
        assert by_role["terrain_base"]["generation_mode"] == "image_to_image"
        assert by_role["terrain_base"]["generation_reference"]["usage"] == "camera_and_clearance_reference_only"
        assert by_role["terrain_base"]["output_contract"]["size_tier"] == "1K"
        assert by_role["terrain_base"]["output_contract"]["ratio"] == "16:9"
        assert "pure-white studio background" in by_role["road_surface"]["prompt_brief"]
        assert "one single empty low stone-and-timber" in by_role["build_slot_platform"]["prompt_brief"]
        assert by_role["road_surface"]["generation_mode"] == "text_to_image"
        assert by_role["road_surface"]["output_contract"]["transparent"] is True
        assert request_pack["assembly_contract"]["semantic_authority"] == "map_runtime_package"
        assert request_pack["assembly_contract"]["forbid_image_to_semantic_inference"] is True
        resumed = orchestrator.compile_map(input_path, output, resume=True)
        assert resumed["resume"]["reused"] is True
    finally:
        shutil.rmtree(output, ignore_errors=True)


def test_live_visual_stage_batches_all_requests_without_runtime_promotion(tmp_path, monkeypatch):
    output = ROOT / "game_data/media/layered_maps/map_orchestrator_live_test_node"
    input_value = orchestrator._load(INPUT)
    battle = orchestrator._load(ROOT / "game_data/demo/first_battle_config.json")
    style = orchestrator._load(
        ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"
    )
    battle["node_id"] = "map_orchestrator_live_test_node"
    style["node_id"] = "map_orchestrator_live_test_node"
    battle_path = tmp_path / "battle.json"
    style_path = tmp_path / "style.json"
    input_path = tmp_path / "input.json"
    orchestrator._write(battle_path, battle)
    orchestrator._write(style_path, style)
    input_value["battle_config_path"] = str(battle_path)
    input_value["map_style_pack_path"] = str(style_path)
    orchestrator._write(input_path, input_value)
    calls = []

    def fake_closed_loop(_pack_path, pack, output_dir, reviewed_dir, *_profiles, **kwargs):
        calls.append((len(pack["requests"]), kwargs["max_workers"]))
        backdrops = reviewed_dir / "backdrops"
        textures = reviewed_dir / "textures"
        components = reviewed_dir / "components"
        backdrops.mkdir(parents=True, exist_ok=True)
        textures.mkdir(parents=True, exist_ok=True)
        components.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            ROOT / "game_data/media/layered_maps/gray_lantern_station/backdrops/gray_lantern_station.reviewed_painted_backdrop.png",
            backdrops / "map_orchestrator_live_test_node.reviewed_painted_backdrop.png",
        )
        shutil.copy2(
            ROOT / "game_data/media/layered_maps/gray_lantern_station/textures/gray_lantern_station.road_tile.png",
            textures / "road_tile.png",
        )
        shutil.copy2(
            ROOT / "game_data/media/layered_maps/gray_lantern_station/textures/gray_lantern_station.slot_tile.png",
            textures / "slot_tile.png",
        )
        for role in ("objective_foundation", "spawn_marker", "non_blocking_decoration"):
            shutil.copy2(
                ROOT / "game_data/media/layered_maps/gray_lantern_station/textures/gray_lantern_station.slot_tile.png",
                components / f"{role}.png",
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "map_visual_closed_loop_report.v0.1.json"
        report = {
            "schema_version": "map_visual_closed_loop_report.v0.1",
            "node_id": pack["node_id"],
            "worldbook_id": pack["worldbook_id"],
            "status": "runtime_visuals_ready",
            "runtime_critical_roles_ready": True,
            "runtime_critical_roles": ["build_slot_platform", "road_surface", "terrain_base"],
            "summary": {
                "request_count": 6, "passed_count": 6, "failed_count": 0,
                "provider_failure_count": 0, "attempt_count": 6,
                "provider_call_count": 6, "vision_review_call_count": 6,
                "promotion_count": 6,
            },
            "results": [],
            "failures": [],
            "promotions": [],
            "reviewed_backdrop_source_dir": str(backdrops),
            "reviewed_texture_source_dir": str(textures),
            "reviewed_component_source_dir": str(components),
            "policy": {
                "runtime_semantics_source": "MapRuntimePackage",
                "image_to_semantic_inference": False,
                "raw_prompt_stored": False,
                "raw_provider_response_stored": False,
                "automatic_promotion_scope": "reviewed_visual_staging_only",
                "unreviewed_candidate_player_visible": False,
            },
        }
        orchestrator._write(report_path, report)
        return {**report, "report_path": str(report_path)}

    monkeypatch.setattr(orchestrator.image_provider, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(orchestrator.vision_review, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(orchestrator.map_visual_closed_loop, "run_closed_loop", fake_closed_loop)
    shutil.rmtree(output, ignore_errors=True)
    try:
        report = orchestrator.compile_map(input_path, output, live_visuals=True)
        assert calls == [(6, 3)]
        assert report["provider_execution"]["call_count"] == 6
        assert report["provider_execution"]["candidate_generation_status"] == "runtime_visuals_ready"
        assert report["provider_execution"]["reviewed_local_media_imported"] is True
        assert report["provider_execution"]["automatic_reviewed_staging_ready"] is True
        package = orchestrator._load(output / "layered_map_visual_package.v0.1.json")
        media_roles = {item["role"] for item in package["media_assets"]}
        assert {"objective_foundation", "spawn_marker", "non_blocking_decoration"}.issubset(media_roles)
        composite = (output / "composited/map_orchestrator_live_test_node.layered_map.svg").read_text()
        assert 'data-objective-part="reviewed-component"' in composite
        assert 'data-spawn-part="reviewed-component"' in composite
        assert 'data-decoration="reviewed-component"' in composite
    finally:
        shutil.rmtree(output, ignore_errors=True)
