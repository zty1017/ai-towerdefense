#!/usr/bin/env python3
"""Validate the battle interaction contract without launching a browser.

This static contract protects the player-facing tower-defense interaction from
regressing into a debug panel. Dragging a tool card onto the battlefield is the
primary deployment gesture; click-to-place can remain as a fallback.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report_io import write_json


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
RUNTIME_JS_DIR = ROOT / "frontend/runtime"
RUNTIME_JS_FILES = sorted(RUNTIME_JS_DIR.glob("*.js"))
STYLES_CSS = ROOT / "frontend/styles.css"
REPORT_SCHEMA_VERSION = "battle_interaction_contract_report.v0.1"
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def frontend_js_files() -> list[Path]:
    return [APP_JS, *RUNTIME_JS_FILES]


def read_frontend_sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in frontend_js_files()}


def frontend_source_bundle(sources: dict[Path, str]) -> str:
    return "\n\n".join(
        f"/* frontend source: {rel(path)} */\n{source}" for path, source in sources.items()
    )


def runtime_module_sources(sources: dict[Path, str]) -> dict[str, str]:
    return {path.name: source for path, source in sources.items() if path.parent == RUNTIME_JS_DIR}


def frontend_source_bundle_report(sources: dict[Path, str]) -> dict[str, Any]:
    runtime_paths = [path for path in sources if path.parent == RUNTIME_JS_DIR]
    return {
        "entrypoint": rel(APP_JS),
        "source_file_count": len(sources),
        "source_files": [rel(path) for path in sources],
        "runtime_source_file_count": len(runtime_paths),
        "runtime_source_files": [rel(path) for path in runtime_paths],
    }


def js_section(source: str, start_name: str, end_name: str | None = None) -> str:
    start_match = re.search(
        rf"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+{re.escape(start_name)}\s*\(",
        source,
    )
    if not start_match:
        return ""
    start = start_match.start()
    if end_name:
        end_match = re.search(
            rf"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+{re.escape(end_name)}\s*\(",
            source[start + 1 :],
        )
        if end_match:
            return source[start : start + 1 + end_match.start()]
    search_start = start_match.end()
    next_match = re.search(r"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+\w+\s*\(", source[search_start:])
    if next_match:
        return source[start : search_start + next_match.start()]
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


def has_named_export(source: str, name: str) -> bool:
    escaped = re.escape(name)
    return bool(
        re.search(rf"(?m)^[ \t]*export\s+(?:async\s+)?function\s+{escaped}\s*\(", source)
        or re.search(rf"(?s)\bexport\s*\{{[^}}]*\b{escaped}\b[^}}]*\}}", source)
    )


def set_battle_toast_literals(source: str) -> str:
    return "\n".join(
        match.group("literal")
        for match in re.finditer(
            r"setBattleToast\(\s*(?P<literal>\"[^\"\\]*(?:\\.[^\"\\]*)*\"|'[^'\\]*(?:\\.[^'\\]*)*'|`[^`\\]*(?:\\.[^`\\]*)*`)",
            source,
            re.S,
        )
    )


def has_state_mutation(section: str) -> bool:
    assignment = re.search(
        r"\b(?:state|battle)\.[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\s*(?:=|\+=|-=|\*=|/=|%=|\+\+|--)",
        section,
    )
    mutating_call = re.search(r"\.(?:push|pop|splice|shift|unshift|sort|reverse)\s*\(", section)
    helper_mutation = re.search(r"\b(?:setBattleToast|deployToolAt|placeBasicDefense|placeSampleTrap|useSupportPulse|addEffect|addBeam|addFloating|finishBattle)\s*\(", section)
    return bool(assignment or mutating_call or helper_mutation)


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "passed" if passed else "failed",
            "detail": detail,
        }
    )


def validate_contract(frontend: str, css: str, runtime_sources: dict[str, str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    battle_dom_controller = runtime_sources.get("battle-dom-controller.js", "")
    setup = js_section(battle_dom_controller, "setupBattle")
    state_factory = "\n".join(
        [
            js_section(frontend, "createBattleState"),
            js_section(frontend, "createBattleStateFactory"),
        ]
    )
    begin_drag = js_section(frontend, "beginToolDrag", "updateToolDrag")
    update_drag = js_section(frontend, "updateToolDrag", "finishToolDrag")
    finish_drag = js_section(frontend, "finishToolDrag", "deployToolAt")
    cancel_drag = js_section(frontend, "cancelToolDrag")
    toolbar_markup = js_section(frontend, "battleToolsMarkup", "drawBattle")
    draw_battle = "\n".join(
        [
            js_section(frontend, "drawBattle", "runtimeMapSeed"),
            js_section(frontend, "drawBattleFrame"),
        ]
    )
    deployment_renderer = runtime_sources.get("battle-deployment-renderer.js", "")
    deploy_hints = js_section(deployment_renderer, "drawDeployHints")
    install_probe = js_section(frontend, "installBattleSmokeProbe", "battleSmokeDeploymentPoint")
    probe_point = js_section(frontend, "battleSmokeDeploymentPoint", "battleSmokeSnapshot")
    probe_snapshot = js_section(frontend, "battleSmokeSnapshot", "stopBattleLoop")
    unavailable_text = js_section(frontend, "toolUnavailableText", "canPreviewToolAt")
    placement_feedback = "\n".join(
        [
            js_section(frontend, "placeBasicDefense", "placeSampleTrap"),
            js_section(frontend, "placeSampleTrap", "useSupportPulse"),
            js_section(frontend, "useSupportPulse", "setBattleToast"),
            set_battle_toast_literals(frontend),
        ]
    )
    toolbar_css = "\n".join(css_blocks(css, ".toolbar-card"))
    toolbar_drag_css = css_block(css, ".toolbar-card.is-dragging")
    stage_css = css_block(css, ".battle-stage")
    canvas_css = css_block(css, "#battleCanvas")
    input_controller = runtime_sources.get("battle-input-controller.js", "")
    battle_rules = runtime_sources.get("battle-rules.js", "")
    entity_renderer = runtime_sources.get("battle-entity-renderer.js", "")
    projection_adapter = runtime_sources.get("runtime-projection-adapter.js", "")
    root_event_router = runtime_sources.get("root-event-router.js", "")
    drag_ghost = entity_renderer
    input_controller_exports = [
        "onBattleCanvasClick",
        "onBattleCanvasPointerMove",
        "onBattleCanvasPointerLeave",
        "beginToolDrag",
        "updateToolDrag",
        "finishToolDrag",
        "cancelToolDrag",
    ]
    battle_rule_exports = [
        "createBattleStateFactory",
        "canPlaceToolAt",
        "toolReady",
        "buildSpawnSchedule",
    ]
    projection_exports = [
        "buildBattleToolProjection",
        "assetKindForToolId",
    ]
    add_check(
        checks,
        "deployment_renderer_module_boundary",
        has_named_export(deployment_renderer, "createBattleDeploymentRenderer")
        and "document." not in deployment_renderer
        and "state." not in deployment_renderer
        and "deployToolAt(" not in deployment_renderer,
        "battle-deployment-renderer must expose a presentation-only factory without owning DOM or deployment rules.",
    )

    add_check(
        checks,
        "battle_dom_controller_module_boundary",
        has_named_export(battle_dom_controller, "createBattleDomController")
        and "advanceBattleStep" not in battle_dom_controller
        and "deployRuntimeTool(" not in battle_dom_controller
        and "finishBattle(" not in battle_dom_controller,
        "battle-dom-controller must own battle DOM lifecycle without owning simulation, runtime deployment, or settlement.",
    )
    add_check(
        checks,
        "frontend_source_bundle_includes_runtime_modules",
        "frontend/app.js" in frontend
        and bool(runtime_sources)
        and "frontend source: frontend/runtime/" in frontend,
        "validator must scan frontend/app.js plus sorted frontend/runtime/*.js modules.",
    )
    add_check(
        checks,
        "battle_rules_runtime_module_present",
        bool(battle_rules),
        "frontend/runtime/battle-rules.js must be part of the scanned frontend source bundle.",
    )
    add_check(
        checks,
        "battle_input_controller_runtime_module_present",
        bool(input_controller),
        "frontend/runtime/battle-input-controller.js must be part of the scanned frontend source bundle.",
    )
    add_check(
        checks,
        "battle_entity_renderer_runtime_module_present",
        bool(entity_renderer) and has_named_export(entity_renderer, "createBattleEntityRenderer"),
        "frontend/runtime/battle-entity-renderer.js must own the canvas drag ghost renderer.",
    )
    add_check(
        checks,
        "battle_input_controller_runtime_exports_contract",
        bool(input_controller) and all(has_named_export(input_controller, name) for name in input_controller_exports),
        "battle-input-controller.js must export the battle canvas and drag handler contract.",
    )
    add_check(
        checks,
        "battle_rules_runtime_exports_contract",
        bool(battle_rules) and all(has_named_export(battle_rules, name) for name in battle_rule_exports),
        "battle-rules.js must export createBattleStateFactory/canPlaceToolAt/toolReady/buildSpawnSchedule.",
    )
    add_check(
        checks,
        "root_event_router_module_boundary",
        has_named_export(root_event_router, "createRootEventRouter")
        and "deployToolAt(" not in root_event_router
        and "finishBattle(" not in root_event_router
        and "state." not in root_event_router,
        "root-event-router must own listener wiring and delegate commands without owning gameplay state.",
    )
    add_check(
        checks,
        "runtime_projection_adapter_module_present",
        bool(projection_adapter),
        "frontend/runtime/runtime-projection-adapter.js must be part of the scanned frontend source bundle.",
    )
    add_check(
        checks,
        "runtime_projection_adapter_exports_contract",
        bool(projection_adapter) and all(has_named_export(projection_adapter, name) for name in projection_exports),
        "runtime-projection-adapter.js must export buildBattleToolProjection/assetKindForToolId.",
    )

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
                'canvas.addEventListener("pointermove", onCanvasPointerMove)',
                'canvas.addEventListener("pointerleave", onCanvasPointerLeave)',
            ],
        ),
        "battle canvas must update deployment preview while the pointer moves.",
    )
    add_check(
        checks,
        "toolbar_pointerdown_starts_drag",
        contains_all(
            root_event_router + frontend,
            [
                '.toolbar-card[data-tool]',
                "canBeginToolDrag(event, target)",
                "options.beginToolDrag(target.dataset.tool, event)",
                'canBeginToolDrag: (event) => state.view === "battle" && event.button === 0',
            ],
        ),
        "tool cards must start a drag gesture from pointerdown in the battle view.",
    )
    add_check(
        checks,
        "window_drag_lifecycle_registered",
        contains_all(
            root_event_router,
            [
                'windowRef.addEventListener("pointermove", options.updateToolDrag)',
                'windowRef.addEventListener("pointerup", options.finishToolDrag)',
                'windowRef.addEventListener("pointercancel", options.cancelToolDrag)',
            ],
        ),
        "drag move/up/cancel listeners must live on window so release or cancellation outside the card still completes cleanly.",
    )
    add_check(
        checks,
        "begin_drag_sets_tool_and_prevents_default",
        contains_all(
            begin_drag,
            [
                "battle.selectedTool = tool || \"basic\"",
                "if (!toolReady(battle.selectedTool))",
                "battle.draggingTool = null",
                "setBattleToast(toolUnavailableText(battle.selectedTool))",
                "return",
                "battle.draggingTool = battle.selectedTool",
                "battle.dragPointer = { x: event.clientX, y: event.clientY }",
                "battle.hoverCell = cellFromCanvasEvent(event)",
                "event.preventDefault()",
            ],
        ),
        "beginToolDrag must select the tool, block unavailable drags, initialize valid drag state, show unavailable feedback, and suppress native drag behavior.",
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
        )
        and finish_drag.count("deployToolAt(") == 1,
        "finishToolDrag must clear drag state and deploy exactly on pointer release over a valid battle cell.",
    )
    add_check(
        checks,
        "cancel_drag_clears_state_without_deploying",
        contains_all(
            cancel_drag,
            [
                "battle.draggingTool = null",
                "battle.dragPointer = null",
                "battle.hoverCell = null",
                "updateBattleDom()",
            ],
        )
        and "deployToolAt(" not in cancel_drag
        and "placeBasicDefense(" not in cancel_drag,
        "cancelToolDrag must clear drag state without deploying on pointer cancellation.",
    )
    add_check(
        checks,
        "toolbar_cards_are_non_native_drag_sources",
        contains_all(toolbar_markup, ['class="toolbar-card', 'data-action="select-tool"', 'data-tool="${safeText(tool.id)}"', 'draggable="false"', "is-dragging"]),
        "tool cards must expose game drag state instead of browser-native draggable behavior.",
    )
    add_check(
        checks,
        "battle_draws_preview_and_drag_ghost",
        ("drawDeployHints(ctx)" in draw_battle or "drawDeployHints(ctx," in draw_battle)
        and "drawDragGhost(ctx)" in draw_battle,
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
        'canvas.addEventListener("click", onCanvasClick)' in setup
        and "deployToolAt(battle.selectedTool, cell)" in js_section(
            frontend,
            "onBattleCanvasClick",
            "onBattleCanvasPointerMove",
        ),
        "click placement may remain as a fallback while drag-to-place is protected as the primary contract.",
    )
    add_check(
        checks,
        "no_technical_terms_in_player_drag_feedback",
        not re.search(
            r"\b(provider|schema|prompt|json|trace|api|model)\b",
            compact(begin_drag + update_drag + finish_drag + cancel_drag + unavailable_text + placement_feedback),
            re.I,
        ),
        "player-facing battle feedback must not expose provider/schema/prompt/debug wording.",
    )
    add_check(
        checks,
        "battle_smoke_probe_installed_after_metrics",
        "resizeBattleCanvas();\n    installSmokeProbe();" in setup,
        "battle smoke probe must be installed only after canvas metrics are initialized.",
    )
    add_check(
        checks,
        "battle_smoke_probe_query_gated",
        contains_all(
            install_probe,
            [
                "if (!battleVisualSmokeMode()) return;",
                "window.__AI_TD_BATTLE_SMOKE__ =",
                "snapshot: battleSmokeSnapshot",
                "deploymentPoint: battleSmokeDeploymentPoint",
            ],
        ),
        "battle smoke probe must only be exposed in battleVisualSmoke mode.",
    )
    add_check(
        checks,
        "battle_smoke_probe_uses_runtime_slots",
        contains_all(
            probe_point,
            [
                "assetKindForTool(tool)",
                "buildSlots()",
                "allowed.includes(assetKind)",
                "!isOccupied(position)",
                "projectCell(cell.x, cell.y)",
                "document.elementFromPoint",
                ".battle-tools",
                'closest("#battleCanvas, .battle-stage")',
            ],
        ),
        "battle smoke deployment point must derive from runtime build slots and avoid toolbar-covered targets.",
    )
    add_check(
        checks,
        "battle_smoke_probe_snapshot_is_read_only",
        contains_all(
            probe_snapshot,
            [
                'mode: "battleVisualSmoke"',
                "resources: battle.resources",
                "basicUses: battle.basicUses",
                "defensesCount: Array.isArray(battle.defenses)",
                "trapsCount: Array.isArray(battle.traps)",
                "deploymentPoint: battleSmokeDeploymentPoint",
            ],
        )
        and "deployToolAt(" not in probe_snapshot
        and "placeBasicDefense(" not in probe_snapshot
        and "state.view =" not in probe_snapshot,
        "battle smoke snapshot must expose read-only counters and never mutate battle state.",
    )
    add_check(
        checks,
        "battle_smoke_probe_snapshot_has_no_state_mutation",
        not has_state_mutation(probe_snapshot),
        "battle smoke snapshot must expose read-only counters and never mutate battle state.",
    )
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-output", type=Path, help="Write a structured validation report.")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frontend_sources = read_frontend_sources()
    frontend = frontend_source_bundle(frontend_sources)
    runtime_sources = runtime_module_sources(frontend_sources)
    css = STYLES_CSS.read_text(encoding="utf-8")
    checks = validate_contract(frontend, css, runtime_sources)
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
            "runtime_source_file_count": len(runtime_sources),
        },
        "frontend_source_bundle": frontend_source_bundle_report(frontend_sources),
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
