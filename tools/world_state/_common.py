"""Shared helpers for world_state validators.

Keeps the forbidden-field set and JSON loading consistent across
validate_run_world_state.py and validate_world_delta.py. This module never
reads .env and never calls a real provider.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Field names that must never appear anywhere in a run world state or delta.
# Mirrors the policy in tools/asset_graph/validate_workflow.py.
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)

# Words banned from player-visible text. Word-boundary matched, case-insensitive.
# These are technical / studio-layer terms that must not leak to the player.
BANNED_PLAYER_WORDS: frozenset[str] = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "schema",
        "traceback",
        "prompt",
        "mock",
        "simulation",
        "trace",
        "compiler",
        "token",
    }
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject forbidden keys anywhere in the document."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(
                    f"forbidden field '{child_path}' is not allowed in a "
                    f"run world state / delta (must not carry "
                    f"provider/trace/raw payloads)"
                )
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_forbidden_fields(child, child_path, errors)


def get_jsonschema_validator(schema: dict[str, Any]):
    """Return the best available jsonschema validator for the given schema.

    jsonschema 3.x only ships Draft7Validator; newer versions ship
    Draft202012Validator. Our schemas only use features supported by Draft 7
    (const, oneOf, additionalProperties, enum, etc.), so Draft7Validator is
    sufficient as the jsonschema backend.
    """
    try:
        from jsonschema import Draft202012Validator  # type: ignore

        return Draft202012Validator(schema)
    except Exception:  # pragma: no cover - depends on installed version
        pass
    try:
        from jsonschema import Draft7Validator  # type: ignore

        return Draft7Validator(schema)
    except Exception:
        return None


def has_jsonschema() -> bool:
    """Return True if jsonschema is importable."""
    try:
        import jsonschema  # noqa: F401

        return True
    except Exception:
        return False
