#!/usr/bin/env python3
"""Validate fixture-backed multi-node battle settlement.

This check exercises the backend service layer without FastAPI/TestClient. It
uses a temporary SQLite database and confirms the MVP playable route can
advance through gray_lantern_station, lamp_wick_store, and old_signal_tower.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fd, db_path = tempfile.mkstemp(prefix="ai_td_multinode_settlement_", suffix=".db")
    os.close(fd)
    os.environ["APP_DB_PATH"] = db_path
    try:
        from backend.app.db import db_cursor, init_db, now_iso, reset_connection
        from backend.app.services import campaign_router_service, frontend_mock_service

        init_db(db_path)
        reset_connection()
        ts = now_iso()
        session_id = "validate_multinode_settlement"
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO sessions "
                "(session_id, display_name, created_at, last_active_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, "validator", ts, ts),
            )

        frontend_mock_service.create_world_instance(session_id)
        route0 = campaign_router_service.get_campaign_router(session_id)["campaign_router"]
        assert route0["current"]["node_id"] == "gray_lantern_station"
        assert route0["next"]["node_id"] == "lamp_wick_store"

        first = frontend_mock_service.record_battle_result(
            session_id, "gray_lantern_station", {"result": "victory"}
        )["settlement"]
        assert first["settlement_mode"] == "transaction"
        assert first["run_world_state"]["progress"]["phase"] == "post_first_defense"

        route1 = campaign_router_service.get_campaign_router(session_id)["campaign_router"]
        assert route1["current"]["node_id"] == "lamp_wick_store"
        assert route1["next"]["node_id"] == "old_signal_tower"

        wick = frontend_mock_service.record_battle_result(
            session_id, "lamp_wick_store", {"result": "victory"}
        )["settlement"]
        assert wick["settlement_mode"] == "transaction"
        assert wick["world_delta"]["source"] == "battle_result"
        assert wick["world_delta_transaction"]["source"] == "battle_result"
        assert wick["world_delta_transaction"]["transaction_id"] == (
            "tx_stage_04_wick_store_pressure_battle_001"
        )
        assert wick["core_artifact_refs"]["world_delta_transaction"].endswith(
            "stage_04_wick_store_pressure_battle.world_delta_transaction.json"
        )
        assert wick["run_world_state"]["progress"]["phase"] == "post_wick_store_defense"

        route2 = campaign_router_service.get_campaign_router(session_id)["campaign_router"]
        assert route2["current"]["node_id"] == "old_signal_tower"

        tower = frontend_mock_service.record_battle_result(
            session_id, "old_signal_tower", {"result": "victory"}
        )["settlement"]
        assert tower["settlement_mode"] == "fixture_bridge"
        assert tower["world_delta"] is None
        assert tower["world_delta_transaction"]["source"] == "research_job"
        assert tower["fixture_baseline"]["baseline_type"] == "research_job"
        assert tower["fixture_baseline"]["baseline_ref"].endswith(
            "demo_after_stage_06_signal_resonance.run_world_state.json"
        )
        assert tower["run_world_state"]["progress"]["phase"] == "signal_resonance_trial"

    finally:
        Path(db_path).unlink(missing_ok=True)

    print("OK multinode battle settlement")
    print("- gray_lantern_station -> lamp_wick_store -> old_signal_tower route advances")
    print("- lamp_wick_store uses battle_result transaction stage04")
    print("- old_signal_tower is honestly marked as fixture_bridge/research_job baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
