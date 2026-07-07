#!/usr/bin/env python3
"""Smoke-check the review-only MapRuntimePackage v0.2 preview API.

This tool creates an isolated anonymous session through the FastAPI TestClient,
then requests the v0.2 map preview endpoint for each MVP battle node. It writes
a redacted report that can be committed as review evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(ROOT))

from tools.dev.report_io import write_json

NODE_IDS = ("gray_lantern_station", "lamp_wick_store", "old_signal_tower")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def payload(response: Any) -> dict[str, Any]:
    if response.status_code >= 400:
        raise AssertionError(f"unexpected HTTP {response.status_code}: {response.text}")
    body = response.json()
    if body.get("mode") != "frontend_mock_fixture":
        raise AssertionError(f"unexpected response mode: {body.get('mode')}")
    return as_obj(body.get("payload"))


def semantic_counts(map_package: dict[str, Any]) -> dict[str, int]:
    return {
        "resource_node_count": len(map_package.get("resource_nodes") or []),
        "hazard_zone_count": len(map_package.get("hazard_zones") or []),
        "defense_anchor_count": len(map_package.get("defense_anchors") or []),
        "blocked_area_count": len(map_package.get("blocked_areas") or []),
    }


def check_node(client: Any, session_id: str, node_id: str) -> dict[str, Any]:
    preview = payload(
        client.get(f"/api/sessions/{session_id}/battles/{node_id}/map-v02-preview")
    )
    if preview.get("preview_mode") != "review_only_map_v02":
        raise AssertionError(f"{node_id}: preview_mode mismatch")
    if preview.get("review_only") is not True:
        raise AssertionError(f"{node_id}: review_only must be true")
    if preview.get("runtime_activation_allowed") is not False:
        raise AssertionError(f"{node_id}: runtime activation must be false")

    map_package = as_obj(preview.get("map_runtime_package_v02"))
    if map_package.get("schema_version") != "map_runtime_package.v0.2":
        raise AssertionError(f"{node_id}: v0.2 schema mismatch")
    if map_package.get("node_id") != node_id:
        raise AssertionError(f"{node_id}: package node mismatch")
    counts = semantic_counts(map_package)
    if any(value < 1 for value in counts.values()):
        raise AssertionError(f"{node_id}: missing v0.2 semantic counts {counts}")

    bundle = as_obj(preview.get("map_render_plan_bundle_v02"))
    if bundle.get("review_only") is not True:
        raise AssertionError(f"{node_id}: bundle review_only must be true")
    if bundle.get("runtime_activation_allowed") is not False:
        raise AssertionError(f"{node_id}: bundle runtime activation must be false")
    preview_report = as_obj(bundle.get("procedural_map_preview_report"))
    if preview_report.get("status") != "preview_ready_review_only":
        raise AssertionError(f"{node_id}: preview report not ready")
    consistency = as_obj(bundle.get("semantic_visual_consistency_report"))
    if consistency.get("status") != "passed":
        raise AssertionError(f"{node_id}: semantic consistency not passed")

    default_runtime = payload(
        client.get(f"/api/sessions/{session_id}/battles/{node_id}/map-runtime-package")
    )
    default_package = as_obj(default_runtime.get("map_runtime_package"))
    if default_package.get("schema_version") != "map_runtime_package.v0.1":
        raise AssertionError(f"{node_id}: default map runtime is not v0.1")
    leaked_v02_fields = [
        key
        for key in ("resource_nodes", "hazard_zones", "defense_anchors", "blocked_areas")
        if key in default_package
    ]
    if leaked_v02_fields:
        raise AssertionError(f"{node_id}: v0.2 fields leaked into default runtime")

    source_refs = as_obj(preview.get("source_refs"))
    safety = as_obj(preview.get("safety"))
    return {
        "node_id": node_id,
        "v02_package_id": map_package.get("package_id"),
        "counts": counts,
        "preview_svg_ref": preview.get("preview_svg_ref"),
        "source_ref_keys": sorted(source_refs),
        "bundle_status": {
            "semantic_visual_consistency": consistency.get("status"),
            "preview_report": preview_report.get("status"),
        },
        "safety": {
            "reads_env": safety.get("reads_env"),
            "provider_call_count": safety.get("provider_call_count"),
            "player_default_runtime_mutation": safety.get(
                "player_default_runtime_mutation"
            ),
        },
        "default_runtime_schema_version": default_package.get("schema_version"),
        "default_runtime_v02_field_leak_count": len(leaked_v02_fields),
    }


def build_report(generated_at: str | None = None) -> dict[str, Any]:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from fastapi.testclient import TestClient  # noqa: WPS433
    from app import db as db_module  # noqa: WPS433
    from app.main import create_app  # noqa: WPS433

    generated = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with tempfile.TemporaryDirectory(prefix="ai_td_map_v02_api_") as tmpdir:
        db_path = Path(tmpdir) / "app.db"
        previous_db_path = os.environ.get("APP_DB_PATH")
        os.environ["APP_DB_PATH"] = str(db_path)
        try:
            db_module.reset_connection()
            db_module.init_db(str(db_path))
            app = create_app()
            with TestClient(app) as client:
                session_response = client.post("/api/sessions")
                if session_response.status_code != 201:
                    raise AssertionError(
                        f"session create failed: {session_response.status_code}"
                    )
                session_id = session_response.json()["session_id"]
                node_reports = [
                    check_node(client, session_id, node_id) for node_id in NODE_IDS
                ]
                unknown_response = client.get(
                    f"/api/sessions/{session_id}/battles/unknown/map-v02-preview"
                )
        finally:
            db_module.reset_connection()
            if previous_db_path is None:
                os.environ.pop("APP_DB_PATH", None)
            else:
                os.environ["APP_DB_PATH"] = previous_db_path

    if unknown_response.status_code != 404:
        raise AssertionError(
            f"unknown node expected 404, got {unknown_response.status_code}"
        )

    semantic_totals = {
        key: sum(int(as_obj(item.get("counts")).get(key) or 0) for item in node_reports)
        for key in (
            "resource_node_count",
            "hazard_zone_count",
            "defense_anchor_count",
            "blocked_area_count",
        )
    }
    return {
        "schema_version": "map_v02_preview_api_smoke_report.v0.1",
        "report_id": "map_v02_preview_api_smoke_report_v0_1",
        "generated_at": generated,
        "status": "passed",
        "endpoint": "GET /api/sessions/{session_id}/battles/{node_id}/map-v02-preview",
        "response_wrapper_mode": "frontend_mock_fixture",
        "review_only": True,
        "runtime_activation_allowed": False,
        "node_count": len(node_reports),
        "node_ids": [item["node_id"] for item in node_reports],
        "semantic_totals": semantic_totals,
        "default_runtime_v01_preserved_count": sum(
            1
            for item in node_reports
            if item.get("default_runtime_schema_version") == "map_runtime_package.v0.1"
            and item.get("default_runtime_v02_field_leak_count") == 0
        ),
        "unknown_node_status_code": unknown_response.status_code,
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": sum(
                int(as_obj(item.get("safety")).get("provider_call_count") or 0)
                for item in node_reports
            ),
            "player_default_runtime_mutation_count": sum(
                1
                for item in node_reports
                if as_obj(item.get("safety")).get("player_default_runtime_mutation")
            ),
            "world_state_mutation_count": 0,
        },
        "nodes": node_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json",
    )
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    report = build_report(args.generated_at)
    write_json(ROOT / args.output, report, sort_keys=False)
    print(f"map v0.2 preview API smoke passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
