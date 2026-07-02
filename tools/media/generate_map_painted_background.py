#!/usr/bin/env python3
"""Generate a painted tower-defense map background with a live image provider.

The script downloads a local candidate image only. It does not update runtime
packages by itself because every candidate still needs alignment review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402


DEFAULT_BATTLE = ROOT / "game_data/demo/first_battle_config.json"
DEFAULT_OUTPUT = ROOT / "game_data/media/map_visual_reference/mvp_battle_painted_candidate_agnes_01.png"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_prompt(battle: dict[str, Any]) -> str:
    waypoints = ((battle.get("paths") or [{}])[0]).get("waypoints", [])
    route = " -> ".join(f"({p['x']},{p['y']})" for p in waypoints if isinstance(p, dict))
    return (
        "Game-ready 2D pseudo-isometric tower defense battle map background, "
        "16:9 composition, dark lantern fantasy frontier, hand-painted strategy game art. "
        "A winding readable dirt road enters from the right middle shadow breach and exits toward a fortified lantern core on the left side. "
        "Place 8 to 12 empty circular stone tower foundations naturally embedded beside the road, not as UI icons. "
        "Include dark forest edges, broken stone ruins, warm lantern posts, a small signal beacon, subtle purple corruption at the enemy entrance, "
        "and a protected lantern station core. "
        "The map is completely empty of living figures. Absolutely no people, no humans, no humanoids, no soldiers, no NPCs, no creatures, no enemies, no animals, no deployed towers. "
        "No user interface, no text, no labels, no grid, no watermark, no logo. "
        "Keep the road and tower foundations clear enough for gameplay overlays. "
        f"Logical route guide for composition only: {route}."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--battle-config", default=str(DEFAULT_BATTLE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if not args.live:
        print("Refusing to contact image provider without --live.", file=sys.stderr)
        return 2

    battle_path = Path(args.battle_config)
    if not battle_path.is_absolute():
        battle_path = ROOT / battle_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    dotenv_path = Path(args.dotenv)
    if not dotenv_path.is_absolute():
        dotenv_path = ROOT / dotenv_path

    profile = image_provider.PROFILES[args.image_profile]
    image_provider.parse_size(args.size)
    image_provider.load_dotenv(dotenv_path)

    battle = load_json(battle_path)
    if not isinstance(battle, dict):
        print("Battle config root must be an object.", file=sys.stderr)
        return 1

    prompt = build_prompt(battle)
    response = image_provider.generate_image(
        profile,
        prompt,
        size=args.size,
        timeout=args.request_timeout,
    )
    image_url = image_provider.extract_image_url(response)
    image_provider.download_image(image_url, output_path, timeout=args.request_timeout)

    sidecar = {
        "schema_version": "map_painted_candidate.v0.1",
        "candidate_path": output_path.relative_to(ROOT).as_posix()
        if output_path.resolve().is_relative_to(ROOT.resolve())
        else str(output_path),
        "battle_config": battle_path.relative_to(ROOT).as_posix()
        if battle_path.resolve().is_relative_to(ROOT.resolve())
        else str(battle_path),
        "provider_profile": profile.name,
        "model": profile.model,
        "size": args.size,
        "prompt_summary": [
            "2D pseudo-isometric tower defense map",
            "no UI, text, grid, enemies, towers, characters, watermark, or logo",
            "road and empty tower foundations remain clear for runtime overlays",
        ],
        "review_status": "candidate_needs_alignment_review",
    }
    sidecar_path = output_path.with_suffix(output_path.suffix + ".candidate.json")
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote candidate: {output_path}")
    print(f"Wrote sidecar: {sidecar_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
