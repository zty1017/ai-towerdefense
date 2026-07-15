"""Minimal internal evidence endpoints; never used by the player UI."""

from __future__ import annotations

from fastapi import APIRouter

from ..services import map_visual_worker_service


router = APIRouter()


@router.get("/api/studio/map-visual-jobs")
def get_map_visual_jobs() -> dict:
    jobs = map_visual_worker_service.list_jobs()
    return {
        "worker_enabled": map_visual_worker_service.enabled(),
        "job_count": len(jobs),
        "jobs": jobs,
    }

