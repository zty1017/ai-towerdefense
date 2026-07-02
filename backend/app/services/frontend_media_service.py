"""Fixture-backed frontend media service.

This service owns the reviewed frontend media manifests, runtime art kit, and
atlas payloads used by the no-build MVP frontend. It never calls providers or
reads `.env`; it only loads checked-in fixture artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]

_FRONTEND_RUNTIME_ART_KIT = (
    _REPO_ROOT / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json"
)
_MEDIA_MANIFEST = (
    _REPO_ROOT / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json"
)
_ANIMATION_SEED_MANIFEST = (
    _REPO_ROOT / "game_data/media/frontend_mock/frontend_animation_seed_manifest.v0.1.json"
)
_MEDIA_ATLAS_MANIFEST = (
    _REPO_ROOT / "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json"
)
_RUNTIME_ART_MEDIA_MANIFEST = (
    _REPO_ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json"
)
_RUNTIME_ART_ANIMATION_SEED_MANIFEST = (
    _REPO_ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_animation_seed_manifest.v0.1.json"
)
_RUNTIME_ART_ATLAS_MANIFEST = (
    _REPO_ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json"
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_runtime_art_kit() -> dict[str, Any]:
    return _load_json(_FRONTEND_RUNTIME_ART_KIT)


def load_media_manifest() -> dict[str, Any]:
    return _load_json(_MEDIA_MANIFEST)


def load_animation_seed_manifest() -> dict[str, Any]:
    return _load_json(_ANIMATION_SEED_MANIFEST)


def load_media_atlas_manifest() -> dict[str, Any]:
    return _load_json(_MEDIA_ATLAS_MANIFEST)


def load_runtime_art_media_manifest() -> dict[str, Any]:
    return _load_json(_RUNTIME_ART_MEDIA_MANIFEST)


def load_runtime_art_animation_seed_manifest() -> dict[str, Any]:
    return _load_json(_RUNTIME_ART_ANIMATION_SEED_MANIFEST)


def load_runtime_art_atlas_manifest() -> dict[str, Any]:
    return _load_json(_RUNTIME_ART_ATLAS_MANIFEST)


def frontend_media_payload() -> dict[str, Any]:
    return {
        "media_manifest": load_media_manifest(),
        "animation_seed_manifest": load_animation_seed_manifest(),
        "media_atlas_manifest": load_media_atlas_manifest(),
        "animation_pipeline_status": "virtual_atlas_ready_video_frames_not_generated",
    }


def runtime_art_payload() -> dict[str, Any]:
    return {
        "runtime_art_kit": load_runtime_art_kit(),
        "runtime_art_media_manifest": load_runtime_art_media_manifest(),
        "runtime_art_animation_seed_manifest": (
            load_runtime_art_animation_seed_manifest()
        ),
        "runtime_art_atlas_manifest": load_runtime_art_atlas_manifest(),
        "runtime_art_pipeline_status": (
            "developer_compiled_virtual_atlas_ready_video_frames_not_generated"
        ),
    }
