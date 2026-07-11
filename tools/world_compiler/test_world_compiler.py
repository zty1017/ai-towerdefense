from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.world_compiler import world_compiler


ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "examples/world_seeds/cloud_mechanism_frontier.world_seed.json"
CANDIDATE = ROOT / "examples/world_candidates/compiler_test.generated_world_candidate.json"


def test_seed_and_candidate_validate():
    assert world_compiler.validate_seed(world_compiler._load(SEED)) == []
    assert world_compiler.validate_candidate(world_compiler._load(CANDIDATE)) == []


def test_candidate_lowers_to_complete_world_package(tmp_path):
    result = world_compiler.compile_candidate(
        world_compiler._load(SEED),
        world_compiler._load(CANDIDATE),
        tmp_path,
        provenance={
            "generation_mode": "test_fixture",
            "provider_call_performed": False,
            "raw_prompt_stored": False,
            "raw_response_stored": False,
        },
        compile_map=False,
    )
    manifest = result["manifest"]
    assert manifest["world_id"] == "cloud_courier_realm"
    assert manifest["activation"]["world_catalog_ready"] is True
    required = {
        "worldbook", "world_instance_config", "opening", "initial_map",
        "first_crisis_node", "first_battle_config", "map_style_pack",
        "candidate", "map_compilation_input",
    }
    assert required <= set(manifest["artifacts"])
    battle = json.loads(Path(manifest["artifacts"]["first_battle_config"]).read_text())
    assert battle["node_id"] == "broken_cloud_bridge"
    assert len(battle["paths"][0]["waypoints"]) == 6
    style = json.loads(Path(manifest["artifacts"]["map_style_pack"]).read_text())
    assert style["source_refs"]["style_authority"] == "reviewed_ai_proposal"


def test_provider_path_requires_explicit_flag():
    try:
        world_compiler.generate_candidate(
            world_compiler._load(SEED),
            profile_name="ark_deepseek_v4_flash",
            allow_provider=False,
        )
    except world_compiler.WorldCompilationError as exc:
        assert "--allow-provider" in str(exc)
    else:
        raise AssertionError("provider path must remain guarded")


def test_compiled_world_can_drive_map_pipeline(tmp_path):
    map_output = world_compiler.map_compilation_orchestrator.LAYERED_ROOT / "broken_cloud_bridge"
    shutil.rmtree(map_output, ignore_errors=True)
    try:
        result = world_compiler.compile_candidate(
            world_compiler._load(SEED),
            world_compiler._load(CANDIDATE),
            tmp_path,
            provenance={
                "generation_mode": "test_fixture",
                "provider_call_performed": False,
                "raw_prompt_stored": False,
                "raw_response_stored": False,
            },
            compile_map=True,
        )
        map_report = result["manifest"]["map_compilation_report"]
        assert map_report["status"] == "completed"
        assert map_report["node_id"] == "broken_cloud_bridge"
        assert map_report["quality"]["runtime_truth_preserved"] is True
    finally:
        shutil.rmtree(map_output, ignore_errors=True)


def test_provider_candidate_gets_one_bounded_repair(monkeypatch):
    valid = world_compiler._load(CANDIDATE)
    invalid = {"schema_version": "generated_world_candidate.v0.1"}
    responses = iter([invalid, valid])
    profile = world_compiler.adapter.PROFILES["ark_deepseek_v4_flash"]
    monkeypatch.setenv(profile.env_key, "test-only-key")
    monkeypatch.setattr(world_compiler.adapter, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(
        world_compiler.adapter,
        "chat_completion",
        lambda *_args, **_kwargs: {
            "choices": [{"message": {"content": json.dumps(next(responses), ensure_ascii=False)}}]
        },
    )
    candidate, provenance = world_compiler.generate_candidate(
        world_compiler._load(SEED),
        profile_name="ark_deepseek_v4_flash",
        allow_provider=True,
    )
    assert candidate["world_id"] == "cloud_courier_realm"
    assert provenance["attempt_count"] == 2
