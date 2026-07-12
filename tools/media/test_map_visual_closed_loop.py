import json
from pathlib import Path

from tools.media import image_provider
from tools.media import map_visual_closed_loop as closed_loop
from tools.media import map_visual_candidate_cache
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
                "style_contract": {
                    "worldbook_id": "cloud_mechanism_frontier",
                    "theme_terms": ["cloud", "mechanical", "eastern", "storm"],
                    "terrain_material_terms": ["cloud island"],
                    "road_material_terms": ["cable road"],
                },
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


def test_style_repair_uses_request_contract_without_template_leakage():
    request = request_pack()["requests"][0]
    repaired = closed_loop.repaired_request(
        request,
        ["worldbook_style_fit", "semi_realistic_material_finish"],
    )
    prompt = repaired["prompt_brief"].lower()
    assert "cloud_mechanism_frontier" in prompt
    assert "cable road" in prompt
    assert "late-ming" not in prompt
    assert "courier" not in prompt


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


def test_generated_terrain_can_reuse_reviewed_critical_components(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    fallback = tmp_path / "canonical"
    make_test_png(fallback / "textures/test_node.road_tile.png")
    make_test_png(fallback / "textures/test_node.slot_tile.png")

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        path = output_dir / f"{request['role']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        make_test_png(path, white_background=False)
        return {"candidate_path": str(path)}

    checks = {key: True for key in closed_loop.COMMON_CHECKS}
    checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})
    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(
        closed_loop.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {"score": 0.94, "checks": checks, "notes": []}
        ),
    )

    report = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run",
        tmp_path / "reviewed",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        max_attempts=1,
        max_workers=1,
        reviewed_fallback_dir=fallback,
    )

    assert report["status"] == "runtime_visuals_ready"
    assert report["runtime_critical_roles_ready"] is True
    assert report["summary"]["reviewed_fallback_count"] == 2
    assert {item["role"] for item in report["reviewed_fallbacks"]} == {
        "road_surface",
        "build_slot_platform",
    }


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
    assert report["failures"] == []
    assert report["results"][0]["status"] == "failed_after_retries"
    assert report["results"][0]["attempts"][0]["status"] == "generation_error"
    assert report["results"][0]["attempts"][0]["error"] == "TypeError:external_call_failed"


def test_transient_generation_error_retries_with_next_credential(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    credentials = []

    def flaky_generate(_pack_path, _pack, request, output_dir, _profile, **kwargs):
        credentials.append(kwargs["credential_index"])
        if len(credentials) == 1:
            raise RuntimeError("temporary provider failure")
        path = output_dir / f"{request['role']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        make_test_png(path, white_background=False)
        return {"candidate_path": str(path)}

    checks = {key: True for key in closed_loop.COMMON_CHECKS}
    checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})
    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", flaky_generate)
    monkeypatch.setattr(
        closed_loop.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {"score": 0.94, "checks": checks, "notes": []}
        ),
    )
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
    assert credentials == [0, 1]


def test_closed_loop_calls_candidate_generator_with_supported_contract(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    def supported_generation(
        request_pack_path,
        request_pack,
        request,
        output_dir,
        profile,
        *,
        size_override,
        timeout,
        live,
        credential_index=0,
    ):
        candidate = output_dir / "candidate.png"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"not-reviewed")
        return {"candidate_path": str(candidate)}

    monkeypatch.setattr(
        closed_loop.candidate_generator,
        "run_request",
        supported_generation,
    )
    monkeypatch.setattr(
        closed_loop,
        "review_candidate",
        lambda *_args, **_kwargs: {
            "status": "failed",
            "failed_checks": ["worldbook_style_fit"],
        },
    )
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
    assert report["summary"]["provider_failure_count"] == 0
    assert report["summary"]["attempt_count"] == 1


def test_reviewed_candidate_cache_survives_across_runs(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    calls = {"generate": 0, "review": 0}

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        calls["generate"] += 1
        path = output_dir / f"{request['role']}.png"
        make_test_png(path, white_background=False)
        return {"candidate_path": str(path)}

    checks = {key: True for key in closed_loop.COMMON_CHECKS}
    checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})

    def fake_review(*_args, **_kwargs):
        calls["review"] += 1
        return json.dumps({"score": 0.94, "checks": checks, "notes": []})

    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(closed_loop.vision_review, "call_vision_model", fake_review)
    kwargs = {
        "image_profile": image_provider.PROFILES["agnes_image_flash"],
        "vision_profile": vision_review.PROFILES["agnes_multimodal_flash"],
        "max_attempts": 1,
        "max_workers": 1,
        "cache_dir": tmp_path / "cache",
    }
    first = closed_loop.run_closed_loop(
        pack_path, pack, tmp_path / "run_1", tmp_path / "reviewed_1", **kwargs
    )
    second = closed_loop.run_closed_loop(
        pack_path, pack, tmp_path / "run_2", tmp_path / "reviewed_2", **kwargs
    )

    assert calls == {"generate": 1, "review": 1}
    assert first["summary"]["cache_store_count"] == 1
    assert second["summary"]["cache_hit_count"] == 1
    assert second["summary"]["attempt_count"] == 0
    assert second["summary"]["provider_call_count"] == 0
    assert second["summary"]["vision_review_call_count"] == 0
    assert second["results"][0]["cache"]["review"]["cache_review_reused"] is True


def test_cache_policy_change_forces_fresh_generation(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    calls = {"generate": 0}

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        calls["generate"] += 1
        path = output_dir / f"{request['role']}.png"
        make_test_png(path, white_background=False)
        return {"candidate_path": str(path)}

    checks = {key: True for key in closed_loop.COMMON_CHECKS}
    checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})
    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(
        closed_loop.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {"score": 0.99, "checks": checks, "notes": []}
        ),
    )
    common = {
        "image_profile": image_provider.PROFILES["agnes_image_flash"],
        "vision_profile": vision_review.PROFILES["agnes_multimodal_flash"],
        "max_attempts": 1,
        "max_workers": 1,
        "cache_dir": tmp_path / "cache",
    }
    closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run_1",
        tmp_path / "reviewed_1",
        minimum_score=0.78,
        **common,
    )
    changed = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run_2",
        tmp_path / "reviewed_2",
        minimum_score=0.95,
        **common,
    )

    assert calls["generate"] == 2
    assert changed["summary"]["cache_hit_count"] == 0


def test_cache_rejects_tampered_candidate(tmp_path):
    cache = map_visual_candidate_cache.CandidateCache(tmp_path / "cache")
    candidate = tmp_path / "candidate.png"
    make_test_png(candidate, white_background=False)
    review = {"status": "passed", "failed_checks": [], "score": 1.0, "checks": {}}
    stored = cache.store(
        request_fingerprint_value="a" * 64,
        review_policy_fingerprint_value="b" * 64,
        candidate_path=candidate,
        review=review,
        source_prompt_sha256="c" * 64,
        provenance={},
    )
    entry_path = Path(stored["cache_entry_path"])
    entry_path.with_name("candidate.png").write_bytes(b"tampered")

    assert (
        cache.restore(
            request_fingerprint_value="a" * 64,
            review_policy_fingerprint_value="b" * 64,
            output_path=tmp_path / "restored.png",
        )
        is None
    )
