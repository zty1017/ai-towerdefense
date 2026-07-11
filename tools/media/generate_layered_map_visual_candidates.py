#!/usr/bin/env python3
"""Generate review-only candidates from a layered map visual request pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402


PACK_VERSION = "map_layered_visual_generation_request_pack.v0.1"
REPORT_VERSION = "layered_map_visual_candidate_generation_run.v0.1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_id(value: Any) -> str:
    result = "".join(
        character if character.isalnum() or character in "_.-" else "_"
        for character in str(value or "candidate")
    )[:160]
    return result or "candidate"


def selected_requests(pack: dict[str, Any], roles: list[str]) -> list[dict[str, Any]]:
    requests = [item for item in pack.get("requests", []) if isinstance(item, dict)]
    if not roles:
        return requests
    selected = set(roles)
    return [item for item in requests if item.get("role") in selected]


def output_size(request: dict[str, Any], override: str | None) -> str:
    if override:
        image_provider.parse_size(override)
        return override
    contract = request.get("output_contract")
    contract = contract if isinstance(contract, dict) else {}
    size = f"{int(contract.get('width') or 1024)}x{int(contract.get('height') or 1024)}"
    image_provider.parse_size(size)
    return size


def run_request(
    request_pack_path: Path,
    pack: dict[str, Any],
    request: dict[str, Any],
    output_dir: Path,
    profile: image_provider.ImageProfile,
    *,
    size_override: str | None,
    timeout: int,
    live: bool,
) -> dict[str, Any]:
    role = safe_id(request.get("role"))
    node_id = safe_id(pack.get("node_id"))
    request_id = safe_id(request.get("request_id"))
    size = output_size(request, size_override)
    prompt = str(request.get("prompt_brief") or "").strip()
    if not prompt:
        raise ValueError(f"request has no prompt_brief: {request_id}")
    output_path = output_dir / f"{node_id}.{role}.{profile.name}.candidate.png"
    provider_called = False
    if live:
        response = image_provider.generate_image(profile, prompt, size=size, timeout=timeout)
        image_url = image_provider.extract_image_url(response)
        image_provider.download_image(image_url, output_path, timeout=timeout)
        provider_called = True

    sidecar = {
        "schema_version": "layered_map_visual_candidate.v0.1",
        "candidate_id": f"{node_id}.{role}.{profile.name}",
        "request_id": request_id,
        "request_pack_path": rel(request_pack_path),
        "node_id": pack.get("node_id"),
        "worldbook_id": pack.get("worldbook_id"),
        "role": request.get("role"),
        "candidate_path": rel(output_path),
        "provider_profile": profile.name if live else None,
        "model": profile.model if live else None,
        "size": size,
        "prompt_sha256": sha256_text(prompt),
        "provider_called_this_run": provider_called,
        "image_exists": output_path.is_file(),
        "image_sha256": sha256_file(output_path) if output_path.is_file() else None,
        "image_size_bytes": output_path.stat().st_size if output_path.is_file() else 0,
        "review_status": (
            "candidate_needs_visual_and_alignment_review"
            if output_path.is_file()
            else "awaiting_provider_output"
        ),
        "promotion_allowed_now": False,
        "runtime_semantic_authority": False,
        "required_gates": request.get("required_gates", []),
        "safety": {
            "stores_api_key": False,
            "stores_raw_provider_body": False,
            "stores_raw_prompt": False,
            "player_runtime_modified": False,
        },
    }
    sidecar_path = output_path.with_suffix(output_path.suffix + ".candidate.json")
    write_json(sidecar_path, sidecar)
    return {
        "request_id": request_id,
        "role": request.get("role"),
        "status": sidecar["review_status"],
        "candidate_path": sidecar["candidate_path"],
        "sidecar_path": rel(sidecar_path),
        "provider_called_this_run": provider_called,
        "image_exists": sidecar["image_exists"],
    }


def build_report(
    *,
    request_pack_path: Path,
    output_dir: Path,
    profile: image_provider.ImageProfile,
    live: bool,
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(str(item.get("status")) for item in results)
    return {
        "schema_version": REPORT_VERSION,
        "run_id": f"layered_map_visual_{sha256_text(str(request_pack_path.resolve()))[:16]}",
        "status": "completed_with_failures" if failures else "completed_review_only",
        "request_pack_path": rel(request_pack_path),
        "output_dir": rel(output_dir),
        "live": live,
        "provider_profile": profile.name if live else None,
        "model": profile.model if live else None,
        "summary": {
            "request_count": len(results) + len(failures),
            "result_count": len(results),
            "failure_count": len(failures),
            "provider_call_count": sum(
                1 for item in results if item.get("provider_called_this_run")
            ),
            "image_exists_count": sum(1 for item in results if item.get("image_exists")),
            "status_counts": dict(sorted(statuses.items())),
        },
        "results": results,
        "failures": failures,
        "policy": [
            "All outputs are review-only candidates.",
            "No candidate changes MapRuntimePackage or player runtime.",
            "Promotion requires local import, visual review, alignment review, and explicit approval.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-pack", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--role", action="append", default=[])
    parser.add_argument(
        "--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES)
    )
    parser.add_argument("--size")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    pack = load_json(args.request_pack)
    if pack.get("schema_version") != PACK_VERSION:
        raise SystemExit(f"request pack must be {PACK_VERSION}")
    profile = image_provider.PROFILES[args.image_profile]
    if args.live:
        image_provider.load_dotenv(args.dotenv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for request in selected_requests(pack, args.role):
        try:
            results.append(
                run_request(
                    args.request_pack,
                    pack,
                    request,
                    args.output_dir,
                    profile,
                    size_override=args.size,
                    timeout=args.request_timeout,
                    live=args.live,
                )
            )
        except Exception as exc:  # pragma: no cover - live provider failure path.
            failures.append(
                {
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                    "error": str(exc)[:500],
                }
            )
            if not args.continue_on_error:
                break
    report = build_report(
        request_pack_path=args.request_pack,
        output_dir=args.output_dir,
        profile=profile,
        live=args.live,
        results=results,
        failures=failures,
    )
    write_json(args.output, report)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if results and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
