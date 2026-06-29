# AI-Compiled Tower Defense — Backend

FastAPI + SQLite backend for the AI-compiled tower defense asset compiler MVP.

The backend provides anonymous session management: each session is identified by
an opaque, cryptographically-random `session_id`, and all per-session state is
isolated by that id. There is no registration, login, or PII collection.

## Layout

```
backend/
  app/
    main.py          # FastAPI app factory and entrypoint
    config.py        # env-based config (never reads .env)
    db.py            # sqlite3 connection + schema init
    models.py        # Pydantic v2 models
    api/
      health.py      # GET /api/health
      sessions.py    # session routes
  tests/
    conftest.py      # tmp_path-isolated SQLite fixtures
    test_sessions.py
```

## Configuration

All configuration is via environment variables with safe defaults. The backend
never reads `.env`.

| Variable      | Default                       | Purpose                          |
| ------------- | ----------------------------- | -------------------------------- |
| `APP_DB_PATH` | `backend/data/app.db`         | SQLite database file path        |
| `APP_TITLE`   | `AI-Compiled Tower Defense…`  | FastAPI app title                |
| `APP_VERSION` | `0.1.0`                       | FastAPI app version              |

## Running

```bash
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

The schema is created automatically on startup.

## API

| Method | Path                                | Description                       |
| ------ | ----------------------------------- | --------------------------------- |
| GET    | `/api/health`                       | Health check                      |
| POST   | `/api/sessions`                     | Create an anonymous session       |
| GET    | `/api/sessions/{session_id}`        | Read a session (404 if missing)   |
| POST   | `/api/sessions/{session_id}/reset`  | Reset per-session demo data       |

## Tests

```bash
pytest backend/tests
```

Tests use `tmp_path` to point `APP_DB_PATH` at a throwaway SQLite file so the
main database is never touched.
