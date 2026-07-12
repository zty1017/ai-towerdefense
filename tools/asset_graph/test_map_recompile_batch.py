"""Tests for the map recompile batch CLI.

These tests exercise the batch orchestrator end-to-end with a mocked provider
closed loop so no real provider is called and no secret is read.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest

from tools.asset_graph import map_compilation_orchestrator as orchestrator
from tools.asset_graph import run_map_recompile_batch as batch


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_ROOT = ROOT / "game_data" / "media" / "layered_maps"


@pytest.fixture
def staging_root():
    path = CANONICAL_ROOT / "_pytest_recompile_staging" / uuid.uuid4().hex
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def _fake_closed_loop_factory(critical_ready: bool):
    """Return a fake ``run_closed_loop`` matching the orchestrator contract."""

    def fake_closed_loop(
        request_pack_path: Path,
        pack: dict[str, Any],
        output_dir: Path,
        reviewed_dir: Path,
        *_profiles,
        max_attempts: int = 2,
        max_workers: int = 3,
        generation_timeout: int = 240,
        review_timeout: int = 180,
        review_max_tokens: int = 1200,
        minimum_score: float = 0.78,
        reviewed_fallback_dir: Path | None = None,
        cache_dir: Path | None = None,
    ) -> dict[str, Any]:
        node_id = str(pack.get("node_id") or "map")
        backdrops = reviewed_dir / "backdrops"
        textures = reviewed_dir / "textures"
        components = reviewed_dir / "components"
        backdrops.mkdir(parents=True, exist_ok=True)
        textures.mkdir(parents=True, exist_ok=True)
        components.mkdir(parents=True, exist_ok=True)
        # Reuse existing reviewed visual assets from the canonical dir so the
        # layered package builder can read real PNGs without PIL.
        source = CANONICAL_ROOT / node_id
        if source.is_dir():
            shutil.copy2(
                source / "backdrops" / f"{node_id}.reviewed_painted_backdrop.png",
                backdrops / f"{node_id}.reviewed_painted_backdrop.png",
            )
            shutil.copy2(
                source / "textures" / f"{node_id}.road_tile.png",
                textures / "road_tile.png",
            )
            shutil.copy2(
                source / "textures" / f"{node_id}.slot_tile.png" if (source / "textures" / f"{node_id}.slot_tile.png").exists() else source / "textures" / f"{node_id}.road_tile.png",
                textures / "slot_tile.png",
            )
        for role in ("objective_foundation", "spawn_marker", "non_blocking_decoration"):
            shutil.copy2(
                textures / "road_tile.png",
                components / f"{role}.png",
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "map_visual_closed_loop_report.v0.1.json"
        report = {
            "schema_version": "map_visual_closed_loop_report.v0.1",
            "node_id": pack.get("node_id"),
            "worldbook_id": pack.get("worldbook_id"),
            "status": "runtime_visuals_ready" if critical_ready else "blocked_after_retries",
            "runtime_critical_roles_ready": critical_ready,
            "runtime_critical_roles": ["build_slot_platform", "road_surface", "terrain_base"],
            "summary": {
                "request_count": 6,
                "passed_count": 6 if critical_ready else 3,
                "failed_count": 0 if critical_ready else 3,
                "provider_failure_count": 0,
                "attempt_count": 6,
                "provider_call_count": 6,
                "vision_review_call_count": 6,
                "promotion_count": 6 if critical_ready else 0,
            },
            "results": [],
            "failures": [],
            "promotions": [],
            "reviewed_backdrop_source_dir": str(backdrops) if critical_ready else None,
            "reviewed_texture_source_dir": str(textures) if critical_ready else None,
            "reviewed_component_source_dir": str(components) if critical_ready else None,
            "policy": {
                "runtime_semantics_source": "MapRuntimePackage",
                "image_to_semantic_inference": False,
                "raw_prompt_stored": False,
                "raw_provider_response_stored": False,
                "automatic_promotion_scope": "reviewed_visual_staging_only",
                "unreviewed_candidate_player_visible": False,
                "minimum_vision_score": minimum_score,
            },
        }
        orchestrator._write(report_path, report)
        return {**report, "report_path": str(report_path)}

    return fake_closed_loop


@pytest.fixture(autouse=True)
def _patch_provider_loaders(monkeypatch):
    """Prevent any real .env read when --live paths are exercised."""
    monkeypatch.setattr(orchestrator.image_provider, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(orchestrator.vision_review, "load_dotenv", lambda *_: None)


def test_parse_nodes_rejects_unknown():
    with pytest.raises(SystemExit):
        batch._parse_nodes("unknown_node")


def test_parse_nodes_accepts_subset():
    assert batch._parse_nodes("gray_lantern_station,lamp_wick_store") == [
        "gray_lantern_station",
        "lamp_wick_store",
    ]


def test_check_gates_dry_run_skips_visual():
    report = {
        "status": "completed",
        "stages": [{"status": "passed"}],
        "quality": {"logic_visual_alignment": "passed"},
        "provider_execution": {"automatic_reviewed_staging_ready": False},
    }
    gates = batch.check_gates(report, live=False)
    assert gates["structural"] == "passed"
    assert gates["semantic"] == "passed"
    assert gates["alignment"] == "passed"
    assert gates["visual"] == "skipped"
    assert gates["all_passed"] is False


def test_check_gates_live_passed():
    report = {
        "status": "completed",
        "stages": [{"status": "passed"}],
        "quality": {"logic_visual_alignment": "passed_with_warnings"},
        "provider_execution": {
            "automatic_reviewed_staging_ready": True,
            "candidate_generation_status": "runtime_visuals_ready",
        },
    }
    gates = batch.check_gates(report, live=True)
    assert gates["visual"] == "passed"
    assert gates["all_passed"] is True


def test_check_gates_structural_failure_blocks():
    report = {
        "status": "completed",
        "stages": [{"status": "failed"}],
        "quality": {"logic_visual_alignment": "passed"},
        "provider_execution": {},
    }
    gates = batch.check_gates(report, live=True)
    assert gates["structural"] == "failed"
    assert gates["all_passed"] is False


def test_default_dry_run_compiles_node_without_provider_or_promotion(staging_root):
    """Default dry-run: structural compile succeeds, visual gate skipped, no promotion."""
    output_root = staging_root
    report = batch.run_batch(
        ["gray_lantern_station"],
        output_root,
        dotenv_path=None,
        live=False,
        promote=False,
        max_attempts=1,
        max_workers=2,
    )
    assert report["summary"]["node_count"] == 1
    assert report["summary"]["completed_count"] == 1
    assert report["summary"]["failed_count"] == 0
    assert report["summary"]["promoted_count"] == 0
    assert report["safety"]["provider_called"] is False
    assert report["safety"]["player_runtime_mutated"] is False
    node = report["nodes"][0]
    assert node["status"] == "completed"
    assert node["gates"]["structural"] == "passed"
    assert node["gates"]["visual"] == "skipped"
    assert node["gates"]["all_passed"] is False
    assert node["provider_calls"] == 0
    assert node["promotion"]["applied"] is False
    # Batch report is written to the output root.
    assert (output_root / "map_recompile_batch_report.v0.1.json").is_file()
    # Per-node run report exists and proves the orchestrator ran.
    assert node["run_report_path"] is not None
    run_report = json.loads(
        (ROOT / node["run_report_path"]).read_text(encoding="utf-8")
    )
    assert run_report["provider_execution"]["call_count"] == 0
    # The canonical player dir was not touched.
    canonical = CANONICAL_ROOT / "gray_lantern_station" / "map_compilation_run_report.v0.1.json"
    assert not canonical.exists()


def test_live_with_mocked_closed_loop_promotes_to_canonical(
    tmp_path, staging_root, monkeypatch
):
    """--live + --promote: gates pass and validated artifacts sync to canonical."""
    monkeypatch.setattr(
        orchestrator.map_visual_closed_loop,
        "run_closed_loop",
        _fake_closed_loop_factory(critical_ready=True),
    )
    # Redirect canonical root to a temp dir so the real player dir is untouched.
    temp_canonical = tmp_path / "canonical"
    temp_canonical.mkdir()
    monkeypatch.setattr(batch, "CANONICAL_ROOT", temp_canonical)

    output_root = staging_root
    report = batch.run_batch(
        ["gray_lantern_station"],
        output_root,
        dotenv_path=tmp_path / "fake.env",
        live=True,
        promote=True,
        max_attempts=1,
        max_workers=2,
    )
    node = report["nodes"][0]
    assert node["status"] == "completed"
    assert node["gates"]["all_passed"] is True
    assert node["gates"]["visual"] == "passed"
    assert node["provider_calls"] == 6
    assert node["promotion"]["applied"] is True
    assert report["summary"]["promoted_count"] == 1

    # Canonical dir now has the promoted layered package + compile evidence.
    promoted = temp_canonical / "gray_lantern_station"
    assert (promoted / "layered_map_visual_package.v0.1.json").is_file()
    assert (promoted / "map_compile_package.v0.2.json").is_file()
    assert (promoted / "map_compilation_run_report.v0.1.json").is_file()

    # Path refs inside the promoted layered package point at the canonical dir,
    # not the staging dir.
    layered = json.loads(
        (promoted / "layered_map_visual_package.v0.1.json").read_text(encoding="utf-8")
    )
    source_refs = layered.get("source_refs", {})
    runtime_ref = source_refs.get("map_runtime_package_path", "")
    assert "_recompile_staging" not in runtime_ref
    assert "gray_lantern_station/map_runtime_package.v0.2.json" in runtime_ref
    # Visual asset URLs use the canonical path, not staging.
    for asset in layered.get("media_assets", []):
        url = str(asset.get("url") or "")
        if url:
            assert "_recompile_staging" not in url, url

    # Staging dir still retains the report for review.
    assert (output_root / "gray_lantern_station" / "map_compilation_run_report.v0.1.json").is_file()


def test_live_mocked_failure_blocks_promotion(tmp_path, staging_root, monkeypatch):
    """--live with failing closed loop: visual gate fails, promotion blocked."""
    monkeypatch.setattr(
        orchestrator.map_visual_closed_loop,
        "run_closed_loop",
        _fake_closed_loop_factory(critical_ready=False),
    )
    temp_canonical = tmp_path / "canonical"
    temp_canonical.mkdir()
    monkeypatch.setattr(batch, "CANONICAL_ROOT", temp_canonical)

    output_root = staging_root
    report = batch.run_batch(
        ["gray_lantern_station"],
        output_root,
        dotenv_path=tmp_path / "fake.env",
        live=True,
        promote=True,
        max_attempts=1,
        max_workers=2,
    )
    node = report["nodes"][0]
    assert node["status"] == "completed"
    assert node["gates"]["visual"] == "failed"
    assert node["gates"]["all_passed"] is False
    assert node["promotion"]["applied"] is False
    assert "visual_gate_failed" in node["promotion"]["blocked_reasons"]
    assert report["summary"]["promoted_count"] == 0
    assert report["summary"]["blocked_count"] == 1
    # Canonical dir was not modified.
    assert not (temp_canonical / "gray_lantern_station").exists()
    # Failure report is retained in staging.
    assert (output_root / "gray_lantern_station" / "map_compilation_run_report.v0.1.json").is_file()


def test_promote_without_live_is_blocked(staging_root, monkeypatch):
    """--promote without --live: visual gate skipped, promotion blocked."""
    # Even with a successful dry structural compile, promotion cannot apply
    # because the visual gate is skipped without --live.
    output_root = staging_root
    report = batch.run_batch(
        ["gray_lantern_station"],
        output_root,
        dotenv_path=None,
        live=False,
        promote=True,
        max_attempts=1,
        max_workers=2,
    )
    node = report["nodes"][0]
    assert node["status"] == "completed"
    assert node["gates"]["visual"] == "skipped"
    assert node["gates"]["all_passed"] is False
    assert node["promotion"]["applied"] is False
    assert "visual_gate_skipped_requires_live" in node["promotion"]["blocked_reasons"]
    assert report["summary"]["promoted_count"] == 0


def test_multi_node_dry_run_batch_report_summary(staging_root):
    """Dry-run across all three nodes: summary aggregates correctly."""
    output_root = staging_root
    report = batch.run_batch(
        ["gray_lantern_station", "lamp_wick_store", "old_signal_tower"],
        output_root,
        dotenv_path=None,
        live=False,
        promote=False,
        max_attempts=1,
        max_workers=2,
    )
    assert report["summary"]["node_count"] == 3
    assert report["summary"]["completed_count"] == 3
    assert report["summary"]["failed_count"] == 0
    assert report["summary"]["promoted_count"] == 0
    node_ids = [node["node_id"] for node in report["nodes"]]
    assert node_ids == ["gray_lantern_station", "lamp_wick_store", "old_signal_tower"]
    # Each node has a run report.
    for node in report["nodes"]:
        assert node["run_report_path"] is not None
        assert node["gates"]["structural"] == "passed"
        assert node["gates"]["visual"] == "skipped"


def test_main_requires_dotenv_for_live(tmp_path, monkeypatch):
    """main() rejects --live without --dotenv so no implicit .env read occurs."""
    import sys

    monkeypatch.setattr(sys, "argv", [
        "run_map_recompile_batch.py",
        "--live",
    ])
    with pytest.raises(SystemExit) as exc:
        batch.main()
    assert "--dotenv" in str(exc.value)


def test_main_rejects_unknown_dotenv_path(tmp_path, monkeypatch):
    import sys as _sys

    monkeypatch.setattr(
        _sys,
        "argv",
        [
            "run_map_recompile_batch.py",
            "--live",
            "--dotenv",
            str(tmp_path / "does_not_exist.env"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        batch.main()
    assert "does not exist" in str(exc.value)
