#!/usr/bin/env python3
"""Generate review-only candidates from a layered map visual request pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402
import png_pipeline  # noqa: E402


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


def output_spec(
    request: dict[str, Any],
    override: str | None,
    profile: image_provider.ImageProfile,
) -> tuple[str, str | None]:
    contract = request.get("output_contract")
    contract = contract if isinstance(contract, dict) else {}
    ratio = str(contract.get("ratio") or "").strip() or None
    if override:
        size = image_provider.validate_size(override)
        return size, ratio if size.endswith("K") else None
    if profile.name.startswith("agnes_") and contract.get("size_tier"):
        size = image_provider.validate_size(str(contract["size_tier"]))
        return size, image_provider.validate_ratio(ratio or "1:1")
    size = f"{int(contract.get('width') or 1024)}x{int(contract.get('height') or 1024)}"
    image_provider.parse_size(size)
    return size, None


def resolve_reference_path(value: str, request_pack_path: Path) -> Path:
    path = Path(value)
    candidates = [path] if path.is_absolute() else [ROOT / path, request_pack_path.parent / path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"generation reference does not exist: {value}")


def generation_inputs(request: dict[str, Any], request_pack_path: Path) -> tuple[str, list[str]]:
    mode = str(request.get("generation_mode") or "text_to_image")
    if mode == "text_to_image":
        return mode, []
    if mode != "image_to_image":
        raise ValueError(f"unsupported generation_mode: {mode}")
    generation_reference = request.get("generation_reference")
    if not isinstance(generation_reference, dict):
        raise ValueError("image_to_image request has no generation_reference")
    references = [
        item
        for item in (request.get("style_reference"), generation_reference)
        if isinstance(item, dict)
    ]
    input_images = []
    for reference in references:
        reference_path = resolve_reference_path(
            str(reference.get("local_path") or ""), request_pack_path
        )
        expected_sha = str(reference.get("sha256") or "")
        if not expected_sha or sha256_file(reference_path) != expected_sha:
            raise ValueError("generation reference sha256 mismatch")
        input_images.append(image_provider.image_data_uri(reference_path))
    return mode, input_images


def normalize_full_frame_geometry(path: Path, request: dict[str, Any]) -> dict[str, int] | None:
    contract = request.get("output_contract")
    contract = contract if isinstance(contract, dict) else {}
    if contract.get("kind") != "full_frame_backdrop":
        return None
    ratio_text = str(contract.get("ratio") or "")
    if ":" not in ratio_text:
        return None
    left, right = ratio_text.split(":", 1)
    ratio = int(left) / int(right)
    image = png_pipeline.read_png(path)
    cropped = png_pipeline.center_crop_to_ratio(image, ratio)
    if (cropped.width, cropped.height) != (image.width, image.height):
        png_pipeline.write_png(path, cropped)
    return {"width": cropped.width, "height": cropped.height}


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
    credential_index: int = 0,
) -> dict[str, Any]:
    role = safe_id(request.get("role"))
    node_id = safe_id(pack.get("node_id"))
    request_id = safe_id(request.get("request_id"))
    size, ratio = output_spec(request, size_override, profile)
    prompt = str(request.get("prompt_brief") or "").strip()
    if not prompt:
        raise ValueError(f"request has no prompt_brief: {request_id}")
    output_path = output_dir / f"{node_id}.{role}.{profile.name}.candidate.png"
    generation_mode, input_images = generation_inputs(request, request_pack_path)
    if input_images and not profile.name.startswith("agnes_"):
        raise ValueError(f"profile {profile.name!r} does not support this image-to-image contract")
    provider_called = False
    if live:
        response = image_provider.generate_image(
            profile,
            prompt,
            size=size,
            ratio=ratio,
            input_images=input_images,
            response_format="url" if profile.name.startswith("agnes_") else None,
            credential_index=credential_index,
            timeout=timeout,
        )
        image_url = image_provider.extract_image_url(response)
        image_provider.download_image(image_url, output_path, timeout=timeout)
        normalized_dimensions = normalize_full_frame_geometry(output_path, request)
        provider_called = True
    else:
        normalized_dimensions = None

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
        "ratio": ratio,
        "generation_mode": generation_mode,
        "input_image_count": len(input_images),
        "normalized_dimensions": normalized_dimensions,
        "generation_reference_sha256": (
            request.get("generation_reference", {}).get("sha256")
            if isinstance(request.get("generation_reference"), dict)
            else None
        ),
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


def run_pack(
    request_pack_path: Path,
    pack: dict[str, Any],
    output_dir: Path,
    profile: image_provider.ImageProfile,
    *,
    roles: list[str] | None = None,
    size_override: str | None = None,
    timeout: int = 180,
    live: bool = False,
    max_workers: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requests = selected_requests(pack, roles or [])
    results_by_index: dict[int, dict[str, Any]] = {}
    failures_by_index: dict[int, dict[str, Any]] = {}

    def execute(index: int, request: dict[str, Any]) -> dict[str, Any]:
        return run_request(
            request_pack_path,
            pack,
            request,
            output_dir,
            profile,
            size_override=size_override,
            timeout=timeout,
            live=live,
            credential_index=index,
        )

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(requests) or 1))) as executor:
        future_map = {
            executor.submit(execute, index, request): (index, request)
            for index, request in enumerate(requests)
        }
        for future in as_completed(future_map):
            index, request = future_map[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:  # pragma: no cover - live provider failure path.
                failures_by_index[index] = {
                    "request_id": request.get("request_id"),
                    "role": request.get("role"),
                    "error": str(exc)[:500],
                }
    return (
        [results_by_index[index] for index in sorted(results_by_index)],
        [failures_by_index[index] for index in sorted(failures_by_index)],
    )


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
    parser.add_argument("--max-workers", type=int, default=3)
    args = parser.parse_args()

    pack = load_json(args.request_pack)
    if pack.get("schema_version") != PACK_VERSION:
        raise SystemExit(f"request pack must be {PACK_VERSION}")
    profile = image_provider.PROFILES[args.image_profile]
    if args.live:
        image_provider.load_dotenv(args.dotenv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results, failures = run_pack(
        args.request_pack,
        pack,
        args.output_dir,
        profile,
        roles=args.role,
        size_override=args.size,
        timeout=args.request_timeout,
        live=args.live,
        max_workers=args.max_workers,
    )
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
