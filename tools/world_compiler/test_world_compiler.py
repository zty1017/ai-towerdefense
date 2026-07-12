from __future__ import annotations

import json
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
    repo_map_output = world_compiler.map_compilation_orchestrator.LAYERED_ROOT / "broken_cloud_bridge"
    assert not repo_map_output.exists()
    output_root = tmp_path / "content" / "generated_worlds"
    result = world_compiler.compile_candidate(
        world_compiler._load(SEED),
        world_compiler._load(CANDIDATE),
        output_root,
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
    assert not repo_map_output.exists()
    assert (tmp_path / "content/generated_world_media/cloud_courier_realm/maps/broken_cloud_bridge").is_dir()
    catalog_path = Path(result["manifest"]["map_runtime_catalog_path"])
    assert catalog_path.is_file()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["entries"][0]["quality_status"] == "candidate"
    from backend.app.services import map_runtime_catalog

    loaded = map_runtime_catalog.load_catalog(catalog_path, tmp_path)
    assert loaded["entries"][0]["node_id"] == "broken_cloud_bridge"
    v01, v02 = map_runtime_catalog.build_package_index([catalog_path], tmp_path)
    assert v01 == {}
    assert v02 == {}


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


def test_provider_loads_explicit_dotenv_before_first_call(tmp_path, monkeypatch):
    dotenv = tmp_path / "authorized.env"
    dotenv.write_text("ARK_API_KEY=test-only-key\n", encoding="utf-8")
    observed = []
    valid = world_compiler._load(CANDIDATE)

    def load(path):
        observed.append(("dotenv", path))
        monkeypatch.setenv("ARK_API_KEY", "test-only-key")

    def complete(*_args, **_kwargs):
        observed.append(("provider", None))
        return {
            "choices": [
                {"message": {"content": json.dumps(valid, ensure_ascii=False)}}
            ]
        }

    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setattr(world_compiler.adapter, "load_dotenv", load)
    monkeypatch.setattr(world_compiler.adapter, "chat_completion", complete)
    world_compiler.generate_candidate(
        world_compiler._load(SEED),
        profile_name="ark_deepseek_v4_flash",
        allow_provider=True,
        dotenv_path=dotenv,
    )
    assert observed[0] == ("dotenv", dotenv)
    assert observed[1][0] == "provider"
