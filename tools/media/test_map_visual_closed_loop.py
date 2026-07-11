import json
from pathlib import Path

from tools.media import image_provider
from tools.media import map_visual_closed_loop as closed_loop
from tools.media import png_pipeline
from tools.media import vision_review


def make_test_png(path: Path, *, white_background: bool = True) -> None:
    image = png_pipeline.PngImage(640, 640, bytearray(640 * 640 * 4))
    background = (255, 255, 255, 255) if white_background else (32, 40, 45, 255)
    for offset in range(0, len(image.pixels), 4):
        image.pixels[offset : offset + 4] = bytes(background)
    for y in range(180, 460):
        for x in range(160, 480):
            offset = (y * image.width + x) * 4
            image.pixels[offset : offset + 4] = bytes((72, 60, 42, 255))
    png_pipeline.write_png(path, image)


def request_pack() -> dict:
    requests = []
    for index, role in enumerate(
        (
            "terrain_base",
            "road_surface",
            "build_slot_platform",
            "objective_foundation",
            "spawn_marker",
            "non_blocking_decoration",
        ),
        start=1,
    ):
        requests.append(
            {
                "request_id": f"request_{index}",
                "role": role,
                "generation_mode": "text_to_image",
                "prompt_sections": {
                    "subject": role,
                    "environment": "plain white background",
                    "style": "game art",
                    "lighting": "neutral",
                    "composition": "centered",
                    "quality": "clean",
                },
                "prompt_brief": role,
                "output_contract": {"size_tier": "1K", "ratio": "1:1"},
            }
        )
    return {
        "schema_version": "map_layered_visual_generation_request_pack.v0.1",
        "node_id": "test_node",
        "worldbook_id": "test_world",
        "requests": requests,
    }


def test_repair_prompt_uses_controlled_mapping():
    request = request_pack()["requests"][0]
    repaired = closed_loop.repaired_request(
        request,
        ["no_people_or_creatures", "unknown_external_instruction"],
    )
    assert "remove every human" in repaired["prompt_brief"]
    assert "unknown_external_instruction" not in repaired["prompt_brief"]
    assert repaired["prompt_brief"].startswith("Subject:")


def test_score_threshold_never_overrides_hard_checks():
    request = request_pack()["requests"][0]
    checks = {key: True for key in closed_loop.COMMON_CHECKS}
    checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})
    below = closed_loop.normalize_vision_review(
        {"score": 0.77, "checks": checks, "notes": []}, request
    )
    assert below["status"] == "failed"
    checks["central_playable_clearance"] = False
    hard_failure = closed_loop.normalize_vision_review(
        {"score": 1.0, "checks": checks, "notes": []}, request
    )
    assert hard_failure["status"] == "failed"
    assert "central_playable_clearance" in hard_failure["failed_checks"]


def test_calibration_summary_does_not_auto_lower_threshold():
    summary = closed_loop.build_calibration_summary(
        {
            "node_id": "test_node",
            "status": "blocked_after_retries",
            "runtime_critical_roles_ready": False,
            "policy": {"minimum_vision_score": 0.78},
            "results": [
                {
                    "role": "terrain_base",
                    "status": "failed_after_retries",
                    "attempt_count": 2,
                    "attempts": [
                        {"review": {"score": 0.9, "failed_checks": ["no_people_or_creatures"]}}
                    ],
                }
            ],
        }
    )
    assert summary["configured_minimum_score"] == 0.78
    assert summary["recommendation"] == "keep_hard_check_vetoes_and_revise_prompts_before_threshold_changes"


def test_closed_loop_promotes_only_after_critical_roles_pass(tmp_path, monkeypatch):
    pack = request_pack()
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        path = output_dir / f"{request['role']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        make_test_png(path, white_background=request["role"] != "terrain_base")
        return {
            "candidate_path": str(path),
            "sidecar_path": str(path.with_suffix(".json")),
            "provider_called_this_run": True,
            "image_exists": True,
        }

    all_checks = {key: True for key in closed_loop.COMMON_CHECKS}
    for checks in closed_loop.ROLE_CHECKS.values():
        all_checks.update({key: True for key in checks})
    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(
        closed_loop.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {"score": 0.94, "checks": all_checks, "notes": ["passed"]}
        ),
    )
    report = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run",
        tmp_path / "reviewed",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        max_attempts=2,
        max_workers=3,
    )
    assert report["status"] == "runtime_visuals_ready"
    assert report["summary"]["attempt_count"] == 6
    assert report["summary"]["promotion_count"] == 6
    assert (tmp_path / "reviewed/backdrops/test_node.reviewed_painted_backdrop.png").is_file()
    road = png_pipeline.read_png(tmp_path / "reviewed/textures/road_tile.png")
    assert any(alpha == 0 for alpha in road.pixels[3::4])


def test_failed_review_retries_with_repaired_prompt(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    seen_prompts = []

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        seen_prompts.append(request["prompt_brief"])
        path = output_dir / "terrain.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        make_test_png(path, white_background=False)
        return {"candidate_path": str(path)}

    calls = {"count": 0}

    def fake_review(*_args, **_kwargs):
        calls["count"] += 1
        checks = {key: True for key in closed_loop.COMMON_CHECKS}
        checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})
        if calls["count"] == 1:
            checks["no_people_or_creatures"] = False
        return json.dumps({"score": 0.9, "checks": checks, "notes": []})

    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(closed_loop.vision_review, "call_vision_model", fake_review)
    result = closed_loop.run_role(
        pack_path,
        pack,
        pack["requests"][0],
        tmp_path / "run",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        request_index=0,
        max_attempts=2,
        generation_timeout=1,
        review_timeout=1,
        review_max_tokens=300,
    )
    assert result["status"] == "passed"
    assert result["attempt_count"] == 2
    assert "remove every human" in seen_prompts[1]


def test_critical_review_failure_blocks_every_promotion(tmp_path, monkeypatch):
    pack = request_pack()
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        path = output_dir / f"{request['role']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        make_test_png(path, white_background=request["role"] != "terrain_base")
        return {"candidate_path": str(path)}

    def fake_review(_profile, prompt, *_args, **_kwargs):
        checks = {key: True for key in closed_loop.COMMON_CHECKS}
        for role_checks in closed_loop.ROLE_CHECKS.values():
            checks.update({key: True for key in role_checks})
        if '"role": "terrain_base"' in prompt:
            checks["central_playable_clearance"] = False
        return json.dumps({"score": 0.96, "checks": checks, "notes": []})

    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(closed_loop.vision_review, "call_vision_model", fake_review)
    report = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run",
        tmp_path / "reviewed",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        max_attempts=2,
        max_workers=3,
    )
    assert report["status"] == "blocked_after_retries"
    assert report["runtime_critical_roles_ready"] is False
    assert report["promotions"] == []
    assert not (tmp_path / "reviewed").exists()


def test_provider_failure_reports_generation_stage(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    def fail_generation(*_args, **_kwargs):
        raise TypeError("unexpected adapter keyword")

    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fail_generation)
    report = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run",
        tmp_path / "reviewed",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        max_attempts=1,
        max_workers=1,
    )
    assert report["failures"] == [
        {
            "request_id": "request_1",
            "role": "terrain_base",
            "stage": "generation",
            "error": "TypeError:external_call_failed",
        }
    ]
