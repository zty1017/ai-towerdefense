"""Background consumer for reviewed map visual compilation jobs."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
MEDIA_TOOLS = ROOT / "tools" / "media"
ASSET_GRAPH_TOOLS = ROOT / "tools" / "asset_graph"
for module_dir in (MEDIA_TOOLS, ASSET_GRAPH_TOOLS):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

import generate_layered_map_visual_candidates as candidate_generator  # noqa: E402
import image_provider  # noqa: E402
import map_compilation_orchestrator  # noqa: E402
import map_visual_closed_loop  # noqa: E402
import map_visual_job_queue  # noqa: E402
import vision_review  # noqa: E402


LAYERED_ROOT = ROOT / "game_data" / "media" / "layered_maps"


def _dotenv_path() -> Path:
    configured = os.environ.get("AI_TD_ENV_FILE")
    if configured:
        return Path(configured).expanduser()
    local = ROOT / ".env"
    if local.is_file():
        return local
    git_pointer = ROOT / ".git"
    if git_pointer.is_file():
        marker = git_pointer.read_text(encoding="utf-8").strip()
        if marker.startswith("gitdir:"):
            git_dir = Path(marker.partition(":")[2].strip()).resolve()
            for parent in git_dir.parents:
                candidate = parent / ".env"
                if (parent / ".git").exists() and candidate.is_file():
                    return candidate
    return local


def enabled() -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    value = os.environ.get("AI_TD_MAP_VISUAL_WORKER", "auto").strip().lower()
    return value not in {"0", "false", "off", "disabled"}


def job_paths() -> list[Path]:
    return sorted(LAYERED_ROOT.glob(f"*/visual_handoff/{map_visual_job_queue.JOB_FILENAME}"))


def list_jobs() -> list[dict[str, Any]]:
    jobs = []
    for path in job_paths():
        try:
            job = map_visual_job_queue.load_json(path)
        except (OSError, ValueError):
            continue
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        jobs.append(
            {
                "job_id": job.get("job_id"),
                "status": job.get("status"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "node_id": Path(str(job.get("output_dir") or "")).name,
                "result": {
                    "closed_loop_status": result.get("closed_loop_status"),
                    "provider_call_count": result.get("provider_call_count", 0),
                    "vision_review_call_count": result.get("vision_review_call_count", 0),
                    "runtime_activated": result.get("runtime_activated", False),
                }
                if result
                else None,
                "failure": job.get("failure"),
            }
        )
    return jobs


def process_job(path: Path) -> dict[str, Any] | None:
    job = map_visual_job_queue.transition(path, "pending", "running", failure=None)
    if job is None:
        return None
    try:
        settings = job.get("settings") or {}
        request_pack_path = Path(str(job["request_pack_path"]))
        output_dir = Path(str(job["output_dir"]))
        pack = candidate_generator.load_json(request_pack_path)
        dotenv = _dotenv_path()
        image_provider.load_dotenv(dotenv)
        vision_review.load_dotenv(dotenv)
        image_profile = image_provider.PROFILES[str(settings["image_profile"])]
        reviewer = vision_review.PROFILES[str(settings["vision_profile"])]
        candidate_dir = output_dir / "visual_candidates" / str(job["job_id"])
        reviewed_dir = output_dir / "reviewed_visual_staging" / str(job["job_id"])
        report = map_visual_closed_loop.run_closed_loop(
            request_pack_path,
            pack,
            candidate_dir,
            reviewed_dir,
            image_profile,
            reviewer,
            max_attempts=int(settings.get("max_attempts") or 2),
            max_workers=int(settings.get("max_workers") or 3),
            generation_timeout=int(settings.get("generation_timeout") or 240),
            review_timeout=int(settings.get("review_timeout") or 180),
        )
        calibration = map_visual_closed_loop.build_calibration_summary(report)
        calibration_path = candidate_dir / "map_visual_calibration_summary.v0.1.json"
        candidate_generator.write_json(calibration_path, calibration)
        result = {
            "closed_loop_status": report.get("status"),
            "report_path": report.get("report_path"),
            "calibration_path": str(calibration_path.resolve()),
            "provider_call_count": report.get("summary", {}).get("provider_call_count", 0),
            "vision_review_call_count": report.get("summary", {}).get(
                "vision_review_call_count", 0
            ),
            "runtime_activated": False,
        }
        if report.get("runtime_critical_roles_ready"):
            map_compilation_orchestrator.apply_reviewed_visuals(
                Path(str(job["input_path"])), output_dir, report
            )
            result["runtime_activated"] = True
            status = "completed"
        else:
            status = "blocked"
            _update_compile_report(output_dir, status, result)
        return map_visual_job_queue.transition(
            path,
            "running",
            status,
            result=result,
            failure=None,
        )
    except Exception as exc:
        try:
            _update_compile_report(
                Path(str(job["output_dir"])),
                "failed",
                {"closed_loop_status": "failed"},
            )
        except (OSError, ValueError, KeyError):
            pass
        return map_visual_job_queue.transition(
            path,
            "running",
            "failed",
            failure={
                "stage": "background_worker",
                "error_type": type(exc).__name__,
            },
        )


def _update_compile_report(output_dir: Path, status: str, result: dict[str, Any]) -> None:
    report_path = output_dir / "map_compilation_run_report.v0.1.json"
    if not report_path.is_file():
        return
    report = candidate_generator.load_json(report_path)
    provider = report.setdefault("provider_execution", {})
    provider["background_job_status"] = status
    provider["candidate_generation_status"] = result.get("closed_loop_status", status)
    provider["call_count"] = result.get("provider_call_count", 0)
    provider["vision_review_call_count"] = result.get("vision_review_call_count", 0)
    candidate_generator.write_json(report_path, report)


class MapVisualWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not enabled() or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="map-visual-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        await self._task
        self._task = None

    async def _run(self) -> None:
        interval = max(0.25, float(os.environ.get("AI_TD_MAP_VISUAL_POLL_SECONDS", "1")))
        while not self._stop.is_set():
            pending = next(
                (
                    path
                    for path in job_paths()
                    if map_visual_job_queue.load_json(path).get("status") == "pending"
                ),
                None,
            )
            if pending is not None:
                await asyncio.to_thread(process_job, pending)
                continue
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                pass


worker = MapVisualWorker()
