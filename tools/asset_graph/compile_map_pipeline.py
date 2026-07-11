#!/usr/bin/env python3
"""Compile one map through the existing logic, render, layer, and gate stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from map_compilation_orchestrator import MapCompilationError, compile_map, plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--live-visuals", action="store_true")
    parser.add_argument("--image-profile", default="agnes_image_flash")
    parser.add_argument("--dotenv", type=Path)
    parser.add_argument("--visual-request-timeout", type=int, default=240)
    parser.add_argument("--visual-max-workers", type=int, default=3)
    args = parser.parse_args()
    try:
        result = (
            plan(args.input.resolve(), args.output_dir.resolve())
            if args.dry_run
            else compile_map(
                args.input.resolve(),
                args.output_dir.resolve(),
                resume=args.resume,
                force=args.force,
                live_visuals=args.live_visuals,
                image_profile=args.image_profile,
                dotenv_path=args.dotenv,
                visual_request_timeout=args.visual_request_timeout,
                visual_max_workers=args.visual_max_workers,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError, MapCompilationError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
