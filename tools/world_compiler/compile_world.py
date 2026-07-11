#!/usr/bin/env python3
"""Generate or lower one world seed into game-ready content and map packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from world_compiler import (
    WorldCompilationError,
    _load,
    compile_candidate,
    generate_candidate,
    validate_candidate,
    validate_seed,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--candidate", type=Path, help="Use an existing validated candidate instead of a provider call.")
    parser.add_argument("--profile", default="ark_deepseek_v4_flash")
    parser.add_argument("--allow-provider", action="store_true")
    parser.add_argument("--output-root", type=Path, default=Path("content/generated_worlds"))
    parser.add_argument("--compile-map", action="store_true")
    parser.add_argument(
        "--live-map-visuals",
        action="store_true",
        help="Generate all layered map visual candidates during map compilation.",
    )
    parser.add_argument("--map-image-profile", default="agnes_image_flash")
    parser.add_argument("--dotenv", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        seed = _load(args.seed.resolve())
        seed_errors = validate_seed(seed)
        if seed_errors:
            raise WorldCompilationError(seed_errors[0])
        if args.candidate:
            candidate = _load(args.candidate.resolve())
            provenance = {
                "generation_mode": "offline_validated_candidate",
                "provider_call_performed": False,
                "raw_prompt_stored": False,
                "raw_response_stored": False,
            }
        elif args.validate_only:
            print(json.dumps({"status": "seed_valid", "seed_id": seed["seed_id"]}, ensure_ascii=False))
            return 0
        else:
            candidate, provenance = generate_candidate(
                seed, profile_name=args.profile, allow_provider=args.allow_provider
            )
        errors = validate_candidate(candidate)
        if errors:
            raise WorldCompilationError(errors[0])
        if args.validate_only:
            print(json.dumps({"status": "candidate_valid", "world_id": candidate["world_id"]}, ensure_ascii=False))
            return 0
        result = compile_candidate(
            seed, candidate, args.output_root.resolve(), provenance=provenance,
            compile_map=args.compile_map,
            live_map_visuals=args.live_map_visuals,
            map_image_profile=args.map_image_profile,
            dotenv_path=args.dotenv.resolve() if args.dotenv else None,
        )
    except (OSError, ValueError, json.JSONDecodeError, WorldCompilationError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
