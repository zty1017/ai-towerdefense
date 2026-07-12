"""Contracts for optional live media compilation of player research objects."""
from __future__ import annotations

import json
from pathlib import Path


def _source_png(path: Path) -> None:
    from app.services import research_runtime_media_service as service

    size = 512
    pixels = bytearray([255, 255, 255, 255] * size * size)
    for y in range(92, 456):
        half_width = 65 + (y - 92) // 5
        for x in range(size // 2 - half_width, size // 2 + half_width):
            pos = (y * size + x) * 4
            pixels[pos : pos + 4] = bytes((68, 83, 91, 255))
    service.png_pipeline.write_png(
        path, service.png_pipeline.PngImage(size, size, pixels)
    )


def _candidate() -> dict:
    return {
        "id": "asset_live_lantern_tower",
        "presentation": {
            "name": "引潮灯塔",
            "icon_prompt": "古代灯械与铜制导流片",
            "visual_tags": ["中式古风", "灯械", "铜制"],
        },
    }


def test_live_media_is_reviewed_processed_and_published(tmp_path, monkeypatch):
    from app.services import research_runtime_media_service as service

    monkeypatch.setattr(service, "_mode", lambda: "live")
    monkeypatch.setattr(service, "published_root", lambda: tmp_path / "published")
    monkeypatch.setattr(service.image_provider, "load_dotenv", lambda _: None)
    monkeypatch.setattr(service.vision_review, "load_dotenv", lambda _: None)
    monkeypatch.setattr(service.image_provider, "get_api_key", lambda _: "test-key")
    monkeypatch.setattr(service.vision_review, "get_api_key", lambda _: "test-key")
    monkeypatch.setattr(service.image_provider, "generate_image", lambda *_args, **_kwargs: {"data": [{"url": "https://temporary.invalid/image.png"}]})

    def fake_download(_url, output_path, **_kwargs):
        _source_png(output_path)
        return output_path

    monkeypatch.setattr(service.image_provider, "download_image", fake_download)
    monkeypatch.setattr(
        service.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {
                "score": 0.94,
                "checks": {key: True for key in service._REQUIRED_CHECKS},
                "notes": ["主体完整，适合作为塔防对象素材。"],
            },
            ensure_ascii=False,
        ),
    )

    result = service.compile_runtime_media(
        candidate=_candidate(),
        asset_kind="tower_blueprint",
        session_id="session_test",
        job_id="job_test",
        job_dir=tmp_path / "job",
    )

    assert result["status"] == "passed"
    published = Path(result["published_ref"]["path"])
    assert published.is_file()
    processed = service.png_pipeline.read_png(published)
    alpha = processed.pixels[3::4]
    assert min(alpha) == 0
    assert max(alpha) == 255
    assert result["media_refs"]["icon"]["url"].startswith(
        "/assets/generated_runtime/session_test/job_test/"
    )
    atlas_path = Path(result["published_refs"][1]["path"])
    assert atlas_path.is_file()
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    assert atlas["meta"]["image"] == published.name
    assert atlas["frames"]["asset_live_lantern_tower"]["anchor"] == {
        "x": 0.5,
        "y": 1.0,
    }
    evidence_text = Path(result["evidence_path"]).read_text(encoding="utf-8")
    assert "temporary.invalid" not in evidence_text
    assert "古代灯械与铜制导流片" not in evidence_text
    assert "test-key" not in evidence_text
    evidence = json.loads(evidence_text)
    assert evidence["stores_prompt_body"] is False
    assert evidence["stores_provider_body"] is False
    assert evidence["uses_temporary_url"] is False


