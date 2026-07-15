"""Validated catalog and runtime projection for compiled world instances."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..db import db_cursor


ROOT = Path(__file__).resolve().parents[3]
GENERATED_ROOT = ROOT / "content" / "generated_worlds"
LONG_NIGHT_ROOT = ROOT / "content" / "worldbooks" / "long_night_lanterns"
GENERATED_WORLD_PREVIEWS = {
    "xianxia_cloud_frontier": "/assets/map_visual_reference/strategic_xianxia_cloud_frontier.v0.1.jpg",
    "stonewind_border_march": "/assets/map_visual_reference/strategic_stonewind_border_march.v0.1.jpg",
    "stellar_anchor": "/assets/map_visual_reference/strategic_stellar_anchor.v0.1.jpg",
}
GENERATED_WORLD_BATTLE_BACKDROPS = GENERATED_WORLD_PREVIEWS
GENERATED_WORLD_NPC_PORTRAITS = {
    "xianxia_cloud_frontier": "/assets/generated_worlds/npc_portraits/xianxia_cloud_frontier.guardian_elder.v0.1.png",
    "stonewind_border_march": "/assets/generated_worlds/npc_portraits/stonewind_border_march.commander_aldrick.v0.1.png",
    "stellar_anchor": "/assets/generated_worlds/npc_portraits/stellar_anchor.orbital_commander.v0.1.png",
}


class WorldCatalogNotFoundError(LookupError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorldCatalogNotFoundError(str(path))
    return value


def _safe_path(raw: str) -> Path:
    path = Path(raw)
    path = path if path.is_absolute() else ROOT / path
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
        raise WorldCatalogNotFoundError(raw)
    return resolved


def _long_night_entry() -> dict[str, Any]:
    config = _load(LONG_NIGHT_ROOT / "world_instance_config.json")
    worldbook = _load(LONG_NIGHT_ROOT / "worldbook.json")
    return {
        "world_id": "long_night_lanterns",
        "display_name": config["worldbook_display_name"],
        "tagline": worldbook["summary"],
        "visual_style_name": config["visual_style_display_name"],
        "status": "ready",
        "source": "reviewed_mvp_template",
        "entry_node_id": "gray_lantern_station",
        "preview_url": "/assets/layered_maps/gray_lantern_station/composited/gray_lantern_station.layered_map.svg",
        "theme_tags": ["东方古风", "暗夜", "灯火", "驿站"],
        "world_config": config,
    }


def _generated_manifests() -> list[tuple[Path, dict[str, Any]]]:
    if not GENERATED_ROOT.exists():
        return []
    result = []
    for path in sorted(GENERATED_ROOT.glob("*/compiled_world_runtime_manifest.json")):
        try:
            manifest = _load(path)
            if manifest.get("schema_version") != "compiled_world_runtime_manifest.v0.1":
                continue
            result.append((path, manifest))
        except (OSError, ValueError, json.JSONDecodeError, WorldCatalogNotFoundError):
            continue
    return result


def _manifest_artifact(manifest: dict[str, Any], key: str) -> Path:
    artifacts = manifest.get("artifacts") or {}
    raw = artifacts.get(key) if isinstance(artifacts, dict) else None
    if not isinstance(raw, str) or not raw:
        raise WorldCatalogNotFoundError(f"{manifest.get('world_id')}:{key}")
    return _safe_path(raw)


def _map_output(manifest: dict[str, Any], kind_prefix: str) -> Path:
    report = manifest.get("map_compilation_report") or {}
    for ref in report.get("output_refs") or []:
        if isinstance(ref, dict) and str(ref.get("kind") or "").startswith(kind_prefix):
            return _safe_path(str(ref.get("path") or ""))
    raise WorldCatalogNotFoundError(f"{manifest.get('world_id')}:{kind_prefix}")


def _generated_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    style = _load(_manifest_artifact(manifest, "map_style_pack"))
    config = _load(_manifest_artifact(manifest, "world_instance_config"))
    report = manifest.get("map_compilation_report") or {}
    node_id = str(manifest.get("entry_node_id") or "")
    ready = report.get("status") == "completed"
    return {
        "world_id": manifest["world_id"],
        "display_name": manifest["display_name"],
        "tagline": manifest.get("tagline") or "一个由本次编译生成的世界实例。",
        "visual_style_name": style.get("style_pack_id"),
        "status": "ready" if ready else "compiling",
        "source": "ai_compiled_world",
        "entry_node_id": node_id,
        "preview_url": GENERATED_WORLD_PREVIEWS.get(
            str(manifest["world_id"]),
            f"/assets/generated_worlds/{manifest['world_id']}/maps/{node_id}/"
            f"composited/{node_id}.layered_map.svg",
        ) if ready else None,
        "theme_tags": list(style.get("node_theme_tags") or [])[:5],
        "world_config": config,
    }


def _generated_battle_config(
    worldbook: dict[str, Any],
    briefing: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    """Project one compiled world's facts into a coherent player presentation."""
    config = copy.deepcopy(source)
    config["display_name"] = briefing.get("display_name") or config.get("display_name")
    config["summary"] = briefing.get("summary") or config.get("summary")
    npc_ids = briefing.get("npcs_present") or []
    npc_id = str(npc_ids[0]) if npc_ids else ""
    npc = next(
        (
            item
            for item in worldbook.get("npc_archetypes") or []
            if isinstance(item, dict)
            and str(item.get("stable_internal_id") or item.get("id") or "") == npc_id
        ),
        {},
    )
    npc_name = str(npc.get("display_name") or "节点联络人")
    npc_voice = str(npc.get("voice") or briefing.get("summary") or "当前节点需要立即布防。")
    portrait_url = GENERATED_WORLD_NPC_PORTRAITS.get(
        str(worldbook.get("worldbook_id") or ""),
        "",
    )
    threat = briefing.get("threat") if isinstance(briefing.get("threat"), dict) else {}
    facility = (
        briefing.get("facility_state")
        if isinstance(briefing.get("facility_state"), dict)
        else {}
    )
    presentation = copy.deepcopy(config.get("presentation") or {})
    presentation.update(
        {
            "npc_display_name": npc_name,
            "npc_portrait_id": portrait_url,
            "intro_dialogue": {
                "name": npc_name,
                "line": npc_voice,
                "portrait_id": portrait_url,
            },
            "tactical_hints": {
                "enemy_weakness": threat.get("enemy_traits") or "观察敌潮路线并优先处理高速单位。",
                "npc_advice_before_sample": briefing.get("player_action_hint")
                or "先用基础防线稳住核心，等待试作品送达。",
                "npc_advice_after_sample": "试作品已经送达，结合它的实际效果调整防线。",
                "field_condition": facility.get("summary")
                or briefing.get("summary")
                or "当前节点处于紧急防守状态。",
            },
        }
    )
    config["presentation"] = presentation
    return config


