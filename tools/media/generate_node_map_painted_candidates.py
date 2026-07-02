#!/usr/bin/env python3
"""Generate node-specific painted map candidates from battle configs.

This script creates review-only candidate images and sidecars. It never updates
MapRuntimePackage or publishes the candidate by itself; promotion remains a
separate reviewed step because runtime truth must stay in MapRuntimePackage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402


DEFAULT_BATTLE_CONFIGS = [
    ROOT / "game_data/demo/first_battle_config.json",
    ROOT / "game_data/demo/wick_store_pressure_battle_config.json",
    ROOT / "game_data/demo/old_signal_tower_pressure_battle_config.json",
]
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates"


NODE_VISUAL_DIRECTIONS = {
    "gray_lantern_station": (
        "fortified lantern relay station at the left side, pine forest, broken walls, "
        "warm amber lamps, a single readable dirt road, empty stone tower foundations"
    ),
    "lamp_wick_store": (
        "lamp-wick supply depot, old pipes and storage sheds, amber dust, coiled cables, "
        "two readable service roads, empty reinforced tower pads beside the roads"
    ),
    "old_signal_tower": (
        "ruined signal tower on a cold ridge, broken antenna frames, blue-violet echo light, "
        "split ridge paths, empty tower foundations and signal maintenance platforms"
    ),
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def route_summary(battle: dict[str, Any]) -> str:
    parts = []
    for index, route in enumerate(battle.get("paths", []), start=1):
        if not isinstance(route, dict):
            continue
        waypoints = [point for point in route.get("waypoints", []) if isinstance(point, dict)]
        turn_count = max(0, len(waypoints) - 2)
        entry = route.get("entry_label") or "outer edge"
        exit_label = route.get("exit_label") or "protected core"
        parts.append(
            f"route {index} enters from {entry}, bends {turn_count} time(s), and leads toward {exit_label}"
        )
    return "; ".join(parts) or "one readable dirt path across the battlefield"


def target_summary(battle: dict[str, Any]) -> str:
    core = battle.get("core_target", {})
    optional = battle.get("optional_targets", [])
    names = []
    if isinstance(core, dict):
        names.append(str(core.get("display_name") or core.get("target_id") or "core target"))
    for target in optional:
        if isinstance(target, dict):
            names.append(str(target.get("display_name") or target.get("target_id") or "side target"))
    return ", ".join(names) if names else "one protected core"


def build_prompt(battle: dict[str, Any]) -> str:
    node_id = str(battle.get("node_id") or "unknown_node")
    display_name = str(battle.get("display_name") or node_id)
    grid = battle.get("grid", {})
    grid_desc = f"{grid.get('width_cells', 16)} by {grid.get('height_cells', 9)} logical battlefield"
    direction = NODE_VISUAL_DIRECTIONS.get(
        node_id,
        "dark lantern fantasy frontier battlefield, readable roads, empty tower foundations",
    )
    return (
        "Game-ready 2D pseudo-isometric tower defense battle map background, 16:9 wide composition, "
        "hand-painted strategy game art, browser game readable, no UI. "
        f"Map node: {display_name}. Visual direction: {direction}. "
        f"Use this logical guide only for composition, not visible grid: {grid_desc}; {route_summary(battle)}. "
        f"Protected targets: {target_summary(battle)}. "
        "The image must show a complete natural battlefield filling the whole frame, with terrain-integrated dirt paths and clear empty build pads. "
        "Build pads must be flat low circular foundations only, not watchtowers, not turrets, not castles, not vertical tower structures. "
        "Use fantasy dirt roads, stone paths, pipes, or ridge paths only; no modern asphalt highways and no road lane markings. "
        "No characters, no humans, no NPCs, no enemies, no monsters, no animals, no deployed towers, no projectiles, no combat effects. "
        "No text, no labels, no numbers, no arrow symbols, no diagram marks, no logo, no watermark, no UI panels, no cards, no grid overlay. "
        "Leave road and tower foundation areas visually clear for runtime overlays. "
        "Style should feel like a polished tower-defense level map, not a technical diagram."
    )


def write_sidecar(
    output_path: Path,
    battle_path: Path,
    battle: dict[str, Any],
    profile: image_provider.ImageProfile,
    size: str,
    prompt: str,
    *,
    live: bool,
    provider_called: bool,
) -> None:
    image_exists = output_path.exists()
    sidecar = {
        "schema_version": "node_map_painted_candidate.v0.1",
        "candidate_id": f"{battle.get('node_id')}.painted_candidate",
        "candidate_path": rel(output_path),
        "battle_config": rel(battle_path),
        "node_id": battle.get("node_id"),
        "display_name": battle.get("display_name"),
        "provider_profile": profile.name if live or image_exists else None,
        "model": profile.model if live or image_exists else None,
        "size": size,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "image_exists": image_exists,
        "image_size_bytes": output_path.stat().st_size if image_exists else 0,
        "provider_called_this_run": provider_called,
        "generation_status": (
            "live_generated" if provider_called else ("existing_image_sidecar_refreshed" if image_exists else "dry_run_sidecar")
        ),
        "prompt_summary": [
            "node-specific pseudo-isometric tower-defense map",
            "no UI, text, grid, enemies, towers, characters, watermark, or logo",
            "empty tower foundations and roads remain clear for runtime overlays",
        ],
        "review_status": "candidate_needs_alignment_and_visual_review",
        "promotion_policy": "must not update runtime package without explicit review",
    }
    sidecar_path = output_path.with_suffix(output_path.suffix + ".candidate.json")
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_candidate(
    battle_path: Path,
    output_dir: Path,
    profile: image_provider.ImageProfile,
    size: str,
    timeout: int,
    *,
    live: bool,
    refresh_sidecar_only: bool,
) -> Path:
    battle = load_json(battle_path)
    if not isinstance(battle, dict):
        raise RuntimeError(f"{battle_path} root must be an object")
    node_id = str(battle.get("node_id") or battle_path.stem)
    output_path = output_dir / f"{node_id}.painted_candidate.png"
    prompt = build_prompt(battle)
    provider_called = False
    if live and not refresh_sidecar_only:
        response = image_provider.generate_image(profile, prompt, size=size, timeout=timeout)
        image_url = image_provider.extract_image_url(response)
        image_provider.download_image(image_url, output_path, timeout=timeout)
        provider_called = True
    write_sidecar(
        output_path,
        battle_path,
        battle,
        profile,
        size,
        prompt,
        live=live,
        provider_called=provider_called,
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate node-specific map painted candidates.")
    parser.add_argument(
        "--battle-config",
        action="append",
        default=[],
        help="Battle config path. May be provided multiple times. Defaults to all MVP battle configs.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--refresh-sidecars-only",
        action="store_true",
        help="Refresh candidate sidecars for existing images without calling the provider.",
    )
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    image_provider.parse_size(args.size)
    profile = image_provider.PROFILES[args.image_profile]

    battle_paths = [Path(path) for path in args.battle_config] or DEFAULT_BATTLE_CONFIGS
    battle_paths = [path if path.is_absolute() else ROOT / path for path in battle_paths]

    if args.refresh_sidecars_only:
        print("Refreshing sidecars without live provider calls.")
    elif args.live:
        dotenv_path = Path(args.dotenv)
        if not dotenv_path.is_absolute():
            dotenv_path = ROOT / dotenv_path
        image_provider.load_dotenv(dotenv_path)
    else:
        print("Dry run: sidecars only. Pass --live to call image provider.")

    outputs = []
    failures = []
    for battle_path in battle_paths:
        try:
            output = generate_candidate(
                battle_path,
                output_dir,
                profile,
                args.size,
                args.request_timeout,
                live=args.live,
                refresh_sidecar_only=args.refresh_sidecars_only,
            )
        except Exception as exc:  # pragma: no cover - live provider failure path
            if not args.continue_on_error:
                raise
            failures.append({"battle_config": rel(battle_path), "error": str(exc)[:500]})
            print(f"FAILED candidate for {battle_path}: {exc}", file=sys.stderr)
            continue
        outputs.append(output)
        print(f"Wrote candidate sidecar: {output.with_suffix(output.suffix + '.candidate.json')}")
        if args.live and not args.refresh_sidecars_only:
            print(f"Wrote candidate image: {output}")
    print(f"Candidate count: {len(outputs)}")
    if failures:
        failure_path = output_dir / "node_map_candidate_failures.json"
        failure_path.write_text(json.dumps({"failures": failures}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Failure count: {len(failures)}")
        print(f"Wrote failures: {failure_path}")
    return 0 if outputs else 1


if __name__ == "__main__":
    raise SystemExit(main())
