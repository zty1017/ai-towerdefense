"""Regression checks for the split frontend-facing API routers."""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.api import gameplay_runtime, generation_scheduler
from app.main import create_app


def _paths(router) -> set[str]:
    return {
        route.path
        for route in router.routes
        if isinstance(route, APIRoute)
    }


def test_split_frontend_routers_are_visible_in_openapi() -> None:
    expected = _paths(gameplay_runtime.router) | _paths(generation_scheduler.router)
    published = set(create_app().openapi()["paths"])

    assert len(expected) == 59
    assert expected <= published


def test_scheduler_and_gameplay_router_domains_do_not_overlap() -> None:
    scheduler_paths = _paths(generation_scheduler.router)
    gameplay_paths = _paths(gameplay_runtime.router)

    assert scheduler_paths
    assert gameplay_paths
    assert scheduler_paths.isdisjoint(gameplay_paths)
    assert all("/generation-schedule" in path for path in scheduler_paths)
    assert all("/generation-schedule" not in path for path in gameplay_paths)