def _generated_battle_visual_package(
    world_id: str,
    node_id: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    """Replace candidate procedural composites with a reviewed same-world backdrop."""
    url = GENERATED_WORLD_BATTLE_BACKDROPS.get(world_id)
    if not url:
        return source
    package = copy.deepcopy(source)
    layers = [
        item
        for item in package.get("layers") or []
        if isinstance(item, dict) and item.get("role") != "composited"
    ]
    layers.append(
        {
            "layer_id": f"layer_reviewed_world_backdrop_{node_id}",
            "role": "composited",
            "order": 100,
            "player_default": True,
            "source": "reviewed_ai_world_backdrop",
            "url": url,
            "width": 1600,
            "height": 900,
            "quality": {
                "gate_status": "passed",
                "alignment_status": "passed",
                "player_visible_quality": "passed",
            },
        }
    )
    package["layers"] = layers
    package["visual_release_note"] = (
        "Reviewed same-world low-semantic backdrop; runtime routes, slots, objectives, "
        "and entities remain authoritative overlays."
    )
    return package


def get_catalog() -> dict[str, Any]:
    worlds = [_long_night_entry()]
    for _, manifest in _generated_manifests():
        try:
            worlds.append(_generated_entry(manifest))
        except (OSError, ValueError, json.JSONDecodeError, WorldCatalogNotFoundError):
            continue
    return {
        "schema_version": "world_catalog.v0.1",
        "default_world_id": "long_night_lanterns",
        "worlds": worlds,
    }


def world_entry(world_id: str) -> dict[str, Any]:
    entry = next((item for item in get_catalog()["worlds"] if item["world_id"] == world_id), None)
    if entry is None or entry.get("status") != "ready":
        raise WorldCatalogNotFoundError(world_id)
    return entry


def _manifest_for_world(world_id: str) -> dict[str, Any]:
    for _, manifest in _generated_manifests():
        if manifest.get("world_id") == world_id:
            return manifest
    raise WorldCatalogNotFoundError(world_id)


def selected_world_id(session_id: str) -> str:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM world_instance WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if not row:
        return "long_night_lanterns"
    try:
        payload = json.loads(row["payload"])
    except (TypeError, json.JSONDecodeError):
        return "long_night_lanterns"
    return str(payload.get("worldbook_id") or "long_night_lanterns")


def load_world_bundle(world_id: str) -> dict[str, Any]:
    entry = world_entry(world_id)
    if world_id == "long_night_lanterns":
        return {
            "catalog_entry": entry,
            "worldbook": _load(LONG_NIGHT_ROOT / "worldbook.json"),
            "world_config": _load(LONG_NIGHT_ROOT / "world_instance_config.json"),
            "opening": _load(LONG_NIGHT_ROOT / "opening.json"),
            "map": _load(ROOT / "game_data/demo/initial_map.json"),
            "briefing": _load(ROOT / "game_data/demo/first_crisis_node.json"),
            "battle_config": _load(ROOT / "game_data/demo/first_battle_config.json"),
            "map_runtime_package": _load(ROOT / "examples/map_runtime_packages_v02/mvp_first_battle.map_runtime_package_v02.json"),
            "map_style_pack": _load(ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"),
            "map_render_plan": _load(ROOT / "examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json"),
            "semantic_visual_consistency_report": _load(ROOT / "examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json"),
            "layered_map_visual_package": _load(ROOT / "game_data/media/layered_maps/gray_lantern_station/layered_map_visual_package.v0.1.json"),
            "suggested_input": "我想做一个能拖慢影潮的临时装置。",
        }
    manifest = _manifest_for_world(world_id)
    worldbook = _load(_manifest_artifact(manifest, "worldbook"))
    briefing = _load(_manifest_artifact(manifest, "first_crisis_node"))
    battle_config = _generated_battle_config(
        worldbook,
        briefing,
        _load(_manifest_artifact(manifest, "first_battle_config")),
    )
    layered_visual = _generated_battle_visual_package(
        world_id,
        str(manifest.get("entry_node_id") or battle_config.get("node_id") or ""),
        _load(_map_output(manifest, "layered_map_visual_package")),
    )
    return {
        "catalog_entry": entry,
        "worldbook": worldbook,
        "world_config": _load(_manifest_artifact(manifest, "world_instance_config")),
        "opening": _load(_manifest_artifact(manifest, "opening")),
        "map": _load(_manifest_artifact(manifest, "initial_map")),
        "briefing": briefing,
        "battle_config": battle_config,
        "map_runtime_package": _load(_map_output(manifest, "map_runtime_package")),
        "map_style_pack": _load(_manifest_artifact(manifest, "map_style_pack")),
        "map_render_plan": _load(_map_output(manifest, "procedural_map_render_plan")),
        "semantic_visual_consistency_report": _load(_map_output(manifest, "semantic_visual_consistency_report")),
        "layered_map_visual_package": layered_visual,
        "suggested_input": manifest.get("suggested_research_intent"),
    }


def session_bundle(session_id: str) -> dict[str, Any]:
    return load_world_bundle(selected_world_id(session_id))
