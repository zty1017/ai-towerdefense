import shutil
from pathlib import Path

from app.services import world_catalog_service
from tools.asset_graph import map_compile_package
from tools.world_compiler import world_compiler


ROOT = Path(__file__).resolve().parents[2]


def _session(client) -> str:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


def test_world_catalog_exposes_ready_default(client):
    response = client.get("/api/world-catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["schema_version"] == "world_catalog.v0.1"
    assert catalog["default_world_id"] == "long_night_lanterns"
    default = next(item for item in catalog["worlds"] if item["world_id"] == "long_night_lanterns")
    assert default["status"] == "ready"
    assert default["world_config"]["worldbook_template_id"] == "long_night_lanterns"


def test_world_instance_returns_runtime_bundle(client):
    session_id = _session(client)
    response = client.post(
        f"/api/sessions/{session_id}/world-instance",
        json={"world_id": "long_night_lanterns", "selected_options": {}},
    )
    assert response.status_code == 201
    payload = response.json()["payload"]
    assert payload["world_bundle"]["catalog_entry"]["entry_node_id"] == "gray_lantern_station"
    assert payload["world_bundle"]["map_runtime_package"]["schema_version"] == "map_runtime_package.v0.2"


def test_world_instance_rejects_unknown_world(client):
    session_id = _session(client)
    response = client.post(
        f"/api/sessions/{session_id}/world-instance",
        json={"world_id": "missing_world", "selected_options": {}},
    )
    assert response.status_code == 404


def test_generated_world_runs_catalog_to_battle_and_research(client, monkeypatch):
    generated_root = ROOT / "content/generated_worlds_test"
    generated_media_root = ROOT / "content/generated_worlds_test_media"
    map_output = ROOT / "game_data/media/layered_maps/broken_cloud_bridge"
    shutil.rmtree(generated_root, ignore_errors=True)
    shutil.rmtree(generated_media_root, ignore_errors=True)
    shutil.rmtree(map_output, ignore_errors=True)
    try:
        compiled = world_compiler.compile_candidate(
            world_compiler._load(
                ROOT / "examples/world_seeds/cloud_mechanism_frontier.world_seed.json"
            ),
            world_compiler._load(
                ROOT / "examples/world_candidates/compiler_test.generated_world_candidate.json"
            ),
            generated_root,
            provenance={
                "generation_mode": "test_fixture",
                "provider_call_performed": False,
                "raw_prompt_stored": False,
                "raw_response_stored": False,
            },
            compile_map=True,
        )
        assert compiled["manifest"]["map_compilation_report"]["status"] == "completed"
        monkeypatch.setattr(world_catalog_service, "GENERATED_ROOT", generated_root)

        catalog = client.get("/api/world-catalog").json()
        generated = next(
            item for item in catalog["worlds"] if item["world_id"] == "cloud_courier_realm"
        )
        assert generated["status"] == "ready"

        session_id = _session(client)
        created = client.post(
            f"/api/sessions/{session_id}/world-instance",
            json={"world_id": "cloud_courier_realm", "selected_options": {}},
        )
        assert created.status_code == 201, created.text
        bundle = created.json()["payload"]["world_bundle"]
        assert bundle["battle_config"]["node_id"] == "broken_cloud_bridge"

        route = client.get(f"/api/sessions/{session_id}/campaign-router")
        assert route.status_code == 200
        assert route.json()["payload"]["campaign_router"]["current"]["node_id"] == "broken_cloud_bridge"
        battle = client.get(
            f"/api/sessions/{session_id}/battles/broken_cloud_bridge/config"
        )
        assert battle.status_code == 200, battle.text
        assert battle.json()["payload"]["map_runtime_package"]["schema_version"] == "map_runtime_package.v0.2"

        proposal = client.post(
            f"/api/sessions/{session_id}/research/proposals",
            json={
                "intent_text": "做一座借风势击退敌群的临时机关塔",
                "node_id": "broken_cloud_bridge",
            },
        )
        assert proposal.status_code == 201, proposal.text
        assert proposal.json()["compiler_metadata"]["context_package"]["worldbook_id"] == "cloud_courier_realm"
    finally:
        shutil.rmtree(generated_root, ignore_errors=True)
        shutil.rmtree(generated_media_root, ignore_errors=True)
        shutil.rmtree(map_output, ignore_errors=True)


def test_generated_map_node_binding_accepts_isolated_root_but_rejects_escapes():
    check = map_compile_package._is_node_bound_layered_path
    assert check(
        "content/generated_worlds_test_media/demo/maps/node_a/composited.png",
        "node_a",
        url=False,
    )
    assert not check("/tmp/demo/maps/node_a/composited.png", "node_a", url=False)
    assert not check(
        "content/generated_worlds_test_media/../maps/node_a/composited.png",
        "node_a",
        url=False,
    )
