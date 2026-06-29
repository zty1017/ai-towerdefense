"""FastAPI application entrypoint.

Wires routers and initializes the SQLite schema on startup.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import health as health_api
from .api import research as research_api
from .api import sessions as sessions_api
from .config import get_app_title, get_app_version
from .db import init_db


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
    return app


app = create_app()
