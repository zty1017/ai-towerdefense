#!/usr/bin/env python3
"""Generate or prepare review-only controlled map candidates.

This runner consumes MapControlledRegenerationRequestPack. Reference-image mode
is a handoff mode because the current image_provider adapter only supports
OpenAI-compatible text-to-image endpoints. Text-fallback mode can call the
existing provider when --live is passed, but those candidates still remain
review-only and must re-enter alignment / overlay / visual gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402


REPORT_VERSION = "controlled_map_candidate_generation_run.v0.1"
DEFAULT_REQUEST_PACK = ROOT / "examples/review_packs/map_controlled_regeneration_request_pack.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates_controlled_v1"
DEFAULT_REPORT = ROOT / "examples/review_packs/controlled_map_candidate_generation_run.v0.1.json"
FENCE_RE = re.compile(r"```text\n(?P<body>.*?)\n```", re.DOTALL)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def public_url(base_url: str | None, repo_path: str | None) -> str | None:
    if not base_url or not repo_path:
        return None
    return base_url.rstrip("/") + "/" + repo_path.lstrip("/")


def extract_prompt(markdown_path: Path, provider_mode: str) -> str:
    text = markdown_path.read_text(encoding="utf-8")
    blocks = [match.group("body").strip() for match in FENCE_RE.finditer(text)]
    if provider_mode == "reference-image":
        if not blocks:
            raise RuntimeError(f"no provider instruction fenced block in {markdown_path}")
        return blocks[0]
    if len(blocks) < 2:
        raise RuntimeError(f"no text-only fallback fenced block in {markdown_path}")
    return blocks[1]


def output_path_for(request: dict[str, Any], output_dir: Path, provider_mode: str) -> Path:
    node_id = str(request.get("node_id") or "unknown_node")
    suffix = "controlled_reference_candidate" if provider_mode == "reference-image" else "controlled_text_fallback_candidate"
    return output_dir / f"{node_id}.{suffix}.png"


def write_sidecar(
    *,
    output_path: Path,
    request_pack_path: Path,
    request: dict[str, Any],
    prompt: str,
    provider_mode: str,
    profile: image_provider.ImageProfile,
    size: str,
    live: bool,
    provider_called: bool,
    reference_image_url_base: str | None,
) -> dict[str, Any]:
    image_exists = output_path.exists()
    control = as_obj(request.get("control_sketch"))
    control_png_path = str(control.get("png_path") or "")
    sidecar = {
        "schema_version": "controlled_map_candidate.v0.1",
        "candidate_id": f"{request.get('node_id')}.{provider_mode.replace('-', '_')}.controlled_map_candidate",
        "candidate_path": rel(output_path),
        "sidecar_kind": "controlled_map_candidate",
        "request_pack_path": rel(request_pack_path),
        "request_id": request.get("request_id"),
        "node_id": request.get("node_id"),
        "runtime_package_path": request.get("runtime_package_path"),
        "source_prompt_pack": request.get("source_prompt_pack"),
        "source_control_sketch_pack": request.get("source_control_sketch_pack"),
        "control_sketch_png_path": control_png_path,
        "control_sketch_png_sha256": control.get("png_sha256"),
        "control_sketch_public_url": public_url(reference_image_url_base, control_png_path),
        "provider_mode": provider_mode,
        "provider_profile": profile.name if live or image_exists else None,
        "model": profile.model if live or image_exists else None,
        "size": size,
        "prompt_sha256": sha256_text(prompt),
        "image_exists": image_exists,
        "image_size_bytes": output_path.stat().st_size if image_exists else 0,
        "image_sha256": sha256_file(output_path),
        "provider_called_this_run": provider_called,
        "generation_status": (
            "live_generated_text_fallback"
            if provider_called and provider_mode == "text-fallback"
            else (
                "reference_image_handoff_ready"
                if provider_mode == "reference-image"
                else ("dry_run_text_fallback_sidecar" if not image_exists else "existing_image_sidecar_refreshed")
            )
        ),
        "review_status": (
            "candidate_needs_candidate_review_first"
            if image_exists
            else "awaiting_provider_or_paintover_output"
        ),
        "promotion_allowed_now": False,
        "promotion_policy": "must pass candidate, alignment, overlay, visual, and explicit promotion gates before runtime use",
        "required_review_gates": as_list(request.get("required_review_gates")),
        "target_candidate": as_obj(request.get("target_candidate")),
        "provider_reference_contract": as_obj(request.get("provider_reference_contract")),
        "safe_to_send": "topology_prompt_and_control_image_only_no_secret_no_raw_trace",
    }
    write_json(output_path.with_suffix(output_path.suffix + ".candidate.json"), sidecar)
    return sidecar


def selected_requests(pack: dict[str, Any], node_ids: list[str]) -> list[dict[str, Any]]:
    requests = [request for request in as_list(pack.get("requests")) if isinstance(request, dict)]
    if not node_ids:
        return requests
    selected = set(node_ids)
    return [request for request in requests if request.get("node_id") in selected]


def run_request(
    request_pack_path: Path,
    request: dict[str, Any],
    output_dir: Path,
    profile: image_provider.ImageProfile,
    size: str,
    timeout: int,
    provider_mode: str,
    *,
    live: bool,
    reference_image_url_base: str | None,
) -> dict[str, Any]:
    markdown_path = resolve_repo_path(request.get("manual_prompt_markdown_path"))
    if markdown_path is None or not markdown_path.exists():
        raise RuntimeError(f"manual prompt markdown missing for {request.get('request_id')}")
    prompt = extract_prompt(markdown_path, provider_mode)
    output_path = output_path_for(request, output_dir, provider_mode)
    provider_called = False

    if live and provider_mode == "reference-image":
        raise RuntimeError(
            "live reference-image generation is not supported by the current image_provider adapter; "
            "use handoff mode, provide a provider-specific adapter, or run --provider-mode text-fallback"
        )

    if live and provider_mode == "text-fallback":
        response = image_provider.generate_image(profile, prompt, size=size, timeout=timeout)
        image_url = image_provider.extract_image_url(response)
        image_provider.download_image(image_url, output_path, timeout=timeout)
        provider_called = True

    sidecar = write_sidecar(
        output_path=output_path,
        request_pack_path=request_pack_path,
        request=request,
        prompt=prompt,
        provider_mode=provider_mode,
        profile=profile,
        size=size,
        live=live,
        provider_called=provider_called,
        reference_image_url_base=reference_image_url_base,
    )
    return {
        "node_id": request.get("node_id"),
        "request_id": request.get("request_id"),
        "status": sidecar["generation_status"],
        "candidate_path": sidecar["candidate_path"],
        "sidecar_path": rel(output_path.with_suffix(output_path.suffix + ".candidate.json")),
        "image_exists": sidecar["image_exists"],
        "provider_called_this_run": provider_called,
        "provider_mode": provider_mode,
        "review_status": sidecar["review_status"],
        "control_sketch_png_path": sidecar["control_sketch_png_path"],
        "control_sketch_public_url": sidecar["control_sketch_public_url"],
    }


def build_report(
    *,
    request_pack_path: Path,
    output_dir: Path,
    profile: image_provider.ImageProfile,
    size: str,
    provider_mode: str,
    live: bool,
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(str(result.get("status")) for result in results)
    return {
        "schema_version": REPORT_VERSION,
        "report_id": f"mvp_controlled_map_candidate_generation_{provider_mode.replace('-', '_')}",
        "request_pack_path": rel(request_pack_path),
        "output_dir": rel(output_dir),
        "status": "completed_with_failures" if failures else "completed_review_only",
        "provider_mode": provider_mode,
        "live": live,
        "provider_profile": profile.name if live else None,
        "model": profile.model if live else None,
        "summary": {
            "request_count": len(results) + len(failures),
            "result_count": len(results),
            "failure_count": len(failures),
            "image_exists_count": sum(1 for result in results if result.get("image_exists")),
            "provider_call_count": sum(1 for result in results if result.get("provider_called_this_run")),
            "handoff_ready_count": status_counts.get("reference_image_handoff_ready", 0),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "results": results,
        "failures": failures,
        "policy": [
            "Controlled map candidates are review-only.",
            "Reference-image mode prepares sidecars and public URL hints, but does not call the current text-only image adapter.",
            "Text-fallback live generation is allowed only with --live and still cannot update runtime or published visual layers.",
            "All generated images must pass candidate, alignment, overlay, visual, and promotion gates.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or prepare controlled map candidates from request pack.")
    parser.add_argument("--request-pack", default=str(DEFAULT_REQUEST_PACK))
    parser.add_argument("--node-id", action="append", default=[], help="Restrict to node id. May be repeated.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--provider-mode", choices=["reference-image", "text-fallback"], default="reference-image")
    parser.add_argument("--reference-image-url-base", default=None)
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    request_pack_path = Path(args.request_pack)
    if not request_pack_path.is_absolute():
        request_pack_path = ROOT / request_pack_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output_dir.mkdir(parents=True, exist_ok=True)

    image_provider.parse_size(args.size)
    profile = image_provider.PROFILES[args.image_profile]
    if args.live:
        dotenv_path = Path(args.dotenv)
        if not dotenv_path.is_absolute():
            dotenv_path = ROOT / dotenv_path
        image_provider.load_dotenv(dotenv_path)

    pack = load_json(request_pack_path)
    requests = selected_requests(as_obj(pack), args.node_id)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for request in requests:
        try:
            results.append(
                run_request(
                    request_pack_path,
                    request,
                    output_dir,
                    profile,
                    args.size,
                    args.request_timeout,
                    args.provider_mode,
                    live=args.live,
                    reference_image_url_base=args.reference_image_url_base,
                )
            )
        except Exception as exc:  # pragma: no cover - live provider failure path
            failure = {
                "request_id": request.get("request_id"),
                "node_id": request.get("node_id"),
                "error": str(exc)[:500],
            }
            failures.append(failure)
            print(f"FAILED {failure['request_id']}: {failure['error']}", file=sys.stderr)
            if not args.continue_on_error:
                break

    report = build_report(
        request_pack_path=request_pack_path,
        output_dir=output_dir,
        profile=profile,
        size=args.size,
        provider_mode=args.provider_mode,
        live=args.live,
        results=results,
        failures=failures,
    )
    write_json(output, report)
    print(f"Wrote {output}")
    print(f"- status: {report['status']}")
    print(f"- results: {report['summary']['result_count']}")
    print(f"- provider calls: {report['summary']['provider_call_count']}")
    return 0 if results and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
