"""Application configuration.

Reads only from environment variables with safe defaults. Never reads `.env`.
"""
from __future__ import annotations

import os
from pathlib import Path

# Default SQLite path lives under backend/data so tests and dev runs have a
# stable location. Override with APP_DB_PATH for tests or deployments.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def get_db_path() -> str:
    """Return the SQLite database file path from APP_DB_PATH or the default."""
    return os.environ.get("APP_DB_PATH", str(_DEFAULT_DB_PATH))


def get_app_title() -> str:
    return os.environ.get("APP_TITLE", "AI-Compiled Tower Defense Backend")


def get_app_version() -> str:
    return os.environ.get("APP_VERSION", "0.1.0")
