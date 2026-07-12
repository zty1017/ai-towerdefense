"""Pytest fixtures: each test gets an isolated SQLite database under tmp_path."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a path for a throwaway SQLite file under tmp_path."""
    return tmp_path / "test_app.db"


@pytest.fixture()
def app_env(tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point APP_DB_PATH at a temp file and reset the cached connection."""
    monkeypatch.setenv("APP_DB_PATH", str(tmp_db_path))
    # Legacy API tests intentionally keep synchronous completion. Dedicated
    # worker tests explicitly select background mode and exercise real polling.
    monkeypatch.setenv("AI_TD_RESEARCH_WORKER_MODE", "inline")
    # Reset module-level cached connection so the new env var takes effect.
    from app import db as db_module

    db_module.reset_connection()
    db_module.init_db(str(tmp_db_path))
    yield tmp_db_path
    db_module.reset_connection()


@pytest.fixture()
def client(app_env: Path):
    """A TestClient bound to the isolated DB."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def raw_conn(app_env: Path) -> sqlite3.Connection:
    """A raw sqlite3 connection for direct table inspection in tests."""
    conn = sqlite3.connect(str(app_env))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
