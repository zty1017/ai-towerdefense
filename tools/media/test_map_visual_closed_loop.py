import hashlib
import json
import urllib.error
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


def make_light_slot_png(path: Path) -> None:
    image = png_pipeline.PngImage(640, 640, bytearray(640 * 640 * 4))
    for offset in range(0, len(image.pixels), 4):
        image.pixels[offset : offset + 4] = bytes((255, 255, 255, 255))
    for y in range(180, 460):
        for x in range(160, 480):
            offset = (y * image.width + x) * 4
            image.pixels[offset : offset + 4] = bytes((202, 205, 198, 255))
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
        ["no_incompatible_world_elements", "game_ready_material_finish"],
    )
    prompt = repaired["prompt_brief"].lower()
    assert "cloud_mechanism_frontier" in prompt
    assert "cable road" in prompt
    assert "late-ming" not in prompt
    assert "courier" not in prompt


def test_terrain_repair_rewrites_composition_instead_of_only_appending_negatives():
    request = request_pack()["requests"][0]
    repaired = closed_loop.repaired_request(
        request,
        ["no_baked_border_scenery_or_architecture", "no_baked_traversal_route"],
    )
    composition = repaired["prompt_sections"]["composition"]
    assert "entire frame edge to edge" in composition
    assert "remove every wall" in composition
    assert "continuous nearly flat traversable ground" in composition
    assert "deterministic composition" in repaired["prompt_sections"]["quality"]


def test_terrain_review_prompt_defines_geometric_acceptance_boundary():
    prompt = closed_loop.build_review_prompt(request_pack()["requests"][0])
    assert "整幅图都应由近乎平坦、可通行的地表组成" in prompt
    assert "普通铺地石板的接缝" in prompt
    assert "即使只出现在边缘" in prompt


def test_score_threshold_never_overrides_hard_checks():
    request = request_pack()["requests"][0]
    checks = {key: True for key in closed_loop.COMMON_CHECKS}
    checks.update({key: True for key in closed_loop.ROLE_CHECKS["terrain_base"]})
    below = closed_loop.normalize_vision_review(
        {"score": 0.77, "checks": checks, "notes": []},
        request,
        minimum_score=0.85,
    )
    assert below["status"] == "failed"
    checks["no_baked_traversal_route"] = False
    hard_failure = closed_loop.normalize_vision_review(
        {"score": 1.0, "checks": checks, "notes": []}, request
    )
    assert hard_failure["status"] == "failed"
    assert "no_baked_traversal_route" in hard_failure["failed_checks"]


def test_light_slot_material_is_rejected_by_deterministic_gate(tmp_path):
    candidate = tmp_path / "light_slot.png"
    make_light_slot_png(candidate)

    issues, metrics = closed_loop.deterministic_issues(
        candidate, "build_slot_platform"
    )

    assert "deterministic_slot_foreground_too_light" in issues
    assert metrics["pale_foreground_ratio"] > 0.34


def test_style_reference_check_is_only_required_when_reference_exists():
    request = request_pack()["requests"][0]
    assert "target_style_reference_match" not in closed_loop.required_review_checks(
        request["role"], has_style_reference=False
    )
    assert "target_style_reference_match" in closed_loop.required_review_checks(
        request["role"], has_style_reference=True
    )


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
    assert report["results"][0]["status"] == "passed"
    assert report["summary"]["attempt_count"] == 2
    assert report["summary"]["promotion_count"] == 3
    assert {item["role"] for item in report["results"] if item["status"] == "deferred_optional_visual_role"} == {
        "objective_foundation",
        "spawn_marker",
        "non_blocking_decoration",
    }
    assert (tmp_path / "reviewed/textures/terrain_tile.png").is_file()
    assert report["reviewed_backdrop_source_dir"] is None
    road = png_pipeline.read_png(tmp_path / "reviewed/textures/road_tile.png")
    assert road.width == road.height * 2
    assert all(alpha == 255 for alpha in road.pixels[3::4])


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
            checks["no_baked_traversal_route"] = False
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
            "failed_checks": ["no_incompatible_world_elements"],
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


