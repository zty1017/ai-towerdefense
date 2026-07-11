from pathlib import Path
import json

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


def test_agnes_payload_uses_official_tier_ratio_and_img2img_contract():
    payload = image_provider.build_generation_payload(
        image_provider.PROFILES["agnes_image_flash"],
        "Subject: clean terrain.",
        size="1K",
        ratio="16:9",
        input_images=["data:image/png;base64,AAAA"],
        response_format="url",
    )
    assert payload["size"] == "1K"
    assert payload["ratio"] == "16:9"
    assert payload["extra_body"] == {
        "image": ["data:image/png;base64,AAAA"],
        "response_format": "url",
    }
    assert "response_format" not in {key for key in payload if key != "extra_body"}


def test_img2img_reference_is_verified_and_not_written_to_sidecar(tmp_path: Path):
    reference = tmp_path / "composition.png"
    reference.write_bytes(b"not-a-real-png-but-valid-for-data-uri-test")
    pack = request_pack()
    request = pack["requests"][0]
    request["generation_mode"] = "image_to_image"
    request["generation_reference"] = {
        "local_path": str(reference),
        "sha256": generator.sha256_file(reference),
    }
    request["output_contract"].update({"size_tier": "1K", "ratio": "16:9"})
    pack_path = tmp_path / "pack.json"
    generator.write_json(pack_path, pack)
    result = generator.run_request(
        pack_path,
        pack,
        request,
        tmp_path / "candidates",
        image_provider.PROFILES["agnes_image_flash"],
        size_override=None,
        timeout=1,
        live=False,
    )
    sidecar = generator.load_json(Path(result["sidecar_path"]))
    assert sidecar["generation_mode"] == "image_to_image"
    assert sidecar["input_image_count"] == 1
    assert sidecar["size"] == "1K"
    assert sidecar["ratio"] == "16:9"
    assert "base64" not in str(sidecar)


def test_agnes_credentials_rotate_across_available_keys(monkeypatch):
    profile = image_provider.PROFILES["agnes_image_flash"]
    monkeypatch.setenv("AGNES_API_KEY", "key-one")
    monkeypatch.setenv("AGNES_API_KEY_2", "key-two")
    monkeypatch.delenv("AGNES_API_KEY_3", raising=False)
    assert image_provider.get_api_key(profile, 0) == "key-one"
    assert image_provider.get_api_key(profile, 1) == "key-two"
    assert image_provider.get_api_key(profile, 2) == "key-one"


def test_generate_image_accepts_credential_index_and_uses_selected_key(monkeypatch):
    profile = image_provider.PROFILES["agnes_image_flash"]
    monkeypatch.setenv("AGNES_API_KEY", "key-one")
    monkeypatch.setenv("AGNES_API_KEY_2", "key-two")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"data": [{"url": "https://example.invalid/image.png"}]}).encode()

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(image_provider.urllib.request, "urlopen", fake_urlopen)
    response = image_provider.generate_image(
        profile,
        "test prompt",
        credential_index=1,
        timeout=7,
    )
    assert response["data"][0]["url"].endswith("image.png")
    assert captured == {"authorization": "Bearer key-two", "timeout": 7}
