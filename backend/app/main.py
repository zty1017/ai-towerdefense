"""FastAPI application entrypoint.

Wires routers and initializes the SQLite schema on startup.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import frontend_mock as frontend_mock_api
from .api import health as health_api
from .api import research as research_api
from .api import sessions as sessions_api
from .api import studio as studio_api
from .config import get_app_title, get_app_version
from .db import init_db
from .services.map_visual_worker_service import worker as map_visual_worker


_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC_MEDIA_ROOTS = {
    "frontend_mock": _REPO_ROOT / "game_data/media/frontend_mock",
    "frontend_runtime_mock": _REPO_ROOT / "game_data/media/frontend_runtime_mock",
    "strategic_map_markers": _REPO_ROOT / "game_data/media/strategic_map_markers",
}
_STATIC_DIRECT_MEDIA_ROOTS = {
    "layered_maps": _REPO_ROOT / "game_data/media/layered_maps",
    "map_components": _REPO_ROOT / "game_data/media/map_components",
    "map_visual_reference": _REPO_ROOT / "game_data/media/map_visual_reference",
}
_FRONTEND_DIR = _REPO_ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the schema exists before serving any request.
    init_db()
    await map_visual_worker.start()
    try:
        yield
    finally:
        await map_visual_worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=get_app_title(),
        version=get_app_version(),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):\d+$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_api.router)
    app.include_router(sessions_api.router)
    app.include_router(research_api.router)
    app.include_router(frontend_mock_api.router)
    app.include_router(studio_api.router)
    _mount_frontend_mock_media(app)
    _mount_frontend(app)
    return app


def _mount_frontend_mock_media(app: FastAPI) -> None:
    """Serve reviewed/generated mock media through the URLs in media manifests."""
    for namespace, media_dir in _STATIC_MEDIA_ROOTS.items():
        for role_dir in ("processed", "generated", "atlas_frames", "atlas_sheets"):
            directory = media_dir / role_dir
            if directory.exists():
                app.mount(
                    f"/assets/{namespace}/{role_dir}",
                    StaticFiles(directory=str(directory)),
                    name=f"{namespace}_{role_dir}",
                )
    for namespace, directory in _STATIC_DIRECT_MEDIA_ROOTS.items():
        if directory.exists():
            app.mount(
                f"/assets/{namespace}",
                StaticFiles(directory=str(directory)),
                name=namespace,
            )


def _mount_frontend(app: FastAPI) -> None:
    """Serve the no-build MVP frontend from the backend in API mode."""
    if _FRONTEND_DIR.exists():
        app.mount(
            "/frontend",
            StaticFiles(directory=str(_FRONTEND_DIR), html=True),
            name="frontend",
        )


app = create_app()
