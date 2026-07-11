from pathlib import Path

from tools.media import generate_layered_map_visual_candidates as generator
from tools.media import image_provider


def request_pack() -> dict:
    return {
        "schema_version": generator.PACK_VERSION,
        "node_id": "gray_lantern_station",
        "worldbook_id": "long_night_lanterns",
        "requests": [
            {
                "request_id": "terrain_request",
                "role": "terrain_base",
                "prompt_brief": "clean terrain only",
                "output_contract": {"width": 1280, "height": 720},
                "required_gates": ["visual_review"],
            },
            {
                "request_id": "road_request",
                "role": "road_surface",
                "prompt_brief": "road atlas only",
                "output_contract": {"width": 1024, "height": 1024},
                "required_gates": ["alignment_review"],
            },
        ],
    }


def test_role_selection_and_dry_run_sidecar(tmp_path: Path):
    pack = request_pack()
    selected = generator.selected_requests(pack, ["road_surface"])
    assert [item["role"] for item in selected] == ["road_surface"]
    pack_path = tmp_path / "pack.json"
    generator.write_json(pack_path, pack)
    result = generator.run_request(
        pack_path,
        pack,
        selected[0],
        tmp_path / "candidates",
        image_provider.PROFILES["agnes_image_flash"],
        size_override=None,
        timeout=1,
        live=False,
    )
    assert result["provider_called_this_run"] is False
    assert result["image_exists"] is False
    sidecar = generator.load_json(Path(result["sidecar_path"]))
    assert sidecar["size"] == "1024x1024"
    assert sidecar["safety"]["stores_raw_prompt"] is False
    assert sidecar["promotion_allowed_now"] is False


def test_report_counts_review_only_results(tmp_path: Path):
    report = generator.build_report(
        request_pack_path=tmp_path / "pack.json",
        output_dir=tmp_path,
        profile=image_provider.PROFILES["agnes_image_flash"],
        live=True,
        results=[
            {
                "status": "candidate_needs_visual_and_alignment_review",
                "provider_called_this_run": True,
                "image_exists": True,
            }
        ],
        failures=[],
    )
    assert report["status"] == "completed_review_only"
    assert report["summary"]["provider_call_count"] == 1
    assert report["summary"]["image_exists_count"] == 1
