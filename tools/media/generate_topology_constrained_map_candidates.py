#!/usr/bin/env python3
"""Generate review-only map candidates from topology-constrained prompt packs.

This is for map-as-compiled-object iteration. It reads prompt briefs that are
already derived from MapRuntimePackage topology, calls an image provider only
when --live is passed, and writes candidate sidecars for later review gates.
It never updates MapRuntimePackage and never publishes visual layers.
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


DEFAULT_PROMPT_PACK = ROOT / "examples/review_packs/topology_constrained_map_prompt_pack.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates_topology_v1"
DEFAULT_NODE_ID = "old_signal_tower"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def select_prompt(pack: dict[str, Any], node_id: str, include_fallback: bool) -> dict[str, Any]:
    prompts = [prompt for prompt in as_list(pack.get("prompts")) if isinstance(prompt, dict)]
    matches = [prompt for prompt in prompts if prompt.get("node_id") == node_id]
    if not matches:
        raise RuntimeError(f"prompt pack does not contain node_id={node_id!r}")
    if include_fallback:
        return matches[0]
    preferred = [
        prompt
        for prompt in matches
        if isinstance(prompt.get("status"), str) and str(prompt.get("status")).startswith("prompt_ready")
    ]
    if preferred:
        return preferred[0]
    raise RuntimeError(f"node_id={node_id!r} has no prompt_ready entry; pass --include-fallback to use fallback prompts")


def build_provider_prompt(prompt_entry: dict[str, Any]) -> str:
    negative = ", ".join(str(item) for item in as_list(prompt_entry.get("negative_constraints")))
    gates = ", ".join(str(item) for item in as_list(prompt_entry.get("required_review_gates")))
    return (
        f"{prompt_entry.get('prompt_brief')}\n\n"
        "Hard requirements for this image:\n"
        "- It must be a single clean game map background with no UI and no overlay symbols.\n"
        "- Roads, landmarks, and flat build clearings must be visible enough for a later runtime overlay review.\n"
        "- Do not include enemies, towers, projectiles, characters, text, arrows, labels, grid lines, cards, or panels.\n"
        "- Keep the protected objective visually readable but not centered as a giant monument unless the topology says so.\n"
        f"- Negative constraints: {negative or 'none'}.\n"
        f"- Later review gates: {gates or 'standard topology and readability gates'}."
    )


def write_sidecar(
    output_path: Path,
    prompt_pack_path: Path,
    prompt_entry: dict[str, Any],
    provider_prompt: str,
    profile: image_provider.ImageProfile,
    size: str,
    *,
    live: bool,
    provider_called: bool,
) -> None:
    image_exists = output_path.exists()
    sidecar = {
        "schema_version": "topology_constrained_map_candidate.v0.1",
        "candidate_id": f"{prompt_entry.get('node_id')}.topology_constrained_candidate",
        "candidate_path": rel(output_path),
        "prompt_pack_path": rel(prompt_pack_path),
        "node_id": prompt_entry.get("node_id"),
        "source_prompt_status": prompt_entry.get("status"),
        "primary_use": prompt_entry.get("primary_use"),
        "topology_policy": prompt_entry.get("topology_policy"),
        "runtime_package_path": prompt_entry.get("runtime_package_path"),
        "runtime_topology_summary": prompt_entry.get("runtime_topology_summary"),
        "provider_profile": profile.name if live or image_exists else None,
        "model": profile.model if live or image_exists else None,
        "size": size,
        "prompt_sha256": hashlib.sha256(provider_prompt.encode("utf-8")).hexdigest(),
        "image_exists": image_exists,
        "image_size_bytes": output_path.stat().st_size if image_exists else 0,
        "provider_called_this_run": provider_called,
        "generation_status": (
            "live_generated"
            if provider_called
            else ("existing_image_sidecar_refreshed" if image_exists else "dry_run_sidecar")
        ),
        "review_status": "candidate_needs_alignment_overlay_and_visual_review",
        "promotion_allowed_now": False,
        "promotion_policy": "must not update runtime package or published visual layer without explicit promotion report",
        "required_review_gates": prompt_entry.get("required_review_gates"),
        "negative_constraints": prompt_entry.get("negative_constraints"),
    }
    write_json(output_path.with_suffix(output_path.suffix + ".candidate.json"), sidecar)


def generate_candidate(
    prompt_pack_path: Path,
    prompt_entry: dict[str, Any],
    output_dir: Path,
    profile: image_provider.ImageProfile,
    size: str,
    timeout: int,
    *,
    live: bool,
    refresh_sidecar_only: bool,
) -> Path:
    node_id = str(prompt_entry.get("node_id") or "unknown_node")
    output_path = output_dir / f"{node_id}.topology_constrained_candidate.png"
    provider_prompt = build_provider_prompt(prompt_entry)
    provider_called = False
    if live and not refresh_sidecar_only:
        response = image_provider.generate_image(profile, provider_prompt, size=size, timeout=timeout)
        image_url = image_provider.extract_image_url(response)
        image_provider.download_image(image_url, output_path, timeout=timeout)
        provider_called = True
    write_sidecar(
        output_path,
        prompt_pack_path,
        prompt_entry,
        provider_prompt,
        profile,
        size,
        live=live,
        provider_called=provider_called,
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate topology-constrained map candidates.")
    parser.add_argument("--prompt-pack", default=str(DEFAULT_PROMPT_PACK))
    parser.add_argument("--node-id", action="append", default=[], help="Node id to generate. Defaults to old_signal_tower.")
    parser.add_argument("--include-fallback", action="store_true", help="Allow fallback prompt entries.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--refresh-sidecars-only", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    prompt_pack_path = Path(args.prompt_pack)
    if not prompt_pack_path.is_absolute():
        prompt_pack_path = ROOT / prompt_pack_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    image_provider.parse_size(args.size)
    profile = image_provider.PROFILES[args.image_profile]

    if args.refresh_sidecars_only:
        print("Refreshing sidecars without live provider calls.")
    elif args.live:
        dotenv_path = Path(args.dotenv)
        if not dotenv_path.is_absolute():
            dotenv_path = ROOT / dotenv_path
        image_provider.load_dotenv(dotenv_path)
    else:
        print("Dry run: sidecars only. Pass --live to call image provider.")

    pack = load_json(prompt_pack_path)
    if not isinstance(pack, dict):
        raise RuntimeError(f"{prompt_pack_path} root must be an object")
    node_ids = args.node_id or [DEFAULT_NODE_ID]
    outputs = []
    failures = []
    for node_id in node_ids:
        try:
            prompt_entry = select_prompt(pack, node_id, args.include_fallback)
            output = generate_candidate(
                prompt_pack_path,
                prompt_entry,
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
            failures.append({"node_id": node_id, "error": str(exc)[:500]})
            print(f"FAILED candidate for {node_id}: {exc}", file=sys.stderr)
            continue
        outputs.append(output)
        print(f"Wrote candidate sidecar: {output.with_suffix(output.suffix + '.candidate.json')}")
        if args.live and not args.refresh_sidecars_only:
            print(f"Wrote candidate image: {output}")
    if failures:
        failure_path = output_dir / "topology_constrained_candidate_failures.json"
        write_json(failure_path, {"failures": failures})
        print(f"Failure count: {len(failures)}")
        print(f"Wrote failures: {failure_path}")
    print(f"Candidate count: {len(outputs)}")
    return 0 if outputs else 1


if __name__ == "__main__":
    raise SystemExit(main())
