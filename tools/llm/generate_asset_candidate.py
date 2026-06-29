#!/usr/bin/env python3
"""Generate a CompiledAssetCandidate v0.1 via an LLM provider.

Dry-run by default: refuses to call any provider without --live.
When --live is given, calls the configured provider, extracts JSON,
validates the result against validate_asset_candidate, and writes
the validated candidate to --output.

Usage:
    python3 tools/llm/generate_asset_candidate.py \\
        --proposal examples/proposals/light_slow_field.proposal.json \\
        --effect-registry shared/module_registry/effect_blocks.v0.1.json \\
        --output /tmp/asset_candidate.json \\
        --provider-profile ark_deepseek_v4_flash \\
        --live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import adapter  # noqa: E402
import asset_candidate_prompt  # noqa: E402

CONTENT_PIPELINE_DIR = ROOT / "tools" / "content_pipeline"
if str(CONTENT_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(CONTENT_PIPELINE_DIR))

import validate_asset_candidate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a CompiledAssetCandidate v0.1 via an LLM provider."
    )
    parser.add_argument("--proposal", required=True, help="Path to Proposal JSON.")
    parser.add_argument("--effect-registry", help="Path to effect_blocks registry JSON (defaults to shared/module_registry/effect_blocks.v0.1.json).")
    parser.add_argument("--output", required=True, help="Path to write the validated CompiledAssetCandidate JSON.")
    parser.add_argument(
        "--provider-profile",
        default="ark_deepseek_v4_flash",
        choices=list(adapter.PROFILES),
        help="Provider profile to use (default: ark_deepseek_v4_flash).",
    )
    parser.add_argument("--max-tokens", type=int, default=8192, help="Max tokens for the response.")
    parser.add_argument("--request-timeout", type=int, default=120, help="Request timeout in seconds.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call the remote provider. Without this flag, the script refuses.",
    )
    args = parser.parse_args()

    # Load .env if present
    adapter.load_dotenv(ROOT / ".env")

    # Dry-run guard
    if not args.live:
        print(
            "Refusing to call a remote provider without --live. "
            "Pass --live to enable the real API call.",
            file=sys.stderr,
        )
        return 2

    # Load inputs
    def load_json(path_str: str) -> dict:
        p = Path(path_str)
        if not p.exists():
            print(f"Input file not found: {p}", file=sys.stderr)
            sys.exit(1)
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)

    proposal = load_json(args.proposal)
    registry_path = Path(args.effect_registry) if args.effect_registry else ROOT / "shared/module_registry/effect_blocks.v0.1.json"
    effect_registry = load_json(str(registry_path))

    profile = adapter.PROFILES[args.provider_profile]

    # Build messages
    messages = [
        {"role": "system", "content": asset_candidate_prompt.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": asset_candidate_prompt.build_user_prompt(proposal, effect_registry),
        },
    ]

    print(f"Calling provider profile={profile.name!r} model={profile.model!r} ...", file=sys.stderr)
    response_format = (
        {"type": "json_object"} if profile.supports_json_object else None
    )

    try:
        response = adapter.chat_completion(
            profile,
            messages,
            max_tokens=args.max_tokens,
            timeout=args.request_timeout,
            response_format=response_format,
        )
    except Exception as exc:
        print(f"Provider call failed: {exc}", file=sys.stderr)
        return 1

    raw_text = adapter.extract_content_from_response(response)
    candidate = adapter.extract_json(raw_text)

    if candidate is None:
        print("Failed to extract JSON from provider response.", file=sys.stderr)
        print(f"Provider response text length: {len(raw_text)} characters.", file=sys.stderr)
        return 1

    candidate = asset_candidate_prompt.normalize_candidate_provenance(
        candidate,
        proposal,
        provider=profile.name,
        model=profile.model,
    )

    # Validate
    errors = validate_asset_candidate.validate(candidate, effect_registry)
    if errors:
        print("INVALID CompiledAssetCandidate — validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        failed_path = Path("/tmp") / f"failed_asset_candidate_{profile.name}.json"
        failed_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Failed artifact written to {failed_path} for inspection.", file=sys.stderr)
        return 1

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: validated CompiledAssetCandidate written to {output_path}")
    print(f"  - id: {candidate.get('id')}")
    print(f"  - lifecycle: {candidate.get('lifecycle')}")
    print(f"  - asset_type: {candidate.get('gameplay', {}).get('asset_type')}")
    print(f"  - effects: {len(candidate.get('gameplay', {}).get('effect_blocks', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
