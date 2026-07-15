#!/usr/bin/env python3
"""构建黑客松源码包，排除密钥、缓存和可重建的媒体中间产物。"""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
IGNORED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}
IGNORED_PREFIXES = (
    "release/",
    "submission/final/",
    "submission/assets/screenshots/",
    "submission/generated/",
    "game_data/media/layered_maps/_exploration/",
    "game_data/media/map_components/candidates/",
    "game_data/media/sprite_regeneration_candidates/",
    "game_data/media/sprite_repair_candidates/",
    "game_data/media/frontend_mock/generated/",
    "game_data/media/frontend_runtime_mock/generated/",
)


def ignored(relative: Path) -> bool:
    parts = relative.parts
    value = relative.as_posix()
    if any(part in IGNORED_DIRS for part in parts):
        return True
    if relative.name == ".env" or relative.suffix in {".pyc", ".sqlite", ".sqlite3", ".db"}:
        return True
    if value.startswith(IGNORED_PREFIXES):
        return True
    if value.startswith("game_data/media/map_visual_reference/node_candidates"):
        return True
    if "/layers/" in f"/{value}" and (
        value.startswith("game_data/media/layered_maps/")
        or value.startswith("content/generated_world_media/")
    ):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    file_count = 0
    raw_bytes = 0
    with ZipFile(args.output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if ignored(relative):
                continue
            archive.write(path, Path("Compiler") / relative)
            file_count += 1
            raw_bytes += path.stat().st_size
    print(
        {
            "output": str(args.output),
            "file_count": file_count,
            "raw_bytes": raw_bytes,
            "zip_bytes": args.output.stat().st_size,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