def test_non_semantic_control_reference_does_not_invalidate_candidate_cache():
    pack = request_pack()
    request = pack["requests"][0]
    request["control_reference"] = {
        "usage": "alignment_preview_only",
        "sha256": "a" * 64,
        "semantic_authority": False,
    }
    first, _ = closed_loop.cache_fingerprints(
        pack,
        request,
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        0.78,
    )
    request["control_reference"]["sha256"] = "b" * 64
    second, _ = closed_loop.cache_fingerprints(
        pack,
        request,
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        0.78,
    )

    assert first == second


def test_cache_policy_change_reuses_candidate_that_meets_stricter_policy(
    tmp_path, monkeypatch
):
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

    assert calls["generate"] == 1
    assert changed["summary"]["cache_hit_count"] == 1


def test_cache_policy_change_regenerates_candidate_below_new_threshold(
    tmp_path, monkeypatch
):
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
    scores = iter((0.9, 0.99))
    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(
        closed_loop.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {"score": next(scores), "checks": checks, "notes": []}
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
        base_prompt_sha256="c" * 64,
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


def test_transient_generation_retries_do_not_consume_visual_attempt(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = [pack["requests"][0]]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    calls = {"generate": 0}

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        calls["generate"] += 1
        if calls["generate"] < 3:
            raise image_provider.TransientHttpError(503)
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

    report = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run",
        tmp_path / "reviewed",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        max_attempts=1,
        max_workers=1,
        max_transport_retries=2,
        transport_backoff_base=0,
        transport_backoff_cap=0,
    )

    assert calls["generate"] == 3
    assert report["summary"]["attempt_count"] == 1
    assert report["summary"]["provider_call_count"] == 3
    assert report["summary"]["transport_retry_count"] == 2
    assert report["results"][0]["attempts"][0]["transport_retry_count"] == 2


def test_transient_review_retries_do_not_regenerate_candidate(tmp_path, monkeypatch):
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

    def flaky_review(*_args, **_kwargs):
        calls["review"] += 1
        if calls["review"] < 3:
            raise urllib.error.HTTPError(
                "https://example.invalid/review", 503, "temporary", {}, None
            )
        return {
            "status": "passed",
            "score": 0.99,
            "checks": checks,
            "failed_checks": [],
            "notes": [],
        }

    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(closed_loop, "review_candidate", flaky_review)

    report = closed_loop.run_closed_loop(
        pack_path,
        pack,
        tmp_path / "run",
        tmp_path / "reviewed",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        max_attempts=1,
        max_workers=1,
        max_transport_retries=2,
        transport_backoff_base=0,
        transport_backoff_cap=0,
    )

    assert calls == {"generate": 1, "review": 3}
    assert report["results"][0]["status"] == "passed"
    assert report["summary"]["provider_call_count"] == 1
    assert report["summary"]["vision_review_call_count"] == 3
    assert report["summary"]["transport_retry_count"] == 2
    assert report["results"][0]["attempts"][0]["review_transport_retry_count"] == 2


def test_existing_candidate_is_re_reviewed_before_regeneration(tmp_path, monkeypatch):
    pack = request_pack()
    request = pack["requests"][0]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    attempt_dir = tmp_path / "run" / "attempt_01"
    attempt_dir.mkdir(parents=True)
    candidate = attempt_dir / "test_node.terrain_base.agnes_image_flash.candidate.png"
    make_test_png(candidate, white_background=False)
    sidecar = Path(str(candidate) + ".candidate.json")
    sidecar.write_text(
        json.dumps(
            {
                "prompt_sha256": hashlib.sha256(
                    request["prompt_brief"].encode("utf-8")
                ).hexdigest(),
                "generation_reference_sha256": None,
                "image_sha256": closed_loop.sha256_file(candidate),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        closed_loop.candidate_generator,
        "run_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("candidate should not be regenerated")
        ),
    )
    monkeypatch.setattr(
        closed_loop,
        "review_candidate",
        lambda *_args, **_kwargs: {
            "status": "passed",
            "score": 0.99,
            "checks": {},
            "failed_checks": [],
            "notes": [],
        },
    )

    result = closed_loop.run_role(
        pack_path,
        pack,
        request,
        tmp_path / "run",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        request_index=0,
        max_attempts=1,
        generation_timeout=1,
        review_timeout=1,
        review_max_tokens=300,
    )

    assert result["status"] == "passed"
    assert result["attempt_count"] == 0
    assert result["attempts"][0]["status"] == "reused_candidate_reviewed"


def test_existing_candidate_from_stale_prompt_is_not_reused(tmp_path):
    pack = request_pack()
    request = pack["requests"][0]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    attempt_dir = tmp_path / "run" / "attempt_01"
    attempt_dir.mkdir(parents=True)
    candidate = attempt_dir / "test_node.terrain_base.agnes_image_flash.candidate.png"
    make_test_png(candidate, white_background=False)
    Path(str(candidate) + ".candidate.json").write_text(
        json.dumps(
            {
                "prompt_sha256": hashlib.sha256(b"obsolete prompt").hexdigest(),
                "generation_reference_sha256": None,
                "image_sha256": closed_loop.sha256_file(candidate),
            }
        ),
        encoding="utf-8",
    )

    found = closed_loop.find_existing_candidates(
        tmp_path / "run",
        pack,
        request,
        [image_provider.PROFILES["agnes_image_flash"]],
        pack_path,
    )

    assert found == []


def test_secondary_style_review_blocks_cartoon_finish():
    review = closed_loop.normalize_secondary_style_review(
        {
            "premium_non_cartoon_finish": False,
            "material_contract_present": True,
            "style_category": "cartoon",
            "notes": ["粗描边和平涂明显。"],
        }
    )

    assert review["status"] == "failed"
    assert review["failed_checks"] == ["premium_non_cartoon_finish"]
    assert review["style_category"] == "cartoon"
    assert closed_loop.review_policy_revision(
        "terrain_base", vision_review.PROFILES["ark_kimi_k2_6"]
    ).endswith(":secondary:ark_kimi_k2_6")


def test_existing_candidates_select_highest_review_score(tmp_path, monkeypatch):
    pack = request_pack()
    request = pack["requests"][0]
    request["image_profile_candidates"] = [
        "agnes_image_flash",
        "agnes_image_20_flash",
    ]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")
    candidates = []
    for attempt, profile_name in ((1, "agnes_image_flash"), (2, "agnes_image_20_flash")):
        attempt_dir = tmp_path / "run" / f"attempt_{attempt:02d}"
        attempt_dir.mkdir(parents=True)
        candidate = attempt_dir / f"test_node.terrain_base.{profile_name}.candidate.png"
        make_test_png(candidate, white_background=False)
        Path(str(candidate) + ".candidate.json").write_text(
            json.dumps(
                {
                    "prompt_sha256": hashlib.sha256(
                        request["prompt_brief"].encode("utf-8")
                    ).hexdigest(),
                    "generation_reference_sha256": None,
                    "image_sha256": closed_loop.sha256_file(candidate),
                }
            ),
            encoding="utf-8",
        )
        candidates.append(candidate)

    monkeypatch.setattr(
        closed_loop.candidate_generator,
        "run_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("passing existing candidates should prevent regeneration")
        ),
    )

    def review(candidate_request, candidate_path, *_args, **_kwargs):
        del candidate_request
        return {
            "status": "passed",
            "score": 0.82 if "attempt_01" in str(candidate_path) else 0.96,
            "checks": {},
            "failed_checks": [],
            "notes": [],
        }

    monkeypatch.setattr(closed_loop, "review_candidate", review)
    result = closed_loop.run_role(
        pack_path,
        pack,
        request,
        tmp_path / "run",
        image_provider.PROFILES["agnes_image_flash"],
        vision_review.PROFILES["agnes_multimodal_flash"],
        request_index=0,
        max_attempts=1,
        generation_timeout=1,
        review_timeout=1,
        review_max_tokens=300,
    )

    assert result["accepted_candidate_path"] == str(candidates[1].resolve())
    assert len(result["attempts"]) == 2


def test_material_postprocessing_prepares_runtime_geometry(tmp_path):
    source = tmp_path / "source.png"
    make_test_png(source, white_background=False)
    terrain = tmp_path / "terrain.png"
    road = tmp_path / "road.png"

    terrain_metrics = closed_loop.postprocess_terrain_texture(source, terrain)
    road_metrics = closed_loop.postprocess_road_texture(source, road)

    assert terrain_metrics["aspect_ratio"] == 1.0
    assert road_metrics["aspect_ratio"] == 2.0
    road_image = png_pipeline.read_png(road)
    for y in range(road_image.height):
        left = y * road_image.width * 4
        right = (y * road_image.width + road_image.width - 1) * 4
        assert road_image.pixels[left : left + 4] == road_image.pixels[right : right + 4]


def test_road_material_can_be_derived_from_reviewed_terrain(tmp_path):
    source = tmp_path / "terrain.png"
    make_test_png(source, white_background=False)
    output = tmp_path / "road.png"
    result = closed_loop.derive_road_surface_from_terrain(
        source,
        output,
        {
            "style_contract": {
                "palette": {"road_base": "#C4C8C0"},
            }
        },
    )
    image = png_pipeline.read_png(output)
    assert image.width == image.height * 2
    assert result["status"] == "derived_from_reviewed_terrain"
    assert result["derivation_graph"][-1] == "runtime_road_brush"
    assert max(image.pixels[0::4]) <= 160
    assert max(image.pixels[1::4]) <= 160
    assert max(image.pixels[2::4]) <= 160


def test_road_provider_is_skipped_for_reviewed_terrain_derivation(tmp_path, monkeypatch):
    pack = request_pack()
    pack["requests"] = pack["requests"][:3]
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack), encoding="utf-8")

    generated_roles = []

    def fake_generate(_pack_path, _pack, request, output_dir, _profile, **_kwargs):
        generated_roles.append(request["role"])
        path = output_dir / f"{request['role']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        make_test_png(path, white_background=request["role"] != "terrain_base")
        return {"candidate_path": str(path)}

    def fake_review(_profile, prompt, *_args, **_kwargs):
        checks = {key: True for key in closed_loop.COMMON_CHECKS}
        for role_checks in closed_loop.ROLE_CHECKS.values():
            checks.update({key: True for key in role_checks})
        return json.dumps({"score": 0.92, "checks": checks, "notes": []})

    monkeypatch.setattr(closed_loop.candidate_generator, "run_request", fake_generate)
    monkeypatch.setattr(closed_loop.vision_review, "call_vision_model", fake_review)
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

    assert report["status"] == "runtime_visuals_ready"
    derived = [
        item
        for item in report["reviewed_fallbacks"]
        if item["role"] == "road_surface"
    ]
    assert derived[0]["status"] == "derived_from_reviewed_terrain"
    assert (tmp_path / "reviewed/textures/road_tile.png").is_file()
    assert "road_surface" not in generated_roles
    road_result = next(item for item in report["results"] if item["role"] == "road_surface")
    assert road_result["status"] == "skipped_provider_for_deterministic_derivation"
    assert report["summary"]["failed_count"] == 0


def test_decoration_components_pack_into_runtime_quadrants(tmp_path):
    sources = []
    colors = ((180, 60, 60), (60, 180, 60), (60, 60, 180), (180, 150, 60))
    for index, color in enumerate(colors):
        image = png_pipeline.transparent_image(256 + index * 32, 220 + index * 24)
        for y in range(40, image.height - 40):
            for x in range(40, image.width - 40):
                offset = (y * image.width + x) * 4
                image.pixels[offset : offset + 4] = bytes((*color, 255))
        path = tmp_path / f"component_{index}.png"
        png_pipeline.write_png(path, image)
        sources.append(path)

    output = tmp_path / "non_blocking_decoration.png"
    metrics = closed_loop.pack_decoration_components(sources, output)
    atlas = png_pipeline.read_png(output)

    assert atlas.width == atlas.height == metrics["cell_size"] * 2
    assert metrics["sha256"] == closed_loop.sha256_file(output)
    assert any(atlas.pixels[index] > 0 for index in range(3, len(atlas.pixels), 4))