def test_provider_failure_returns_safe_fallback(tmp_path, monkeypatch):
    from app.services import research_runtime_media_service as service

    monkeypatch.setattr(service, "_mode", lambda: "live")
    monkeypatch.setattr(service.image_provider, "load_dotenv", lambda _: None)
    monkeypatch.setattr(service.vision_review, "load_dotenv", lambda _: None)
    monkeypatch.setattr(service.image_provider, "get_api_key", lambda _: "test-key")
    monkeypatch.setattr(service.vision_review, "get_api_key", lambda _: "test-key")

    def fail(*_args, **_kwargs):
        raise TimeoutError("provider body must not be retained")

    monkeypatch.setattr(service.image_provider, "generate_image", fail)
    result = service.compile_runtime_media(
        candidate=_candidate(),
        asset_kind="tower_blueprint",
        session_id="session_test",
        job_id="job_test",
        job_dir=tmp_path / "job",
    )

    assert result["status"] == "fallback"
    assert result["reason"] == "TimeoutError"
    assert result["media_refs"] is None
    evidence_text = Path(result["evidence_path"]).read_text(encoding="utf-8")
    assert "provider body" not in evidence_text
    assert "test-key" not in evidence_text


def test_tower_prompt_forbids_habitable_architecture_and_uses_review_feedback():
    from app.services import research_runtime_media_service as service

    initial = service._prompt(_candidate(), "tower_blueprint")
    repaired = service._prompt(
        _candidate(),
        "tower_blueprint",
        1,
        {
            "failed_checks": ["asset_kind_match", "no_people_or_creatures"],
            "notes": ["主体被画成了可居住楼阁，并带有人物。"],
        },
    )

    assert "它不是建筑" in initial
    assert "门、窗、房间、台阶、城墙" in initial
    assert "紧凑机械防御装置" in repaired
    assert "擦除所有人物" in repaired
    assert "可居住楼阁" in repaired


def test_failed_visual_review_persists_compact_diagnostic(tmp_path, monkeypatch):
    from app.services import research_runtime_media_service as service

    monkeypatch.setattr(service, "_mode", lambda: "live")
    monkeypatch.setattr(service.image_provider, "load_dotenv", lambda _: None)
    monkeypatch.setattr(service.vision_review, "load_dotenv", lambda _: None)
    monkeypatch.setattr(service.image_provider, "get_api_key", lambda _: "test-key")
    monkeypatch.setattr(service.vision_review, "get_api_key", lambda _: "test-key")
    prompts = []

    def fake_generate(_profile, prompt, **_kwargs):
        prompts.append(prompt)
        return {"data": [{"url": "https://temporary.invalid/image.png"}]}

    def fake_download(_url, output_path, **_kwargs):
        _source_png(output_path)
        return output_path

    monkeypatch.setattr(service.image_provider, "generate_image", fake_generate)
    monkeypatch.setattr(service.image_provider, "download_image", fake_download)
    monkeypatch.setattr(
        service.vision_review,
        "call_vision_model",
        lambda *_args, **_kwargs: json.dumps(
            {
                "score": 0.31,
                "checks": {
                    key: key not in {"asset_kind_match", "no_people_or_creatures"}
                    for key in service._REQUIRED_CHECKS
                },
                "notes": ["主体是大型楼阁，并且出现人物。"],
            },
            ensure_ascii=False,
        ),
    )

    result = service.compile_runtime_media(
        candidate=_candidate(),
        asset_kind="tower_blueprint",
        session_id="session_test",
        job_id="job_test",
        job_dir=tmp_path / "job",
    )

    assert result["status"] == "fallback"
    assert len(prompts) == 2
    assert "擦除所有人物" in prompts[1]
    evidence = json.loads(Path(result["evidence_path"]).read_text(encoding="utf-8"))
    assert evidence["visual_review"]["score"] == 0.31
    assert evidence["visual_review"]["failed_checks"] == [
        "no_people_or_creatures",
        "asset_kind_match",
    ]
    assert "大型楼阁" in evidence["visual_review"]["notes"][0]
    rendered = json.dumps(evidence, ensure_ascii=False)
    assert "temporary.invalid" not in rendered
    assert "test-key" not in rendered
