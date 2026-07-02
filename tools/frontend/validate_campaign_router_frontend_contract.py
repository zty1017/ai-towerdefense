#!/usr/bin/env python3
"""Validate the no-build frontend consumes the Campaign Router contract.

This static check complements browser/manual testing. It confirms the frontend
uses the backend route cursor for API-mode node loading and keeps the static
first-battle fallback intact.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
README = ROOT / "frontend/README.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate() -> list[str]:
    app = read(APP_JS)
    readme = read(README)
    errors: list[str] = []

    required_app_fragments = [
        'sessionApiPath("/campaign-router")',
        'sessionApiPath("/campaign-router/prefetch-next")',
        "function currentNodeId()",
        "function requestNextPrefetch()",
        "function enterCurrentNode()",
        "static_fallback_route",
        "sessionApiPath(`/nodes/${nodeId}/briefing`)",
        "sessionApiPath(`/battles/${nodeId}/config`)",
        "sessionApiPath(`/battles/${currentNodeId()}/results`)",
    ]
    for fragment in required_app_fragments:
        if fragment not in app:
            errors.append(f"frontend/app.js missing router contract fragment: {fragment}")

    forbidden_app_fragments = [
        "sessionApiPath(`/nodes/${NODE_ID}/briefing`)",
        "sessionApiPath(`/battles/${NODE_ID}/config`)",
        "sessionApiPath(`/battles/${NODE_ID}/results`)",
        "selected.stable_internal_id === NODE_ID ?",
    ]
    for fragment in forbidden_app_fragments:
        if fragment in app:
            errors.append(f"frontend/app.js still hardcodes API node route: {fragment}")

    required_readme_fragments = [
        "/api/sessions/{session_id}/campaign-router",
        "/api/sessions/{session_id}/campaign-router/prefetch-next",
        "静态模式仍固定使用灰灯驿站首战作为可玩兜底",
    ]
    for fragment in required_readme_fragments:
        if fragment not in readme:
            errors.append(f"frontend/README.md missing router note: {fragment}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("INVALID campaign router frontend contract")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK campaign router frontend contract")
    print("- API mode consumes campaign-router current/next node")
    print("- prefetch-next is wired as fire-and-forget")
    print("- static first-battle fallback remains documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
