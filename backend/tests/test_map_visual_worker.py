from __future__ import annotations

import json
from pathlib import Path

from app.services import map_visual_worker_service as service


def test_background_job_runs_closed_loop_and_activates_reviewed_visuals(
    tmp_path: Path, monkeypatch
):
    output_dir = tmp_path / "compiled_map"
    request_pack_path = output_dir / "visual_handoff" / "request.json"
    request_pack_path.parent.mkdir(parents=True)
    request_pack_path.write_text(
        json.dumps(
            {
                "schema_version": "map_layered_visual_generation_request_pack.v0.1",
                "node_id": "test_node",
                "worldbook_id": "test_world",
                "requests": [],
            }
        ),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    job_path = service.map_visual_job_queue.enqueue_job(
        input_path=input_path,
        output_dir=output_dir,
        request_pack_path=request_pack_path,
        image_profile="agnes_image_flash",
        vision_profile="agnes_multimodal_flash",
        max_attempts=2,
        max_workers=3,
        generation_timeout=10,
        review_timeout=10,
    )
    monkeypatch.setattr(service.image_provider, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(service.vision_review, "load_dotenv", lambda *_: None)

    def fake_closed_loop(*_args, **_kwargs):
        return {
            "status": "runtime_visuals_ready",
            "runtime_critical_roles_ready": True,
            "summary": {"provider_call_count": 6, "vision_review_call_count": 6},
            "report_path": str(tmp_path / "report.json"),
        }

    activated = []
    monkeypatch.setattr(service.map_visual_closed_loop, "run_closed_loop", fake_closed_loop)
    monkeypatch.setattr(
        service.map_compilation_orchestrator,
        "apply_reviewed_visuals",
        lambda input_ref, output_ref, _report: activated.append((input_ref, output_ref)),
    )
    result = service.process_job(job_path)
    assert result is not None
    assert result["status"] == "completed"
    assert result["result"]["visual_package_applied"] is True
    assert result["result"]["provider_call_count"] == 6
    assert activated == [(input_path, output_dir)]


def test_studio_job_list_does_not_expose_job_settings(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(service, "LAYERED_ROOT", tmp_path)
    output_dir = tmp_path / "node"
    request_pack_path = output_dir / "visual_handoff" / "request.json"
    request_pack_path.parent.mkdir(parents=True)
    request_pack_path.write_text('{"requests": []}', encoding="utf-8")
    input_path = tmp_path / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    service.map_visual_job_queue.enqueue_job(
        input_path=input_path,
        output_dir=output_dir,
        request_pack_path=request_pack_path,
        image_profile="agnes_image_flash",
        vision_profile="agnes_multimodal_flash",
        max_attempts=2,
        max_workers=3,
        generation_timeout=10,
        review_timeout=10,
    )
    jobs = service.list_jobs()
    assert len(jobs) == 1
    assert "settings" not in jobs[0]
    assert "request_pack_path" not in jobs[0]
