#!/usr/bin/env python3
"""Validate the battle interaction contract without launching a browser.

This static contract protects the player-facing tower-defense interaction from
regressing into a debug panel. Dragging a tool card onto the battlefield is the
primary deployment gesture; click-to-place can remain as a fallback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
STYLES_CSS = ROOT / "frontend/styles.css"
REPORT_SCHEMA_VERSION = "battle_interaction_contract_report.v0.1"
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def js_section(source: str, start_name: str, end_name: str | None = None) -> str:
    start = source.find(f"function {start_name}")
    if start < 0:
        return ""
    if end_name:
        end = source.find(f"\n  function {end_name}", start + 1)
        if end > start:
            return source[start:end]
    next_match = re.search(r"\n  function\s+\w+", source[start + 1 :])
    if next_match:
        return source[start : start + 1 + next_match.start()]
    return source[start:]


def css_block(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}", css, re.S)
    return match.group("body") if match else ""


def css_blocks(css: str, selector: str) -> list[str]:
    return [
        match.group("body")
        for match in re.finditer(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}", css, re.S)
    ]


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value)


def contains_all(value: str, tokens: list[str]) -> bool:
    return all(token in value for token in tokens)


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "passed" if passed else "failed",
            "detail": detail,
        }
    )


def validate_contract(app: str, css: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    setup = js_section(app, "setupBattle", "stopBattleLoop")
    state_factory = js_section(app, "createBattleState")
    begin_drag = js_section(app, "beginToolDrag", "updateToolDrag")
    update_drag = js_section(app, "updateToolDrag", "finishToolDrag")
    finish_drag = js_section(app, "finishToolDrag", "deployToolAt")
    toolbar_markup = js_section(app, "battleToolsMarkup", "drawBattle")
    draw_battle = js_section(app, "drawBattle", "runtimeMapSeed")
    deploy_hints = js_section(app, "drawDeployHints", "drawDeploymentBase")
    drag_ghost = js_section(app, "drawDragGhost", "drawGroundGlow")
    root_listener_match = re.search(
        r'ROOT\.addEventListener\("pointerdown",\s*\(event\)\s*=>\s*\{(?P<body>.*?)\n  \}\);',
        app,
        re.S,
    )
    root_pointerdown = root_listener_match.group("body") if root_listener_match else ""
    toolbar_css = "\n".join(css_blocks(css, ".toolbar-card"))
    toolbar_drag_css = css_block(css, ".toolbar-card.is-dragging")
    stage_css = css_block(css, ".battle-stage")
    canvas_css = css_block(css, "#battleCanvas")

    add_check(
        checks,
        "battle_state_tracks_drag",
        contains_all(state_factory, ["selectedTool: \"basic\"", "draggingTool: null", "dragPointer: null", "hoverCell: null"]),
        "battle state must keep selected, dragging, pointer, and hover-cell fields.",
    )
    add_check(
        checks,
        "canvas_pointer_preview_registered",
        contains_all(
            setup,
            [
                'canvas.addEventListener("pointermove", onBattleCanvasPointerMove)',
                'canvas.addEventListener("pointerleave", onBattleCanvasPointerLeave)',
            ],
        ),
        "battle canvas must update deployment preview while the pointer moves.",
    )
    add_check(
        checks,
        "toolbar_pointerdown_starts_drag",
        contains_all(
            root_pointerdown,
            [
                '.toolbar-card[data-tool]',
                'state.view !== "battle"',
                "event.button !== 0",
                "beginToolDrag(target.dataset.tool, event)",
            ],
        ),
        "tool cards must start a drag gesture from pointerdown in the battle view.",
    )
    add_check(
        checks,
        "window_drag_lifecycle_registered",
        contains_all(app, ['window.addEventListener("pointermove", updateToolDrag)', 'window.addEventListener("pointerup", finishToolDrag)']),
        "drag move/up listeners must live on window so release outside the card still completes cleanly.",
    )
    add_check(
        checks,
        "begin_drag_sets_tool_and_prevents_default",
        contains_all(
            begin_drag,
            [
                "battle.selectedTool = tool || \"basic\"",
                "battle.draggingTool = battle.selectedTool",
                "battle.dragPointer = { x: event.clientX, y: event.clientY }",
                "battle.hoverCell = cellFromCanvasEvent(event)",
                "toolUnavailableText(battle.draggingTool)",
                "event.preventDefault()",
            ],
        ),
        "beginToolDrag must select the tool, initialize drag state, show unavailable feedback, and suppress native drag behavior.",
    )
    add_check(
        checks,
        "update_drag_tracks_pointer_without_deploying",
        contains_all(update_drag, ["battle.dragPointer = { x: event.clientX, y: event.clientY }", "battle.hoverCell = cellFromCanvasEvent(event)", "event.preventDefault()"])
        and "deployToolAt(" not in update_drag,
        "updateToolDrag must only update preview state and never deploy while the pointer is moving.",
    )
    add_check(
        checks,
        "finish_drag_deploys_once_and_clears_state",
        contains_all(
            finish_drag,
            [
                "const tool = battle.draggingTool",
                "const cell = cellFromCanvasEvent(event)",
                "battle.draggingTool = null",
                "battle.dragPointer = null",
                "battle.hoverCell = null",
                "event.preventDefault()",
                "setBattleToast(\"拖到战场格位后释放\")",
                "deployToolAt(tool, cell)",
            ],
        ),
        "finishToolDrag must clear drag state and deploy exactly on pointer release over a valid battle cell.",
    )
    add_check(
        checks,
        "toolbar_cards_are_non_native_drag_sources",
        contains_all(toolbar_markup, ['class="toolbar-card', 'data-action="select-tool"', 'data-tool="${tool.id}"', 'draggable="false"', "is-dragging"]),
        "tool cards must expose game drag state instead of browser-native draggable behavior.",
    )
    add_check(
        checks,
        "battle_draws_preview_and_drag_ghost",
        contains_all(draw_battle, ["drawDeployHints(ctx)", "drawDragGhost(ctx)"]),
        "the battle draw loop must render both grid deployment hints and the dragged tool ghost.",
    )
    add_check(
        checks,
        "deploy_preview_uses_hover_and_validity",
        contains_all(deploy_hints, ["battle.draggingTool || battle.selectedTool", "canPreviewToolAt(tool, previewCell)", "rgba(255,211,122,.17)", "rgba(255,95,83,.16)"]),
        "deployment preview must reflect the current tool and show valid/invalid placement feedback.",
    )
    add_check(
        checks,
        "drag_ghost_uses_pointer_and_tool_media",
        contains_all(drag_ghost, ["battle.draggingTool", "battle.dragPointer", "battle.canvas", "getBoundingClientRect()", "drawSprite(ctx", "drawGroundGlow(ctx"]),
        "drag ghost must follow the pointer and use the tool's in-world visual language.",
    )
    add_check(
        checks,
        "css_toolbar_supports_touch_drag",
        "cursor: grab" in toolbar_css and "touch-action: none" in toolbar_css and "user-select: none" in toolbar_css,
        "toolbar cards must be styled for pointer/touch dragging without text selection or page panning.",
    )
    add_check(
        checks,
        "css_dragging_state_is_visible",
        "cursor: grabbing" in toolbar_drag_css and "transform:" in toolbar_drag_css and "border-color:" in toolbar_drag_css,
        "active dragging state must have visible feedback on the tool card.",
    )
    add_check(
        checks,
        "css_battle_stage_consumes_touch",
        "touch-action: none" in stage_css and "width: 100%" in canvas_css and "height: 100%" in canvas_css,
        "battle stage must consume touch gestures and the canvas must fill the stage.",
    )
    add_check(
        checks,
        "click_to_place_is_only_fallback",
        'canvas.addEventListener("click", onBattleCanvasClick)' in setup and "deployToolAt(battle.selectedTool, cell)" in js_section(app, "onBattleCanvasClick", "onBattleCanvasPointerMove"),
        "click placement may remain as a fallback while drag-to-place is protected as the primary contract.",
    )
    add_check(
        checks,
        "no_technical_terms_in_player_drag_feedback",
        not re.search(r"\b(provider|schema|prompt|json|trace|api|model)\b", compact(begin_drag + update_drag + finish_drag), re.I),
        "player-facing drag feedback must not expose provider/schema/prompt/debug wording.",
    )
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-output", type=Path, help="Write a structured validation report.")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = APP_JS.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")
    checks = validate_contract(app, css)
    failed = [check for check in checks if check["status"] != "passed"]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": "battle_interaction_contract_report_v0_1",
        "generated_at": args.generated_at or now_iso(),
        "status": "passed" if not failed else "failed",
        "summary": {
            "check_count": len(checks),
            "passed_count": len(checks) - len(failed),
            "failed_count": len(failed),
            "primary_interaction": "drag_tool_card_to_battle_cell",
            "click_to_place_fallback_allowed": True,
            "provider_call_count": 0,
            "reads_env_file": False,
            "browser_required": False,
        },
        "checks": checks,
    }
    if args.report_output:
        write_json(args.report_output, report)
    if failed:
        for check in failed:
            print(f"FAIL {check['id']}: {check['detail']}", file=sys.stderr)
        return 1
    print(f"battle interaction contract passed: {len(checks)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
