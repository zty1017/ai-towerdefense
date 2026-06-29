#!/usr/bin/env python3
"""Generate a WorldStateDelta v0.1 via an LLM provider.

Dry-run by default: refuses to call any provider without --live.
When --live is given, calls the configured provider, extracts JSON,
validates the result against jsonschema + world delta rules, and writes
the validated delta to --output.

Usage:
    python3 tools/llm/generate_world_delta.py \\
        --run-world-state examples/run_world_states/demo_initial.run_world_state.json \\
        --battle-result examples/asset_graph/battle_result.sample.json \\
        --session-context examples/asset_graph/session_context.sample.json \\
        --output /tmp/delta.json \\
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
import world_delta_prompt  # noqa: E402

WORLD_STATE_DIR = ROOT / "tools" / "world_state"
if str(WORLD_STATE_DIR) not in sys.path:
    sys.path.insert(0, str(WORLD_STATE_DIR))

import validate_world_delta as v_wd  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a WorldStateDelta v0.1 via an LLM provider."
    )
    parser.add_argument("--run-world-state", required=True, help="Path to RunWorldState JSON.")
    parser.add_argument("--battle-result", required=True, help="Path to battle_result JSON.")
    parser.add_argument("--session-context", required=True, help="Path to session_context JSON.")
    parser.add_argument("--output", required=True, help="Path to write the validated WorldStateDelta JSON.")
    parser.add_argument(
        "--provider-profile",
        default="ark_deepseek_v4_flash",
        choices=list(adapter.PROFILES),
        help="Provider profile to use (default: ark_deepseek_v4_flash).",
    )
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max tokens for the response.")
    parser.add_argument("--request-timeout", type=int, default=90, help="Request timeout in seconds.")
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

    run_world_state = load_json(args.run_world_state)
    battle_result = load_json(args.battle_result)
    session_context = load_json(args.session_context)

    profile = adapter.PROFILES[args.provider_profile]

    # Build messages
    messages = [
        {"role": "system", "content": world_delta_prompt.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": world_delta_prompt.build_user_prompt(
                run_world_state, battle_result, session_context
            ),
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
    delta = adapter.extract_json(raw_text)

    if delta is None:
        print("Failed to extract JSON from provider response.", file=sys.stderr)
        print(f"Provider response text length: {len(raw_text)} characters.", file=sys.stderr)
        return 1

    # Validate
    errors: list[str] = []
    errors.extend(v_wd.validate_with_jsonschema(delta))
    errors.extend(v_wd.validate_world_delta(delta))
    seen: set[str] = set()
    deduped: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    if deduped:
        print("INVALID WorldStateDelta — validation errors:", file=sys.stderr)
        for e in deduped:
            print(f"  - {e}", file=sys.stderr)
        # Write failed artifact to /tmp for debugging
        failed_path = Path("/tmp") / f"failed_delta_{profile.name}.json"
        failed_path.write_text(json.dumps(delta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Failed artifact written to {failed_path} for inspection.", file=sys.stderr)
        return 1

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(delta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"OK: validated WorldStateDelta written to {output_path}")
    print(f"  - delta_id: {delta.get('delta_id')}")
    print(f"  - run_id: {delta.get('run_id')}")
    print(f"  - worldbook_id: {delta.get('worldbook_id')}")
    print(f"  - operations: {len(delta.get('operations', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
