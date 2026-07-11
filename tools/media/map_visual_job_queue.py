"""Small file-backed queue for asynchronous map visual compilation."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "map_visual_background_job.v0.1"
JOB_FILENAME = f"{SCHEMA_VERSION}.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"job root must be an object: {path}")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def enqueue_job(
    *,
    input_path: Path,
    output_dir: Path,
    request_pack_path: Path,
    image_profile: str,
    vision_profile: str,
    max_attempts: int,
    max_workers: int,
    generation_timeout: int,
    review_timeout: int,
) -> Path:
    """Create or retain one idempotent job beside the visual handoff."""
    fingerprint = hashlib.sha256(request_pack_path.read_bytes()).hexdigest()
    path = output_dir / "visual_handoff" / JOB_FILENAME
    if path.exists():
        existing = load_json(path)
        if existing.get("request_fingerprint") == fingerprint and existing.get("status") in {
            "pending",
            "running",
            "completed",
        }:
            return path
    job = {
        "schema_version": SCHEMA_VERSION,
        "job_id": f"mapvis_{fingerprint[:20]}",
        "status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "request_fingerprint": fingerprint,
        "input_path": str(input_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "request_pack_path": str(request_pack_path.resolve()),
        "settings": {
            "image_profile": image_profile,
            "vision_profile": vision_profile,
            "max_attempts": max_attempts,
            "max_workers": max_workers,
            "generation_timeout": generation_timeout,
            "review_timeout": review_timeout,
        },
        "result": None,
        "failure": None,
        "policy": {
            "stores_secrets": False,
            "stores_raw_prompts": False,
            "runtime_activation_requires_reviewed_critical_roles": True,
        },
    }
    return write_json_atomic(path, job)


def transition(path: Path, expected: str, status: str, **fields: Any) -> dict[str, Any] | None:
    job = load_json(path)
    if job.get("status") != expected:
        return None
    job.update(fields)
    job["status"] = status
    job["updated_at"] = now_iso()
    write_json_atomic(path, job)
    return job

