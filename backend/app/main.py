"""FastAPI application entrypoint.

Wires routers and initializes the SQLite schema on startup.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import frontend_mock as frontend_mock_api
from .api import health as health_api
from .api import research as research_api
from .api import sessions as sessions_api
from .config import get_app_title, get_app_version
from .db import init_db


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_MOCK_MEDIA_DIR = _REPO_ROOT / "game_data/media/frontend_mock"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the schema exists before serving any request.
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=get_app_title(),
        version=get_app_version(),
        lifespan=lifespan,
    )
    app.include_router(health_api.router)
    app.include_router(sessions_api.router)
    app.include_router(research_api.router)
    app.include_router(frontend_mock_api.router)
    _mount_frontend_mock_media(app)
    return app


def _mount_frontend_mock_media(app: FastAPI) -> None:
    """Serve reviewed/generated mock media through the URLs in media manifests."""
    for role_dir in ("processed", "generated"):
        directory = _FRONTEND_MOCK_MEDIA_DIR / role_dir
        if directory.exists():
            app.mount(
                f"/assets/frontend_mock/{role_dir}",
                StaticFiles(directory=str(directory)),
                name=f"frontend_mock_{role_dir}",
            )


app = create_app()
