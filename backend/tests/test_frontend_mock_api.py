"""Tests for the fixture-backed frontend mock API surface."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_PROVIDER_ADAPTER_DIR = _ROOT / "tools" / "provider_adapter"
if str(_PROVIDER_ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(_PROVIDER_ADAPTER_DIR))
_TOOLS_DEV_DIR = _ROOT / "tools" / "dev"
if str(_TOOLS_DEV_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DEV_DIR))

from run_provider_adapter import build_dry_run_artifacts  # noqa: E402
from validate_provider_adapter_runner_handoff_outbox import (  # noqa: E402
    validate_provider_adapter_runner_handoff_outbox,
)
from backend.app.services.generation_scheduler_artifact_ledger_builders import (  # noqa: E402
    build_artifact_ledger_payload,
    compact_generation_artifact_ledger,
    compact_provider_artifact_promotion_report,
    compact_provider_artifact_staging,
    compact_provider_output_envelope,
)
from app.services.generation_scheduler_artifact_ledger_repository import (  # noqa: E402
    latest_generation_executor_request_ledger_entry,
    latest_provider_adapter_execution_ledger_entry,
    latest_provider_authorization_ledger_entry,
    latest_provider_output_envelope_ledger_entry,
    load_generation_artifact_ledger_items,
    upsert_generation_artifact_ledger,
)
from backend.app.services.generation_scheduler_handoff_builders import (  # noqa: E402
    build_provider_adapter_runner_handoff_outbox,
    provider_runner_outbox_safety,
)
from backend.app.services.generation_scheduler_artifact_fixtures import (  # noqa: E402
    provider_artifact_fixture_metadata,
    provider_artifact_fixture_paths,
)
from backend.app.services.generation_scheduler_import_safety import (  # noqa: E402
    resolve_import_path,
)
from backend.app.services.generation_scheduler_provider_artifact_review_helpers import (  # noqa: E402
    provider_artifact_promotion_allowed,
    validate_provider_artifact_review_contract,
)
from backend.app.services.generation_scheduler_provider_execution_builders import (  # noqa: E402
    build_generation_executor_run_request_payload,
    build_live_executor_guard_payload,
    build_provider_adapter_execution_receipt_payload,
    build_provider_execution_authorization_payload,
    compact_generation_executor_run_request,
    compact_provider_adapter_execution_receipt,
    compact_provider_execution_authorization,
    provider_authorization_ref,
    rehydrate_generation_executor_request_for_runner,
    rehydrate_provider_authorization_for_runner,
)
from backend.app.services.generation_scheduler_prefetch_cache_builders import (  # noqa: E402
    build_generation_prefetch_cache_payload,
    ledger_entry_ref,
    prefetch_cache_status,
)
from backend.app.services.generation_scheduler_activation_gate_builders import (  # noqa: E402
    build_generation_activation_gate_payload,
)
from backend.app.services.generation_scheduler_shared_prefetch_cache_builders import (  # noqa: E402
    build_shared_prefetch_cache_records,
    compact_shared_prefetch_cache,
)
from backend.app.services.generation_scheduler_shared_prefetch_cache_hit_builders import (  # noqa: E402
    build_shared_prefetch_cache_hit_payload,
)
from backend.app.services.generation_scheduler_shared_cache_reuse_builders import (  # noqa: E402
    REUSE_CANDIDATE_CACHE_STATUS,
    REUSE_CANDIDATE_LEDGER_KIND,
    REUSE_CANDIDATE_LEDGER_STATUS,
    build_shared_cache_reuse_candidate,
    compact_shared_cache_reuse_candidate,
)
from backend.app.services.generation_scheduler_runtime_build_request_builders import (  # noqa: E402
    RUNTIME_BUILD_REQUEST_CACHE_STATUS,
    RUNTIME_BUILD_REQUEST_LEDGER_KIND,
    RUNTIME_BUILD_REQUEST_LEDGER_STATUS,
    build_runtime_build_request,
    compact_runtime_build_request,
)
from backend.app.services.generation_scheduler_runtime_artifact_build_report_builders import (  # noqa: E402
    RUNTIME_ARTIFACT_BUILD_REPORT_CACHE_STATUS,
    RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND,
    RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS,
    build_runtime_artifact_build_report,
    compact_runtime_artifact_build_report,
)
from backend.app.services.generation_scheduler_runtime_artifact_target_resolver import (  # noqa: E402
    resolve_runtime_artifact_targets,
)
from backend.app.services.generation_scheduler_runtime_activation_authorization_builders import (  # noqa: E402
    RUNTIME_ACTIVATION_AUTHORIZATION_CACHE_STATUS,
    RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_KIND,
    RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_STATUS,
)
from backend.app.services.generation_scheduler_shared_prefetch_cache_repository import (  # noqa: E402
    load_shared_prefetch_cache_records,
    upsert_shared_prefetch_cache_records,
)
from backend.app.services.generation_scheduler_provider_adapter_import_helpers import (  # noqa: E402
    provider_adapter_runner_import_alignment_checks,
    validate_provider_adapter_runner_import_contract,
)
from backend.app.services.generation_scheduler_dispatcher_controls import (  # noqa: E402
    dispatcher_step_metadata,
    reject_targeted_metadata,
    requested_max_items,
    targeted_metadata_keys,
)
from app.services.generation_scheduler_run_queue_repository import (  # noqa: E402
    insert_generation_queue_items,
    insert_generation_schedule_run,
    load_generation_queue_item_row,
    load_generation_queue_items,
    load_latest_generation_schedule_run,
    load_next_generation_item_row_by_status,
    update_generation_queue_item,
)
from app.services.generation_scheduler_worker_state_repository import (  # noqa: E402
    insert_provider_guard_log,
    load_provider_guard_logs,
    load_worker_cache_items,
    upsert_worker_cache_payload,
)
from backend.app.services.generation_scheduler_run_queue_builders import (  # noqa: E402
    build_generation_queue_items_from_run,
    build_generation_schedule_buffer,
    build_generation_schedule_run_payload,
    build_worker_cache_payload,
    compact_generation_queue,
    compact_worker_cache,
    safe_id_fragment,
)


def _create_session(client) -> str:
    resp = client.post("/api/sessions")
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def _payload(resp):
    assert resp.status_code < 400, resp.text
    body = resp.json()
    assert body["mode"] == "frontend_mock_fixture"
    return body["payload"]


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_approved_map_runtime_authorization_report(tmp_path: Path) -> Path:
    report = _load_json(
        _ROOT / "examples/review_packs/map_runtime_activation_authorization_report.v0.1.json"
    )
    report["status"] = "authorized_for_gate_review"
    report["inputs"]["approval_plan_supplied"] = True
    for node in report["nodes"]:
        node["authorization_decision"] = "approved"
        node["authorization_status"] = "approved_for_gate_review"
        node["activation_authorized_for_gate"] = True
        node["blocking_reasons"] = []
        node["approval_record"] = {
            "approved_by": "pytest_map_runtime_v02_activation_selector",
            "approved_at": "2026-07-05T00:00:00Z",
            "notes": "temporary approved fixture for activation selector tests",
            "target_match": True,
        }
    node_count = len(report["nodes"])
    report["summary"]["approved_count"] = node_count
    report["summary"]["pending_count"] = 0
    report["summary"]["denied_count"] = 0
    report["summary"]["authorization_status_counts"] = {
        "approved_for_gate_review": node_count
    }
    report["summary"]["activation_authorized_for_gate_count"] = node_count
    output = tmp_path / "approved_map_runtime_activation_authorization_report.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


def test_generation_run_queue_repository_inserts_loads_and_updates(client):
    sid = _create_session(client)
    ts = "2026-07-03T00:00:00Z"
    plan_path = _ROOT / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json"
    run_report_path = (
        _ROOT / "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json"
    )
    run_payload = build_generation_schedule_run_payload(
        sid,
        "gsrun_repo_test",
        ts,
        plan=_load_json(plan_path),
        run_report=_load_json(run_report_path),
        refs={"plan": _rel(plan_path), "run_report": _rel(run_report_path)},
    )
    queue_items = build_generation_queue_items_from_run(run_payload, ts)

    insert_generation_schedule_run(run_payload, ts)
    insert_generation_queue_items(queue_items)

    latest = load_latest_generation_schedule_run(sid)
    all_items = load_generation_queue_items(sid)
    run_items = load_generation_queue_items(sid, "gsrun_repo_test")
    other_run_items = load_generation_queue_items(sid, "gsrun_other")
    next_queued = load_next_generation_item_row_by_status(sid, "queued")

    assert latest is not None
    assert latest["run_id"] == "gsrun_repo_test"
    assert len(all_items) == len(queue_items)
    assert len(run_items) == len(queue_items)
    assert other_run_items == []
    assert next_queued is not None
    assert next_queued["status"] == "queued"

    selected = load_generation_queue_item_row(
        sid,
        str(next_queued["schedule_item_id"]),
    )
    assert selected is not None
    assert selected["id"] == next_queued["id"]

    payload = selected["payload"]
    payload["status"] = "claimed"
    payload["updated_at"] = "2026-07-03T00:05:00Z"
    payload["claimed_by"] = "repo-test"
    update_generation_queue_item(
        int(selected["id"]),
        "claimed",
        payload,
        "2026-07-03T00:05:00Z",
    )

    updated = load_generation_queue_item_row(sid, str(selected["schedule_item_id"]))
    assert updated is not None
    assert updated["status"] == "claimed"
    assert updated["payload"]["claimed_by"] == "repo-test"


def test_generation_worker_state_repository_upserts_cache_and_filters_guard_logs(client):
    sid = _create_session(client)
    ts = "2026-07-03T00:00:00Z"
    plan_path = _ROOT / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json"
    run_report_path = (
        _ROOT / "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json"
    )
    run_payload = build_generation_schedule_run_payload(
        sid,
        "gsrun_worker_state_test",
        ts,
        plan=_load_json(plan_path),
        run_report=_load_json(run_report_path),
        refs={"plan": _rel(plan_path), "run_report": _rel(run_report_path)},
    )
    queue_items = build_generation_queue_items_from_run(run_payload, ts)
    insert_generation_schedule_run(run_payload, ts)
    insert_generation_queue_items(queue_items)
    queue_payload = next(
        item for item in queue_items if item["status"] == "queued"
    )

    cache_payload = build_worker_cache_payload(queue_payload, ts)
    upsert_worker_cache_payload(cache_payload, ts)
    updated_cache = {
        **cache_payload,
        "status": "waiting_review",
        "updated_at": "2026-07-03T00:05:00Z",
    }
    upsert_worker_cache_payload(updated_cache, "2026-07-03T00:05:00Z")

    all_cache = load_worker_cache_items(sid)
    run_cache = load_worker_cache_items(sid, "gsrun_worker_state_test")
    other_run_cache = load_worker_cache_items(sid, "gsrun_other")

    assert len(all_cache) == 1
    assert len(run_cache) == 1
    assert other_run_cache == []
    assert run_cache[0]["created_at"] == ts
    assert run_cache[0]["updated_at"] == "2026-07-03T00:05:00Z"
    assert run_cache[0]["status"] == "waiting_review"

    guard_payload = build_live_executor_guard_payload(
        queue_payload,
        {"worker_id": "guard-worker", "note": "guard log test"},
        ts,
    )
    insert_provider_guard_log(guard_payload, ts)
    insert_provider_guard_log(
        {
            "schema_version": "not_a_guard.v0.1",
            "session_id": sid,
            "run_id": "gsrun_worker_state_test",
            "created_at": ts,
        },
        ts,
    )

    guard_logs = load_provider_guard_logs(sid, "gsrun_worker_state_test")
    other_guard_logs = load_provider_guard_logs(sid, "gsrun_other")

    assert len(guard_logs) == 1
    assert guard_logs[0]["guard_id"] == guard_payload["guard_id"]
    assert other_guard_logs == []


def test_generation_artifact_ledger_repository_upserts_and_filters(client):
    sid = _create_session(client)
    first = build_artifact_ledger_payload(
        session_id=sid,
        artifact_kind="generation_executor_run_request",
        source_id="gexec_test",
        status="prepared_pending_explicit_authorization",
        compact={
            "source": {"schedule_item_id": "sched_test"},
            "provider_execution_intent": {},
        },
        ts="2026-07-03T00:00:00Z",
        latest_run={"run_id": "gsrun_test"},
        schedule_item_id="sched_test",
        worker_id="worker-test",
        note="first write",
    )
    upsert_generation_artifact_ledger(first)

    second = {
        **first,
        "status": "prepared_pending_explicit_authorization",
        "updated_at": "2026-07-03T00:05:00Z",
        "note": "second write",
    }
    upsert_generation_artifact_ledger(second)

    all_items = load_generation_artifact_ledger_items(sid)
    run_items = load_generation_artifact_ledger_items(sid, "gsrun_test")
    other_run_items = load_generation_artifact_ledger_items(sid, "gsrun_other")

    assert len(all_items) == 1
    assert len(run_items) == 1
    assert other_run_items == []
    assert run_items[0]["created_at"] == "2026-07-03T00:00:00Z"
    assert run_items[0]["updated_at"] == "2026-07-03T00:05:00Z"
    assert run_items[0]["note"] == "second write"

    latest = latest_generation_executor_request_ledger_entry(
        sid,
        "gsrun_test",
        "sched_test",
    )
    assert latest is not None
    assert latest["source_id"] == "gexec_test"


def test_generation_artifact_ledger_repository_finds_latest_provider_chain(client):
    sid = _create_session(client)
    ts = "2026-07-03T00:00:00Z"
    authorization = build_artifact_ledger_payload(
        session_id=sid,
        artifact_kind="provider_execution_authorization",
        source_id="auth_test",
        status="granted_for_provider_adapter",
        compact={"authorization_ref": "auth_test"},
        ts=ts,
        latest_run={"run_id": "gsrun_test"},
        schedule_item_id="sched_test",
        worker_id="worker-test",
        note=None,
    )
    receipt = build_artifact_ledger_payload(
        session_id=sid,
        artifact_kind="provider_adapter_execution_receipt",
        source_id="receipt_test",
        status="fixture_output_ready_for_envelope",
        compact={"execution": {"authorization_ref": "auth_test"}},
        ts=ts,
        latest_run={"run_id": "gsrun_test"},
        schedule_item_id="sched_test",
        worker_id="worker-test",
        note=None,
    )
    envelope = build_artifact_ledger_payload(
        session_id=sid,
        artifact_kind="provider_output_envelope",
        source_id="pout_test",
        status="recorded_review_only",
        compact={"envelope_id": "pout_test"},
        ts=ts,
        latest_run={"run_id": "gsrun_test"},
        schedule_item_id="sched_test",
        worker_id="worker-test",
        note=None,
    )
    for item in (authorization, receipt, envelope):
        upsert_generation_artifact_ledger(item)

    assert latest_provider_authorization_ledger_entry(
        sid,
        "gsrun_test",
        "sched_test",
        "auth_test",
    )["source_id"] == "auth_test"
    assert latest_provider_adapter_execution_ledger_entry(
        sid,
        "gsrun_test",
        "sched_test",
        "auth_test",
    )["source_id"] == "receipt_test"
    assert latest_provider_output_envelope_ledger_entry(
        sid,
        "gsrun_test",
        "sched_test",
        "pout_test",
    )["source_id"] == "pout_test"
    assert latest_provider_adapter_execution_ledger_entry(
        sid,
        "gsrun_test",
        "sched_test",
        "wrong_auth",
    ) is None


def test_generation_provider_execution_builders_keep_guard_and_request_contract():
    queue_payload = {
        "run_id": "gsrun_test",
        "session_id": "session_test",
        "schedule_item_id": "sched/demo visual",
        "object_kind": "map_visual_prefetch",
        "object_ref": "map:demo",
        "latency_class": "background_prefetch",
        "provider_policy": {"mode": "manual_authorized_demo", "profile": "image"},
        "attempt_count": 1,
        "max_attempts": 3,
        "fallback_ref": "fallback:map",
    }
    ts = "2026-07-03T00:00:00Z"

    guard = build_live_executor_guard_payload(
        queue_payload,
        {"worker_id": "guard-worker", "note": "guard test"},
        ts,
    )
    assert guard["guard_id"] == "pguard_gsrun_test_sched_demo_visual_01"
    assert guard["status"] == "blocked_pending_explicit_authorization"
    assert guard["provider_call_performed"] is False
    assert guard["world_mutation_performed"] is False
    assert guard["activation_allowed_now"] is False
    assert guard["safe_content_policy"]["reads_env"] is False

    request = build_generation_executor_run_request_payload(
        queue_payload,
        guard,
        {"worker_id": "request-worker"},
        ts,
        input_refs=[{"ref_id": "plan", "kind": "schedule_plan", "path": "plan.json"}],
        context_refs=[
            {"ref_id": "context", "kind": "context_package", "path": "context.json"}
        ],
    )
    assert request["request_id"] == "gexec_gsrun_test_sched_demo_visual_01"
    assert request["provider_execution_intent"]["authorization_required"] is True
    assert request["provider_execution_intent"][
        "provider_call_performed_by_request_builder"
    ] is False
    assert request["request_builder_safety"]["calls_provider"] is False

    compact = compact_generation_executor_run_request(request)
    assert compact["input_ref_count"] == 1
    assert compact["context_ref_count"] == 1
    assert compact["requested_output"]["result_kind"] == "image_candidate"


def test_generation_provider_execution_builders_keep_authorization_and_receipt_contract():
    executor_entry = {
        "session_id": "session_test",
        "run_id": "gsrun_test",
        "schedule_item_id": "sched/demo visual",
        "source_id": "gexec_test",
        "created_at": "2026-07-03T00:00:00Z",
        "compact": {
            "source": {
                "run_id": "gsrun_test",
                "schedule_item_id": "sched/demo visual",
                "object_kind": "map_visual_prefetch",
                "object_ref": "map:demo",
                "guard_id": "pguard_test",
                "provider_mode": "manual_authorized_demo",
                "provider_profile": "image",
            },
            "provider_execution_intent": {
                "provider_mode": "manual_authorized_demo",
                "provider_profile": "image",
            },
            "execution_budget": {
                "attempt_count": 1,
                "max_attempts": 3,
                "remaining_attempts": 2,
            },
            "request_builder_safety": {
                "reads_env": False,
                "calls_provider": False,
                "stores_prompt_body": False,
                "stores_provider_body": False,
                "writes_world_state": False,
                "activates_runtime": False,
            },
        },
    }
    ts = "2026-07-03T00:00:00Z"

    authorization = build_provider_execution_authorization_payload(
        executor_entry,
        {"worker_id": "auth-worker"},
        ts,
    )
    assert authorization["authorization_ref"] == provider_authorization_ref(
        "sched/demo visual"
    )
    assert authorization["authority"]["provider_execution_authorized"] is True
    assert authorization["authority"]["runtime_activation_allowed"] is False
    assert authorization["authorization_builder_safety"]["calls_provider"] is False

    auth_compact = compact_provider_execution_authorization(authorization)
    assert auth_compact["authorization"]["granted"] is True
    assert auth_compact["execution_constraints"]["required_next_gates"] == [
        "provider_output_envelope",
        "local_artifact_staging_manifest",
        "media_gate",
        "semantic_gate",
        "human_review",
        "promotion_report",
    ]

    auth_entry = {
        "session_id": "session_test",
        "run_id": "gsrun_test",
        "schedule_item_id": "sched/demo visual",
        "source_id": authorization["authorization_ref"],
        "created_at": ts,
        "compact": auth_compact,
    }
    receipt = build_provider_adapter_execution_receipt_payload(
        auth_entry,
        {"worker_id": "adapter-worker"},
        ts,
    )
    assert receipt["execution_receipt_id"] == (
        "padapter_sched_demo_visual_fixture_001"
    )
    assert receipt["execution"]["provider_call_performed_by_receipt_builder"] is False
    assert receipt["adapter_safety"]["writes_world_state"] is False

    receipt_compact = compact_provider_adapter_execution_receipt(receipt)
    assert receipt_compact["execution"]["authorization_ref"] == (
        authorization["authorization_ref"]
    )
    assert receipt_compact["output_contract"][
        "must_write_provider_output_envelope"
    ] is True

    rehydrated_request = rehydrate_generation_executor_request_for_runner(
        executor_entry,
        created_at=ts,
        schedule_plan_ref="plan.json",
    )
    assert rehydrated_request["input_refs"][0]["path"] == "plan.json"
    assert rehydrated_request["request_builder_safety"]["calls_provider"] is False

    rehydrated_authorization = rehydrate_provider_authorization_for_runner(
        auth_entry,
        created_at=ts,
    )
    assert rehydrated_authorization["authorization_ref"] == (
        authorization["authorization_ref"]
    )
    assert rehydrated_authorization["authorization_builder_safety"]["reads_env"] is False


def test_provider_adapter_runner_import_helpers_validate_alignment_contract():
    receipt = {
        "source": {
            "schedule_item_id": "sched_test",
            "authorization_ref": "auth_test",
            "executor_request_id": "gexec_test",
            "object_kind": "map_visual_prefetch",
            "object_ref": "map:test",
            "provider_profile": "image",
            "provider_mode": "manual_authorized_demo",
        },
        "execution": {"provider_call_performed_by_receipt_builder": True},
    }
    envelope = {
        "source": {
            "schedule_item_id": "sched_test",
            "object_kind": "map_visual_prefetch",
            "object_ref": "map:test",
            "provider_profile": "image",
            "provider_mode": "manual_authorized_demo",
        },
        "provider_call": {"performed": True, "authorization_ref": "auth_test"},
    }

    checks = provider_adapter_runner_import_alignment_checks(
        receipt,
        envelope,
        schedule_item_id="sched_test",
        authorization_ref="auth_test",
        executor_request_id="gexec_test",
    )
    assert all(checks.values())
    contract = validate_provider_adapter_runner_import_contract(
        receipt,
        envelope,
        schedule_item_id="sched_test",
        authorization_ref="auth_test",
        executor_request_id="gexec_test",
    )
    assert contract["receipt_source"]["schedule_item_id"] == "sched_test"
    assert contract["envelope_source"]["object_ref"] == "map:test"


def test_provider_adapter_runner_import_helpers_report_failed_alignment_names():
    receipt = {
        "source": {
            "schedule_item_id": "sched_test",
            "authorization_ref": "auth_test",
            "executor_request_id": "gexec_test",
            "object_kind": "map_visual_prefetch",
            "object_ref": "map:test",
            "provider_profile": "image",
            "provider_mode": "manual_authorized_demo",
        },
        "execution": {"provider_call_performed_by_receipt_builder": True},
    }
    envelope = {
        "source": {
            "schedule_item_id": "sched_other",
            "object_kind": "map_visual_prefetch",
            "object_ref": "map:other",
            "provider_profile": "image",
            "provider_mode": "manual_authorized_demo",
        },
        "provider_call": {"performed": True, "authorization_ref": "auth_other"},
    }

    try:
        validate_provider_adapter_runner_import_contract(
            receipt,
            envelope,
            schedule_item_id="sched_test",
            authorization_ref="auth_test",
            executor_request_id="gexec_test",
        )
    except ValueError as exc:
        message = str(exc)
        assert "envelope_schedule_item_id" in message
        assert "envelope_object_ref" in message
        assert "performed_authorization_ref" in message
    else:
        raise AssertionError("mismatched provider adapter import should fail")


def test_generation_artifact_ledger_builders_compact_provider_artifacts():
    envelope = _load_json(
        _ROOT
        / "examples/provider_artifact_staging/"
        "p1b_provider_artifact_staging.source_envelope.json"
    )
    staging = _load_json(
        _ROOT
        / "examples/provider_artifact_staging/"
        "p1b_provider_artifact_staging.example.json"
    )
    promotion = _load_json(
        _ROOT
        / "examples/provider_artifact_staging/"
        "p1b_provider_artifact_promotion_report.example.json"
    )

    envelope_compact = compact_provider_output_envelope(envelope)
    assert envelope_compact["envelope_id"] == "pout_performed_stage05_map_visual_001"
    assert envelope_compact["provider_call"]["performed"] is True
    assert envelope_compact["artifact_manifest"]["output_ref_count"] == 1
    assert envelope_compact["activation_gate"]["activation_allowed"] is False

    staging_compact = compact_provider_artifact_staging(staging)
    assert staging_compact["manifest_id"] == "pstaging_stage05_map_visual_001"
    assert staging_compact["staged_artifact_count"] == 1
    assert staging_compact["gate_statuses"]["schema_gate"] == "passed"
    assert staging_compact["promotion_gate"]["promotion_allowed"] is False

    promotion_compact = compact_provider_artifact_promotion_report(promotion)
    assert promotion_compact["report_id"] == "ppromo_stage05_map_visual_001"
    assert promotion_compact["promotion_decision"] == "blocked_review_required"
    assert promotion_compact["promotion_allowed"] is False
    assert promotion_compact["gate_statuses"]["media_gate"] == "not_run"
    assert promotion_compact["safety_summary"]["stores_sensitive_value"] is False


def test_generation_artifact_ledger_builders_keep_review_only_summary_contract():
    compact = {
        "provider_call": {"performed": True},
        "activation_gate": {"activation_allowed": False},
        "promotion_gate": {"promotion_allowed": False},
    }
    entry = build_artifact_ledger_payload(
        session_id="session_test",
        artifact_kind="provider_output_envelope",
        source_id="pout_test",
        status="recorded_review_only",
        compact=compact,
        ts="2026-07-03T00:00:00Z",
        latest_run={"run_id": "gsrun_test"},
        schedule_item_id="sched_test",
        worker_id="worker-test",
        note="ledger builder test",
    )

    assert entry["ledger_id"] == "gled_session_test_provider_output_envelope_pout_test"
    assert entry["provider_call_performed_by_this_request"] is False
    assert entry["world_mutation_performed_by_this_request"] is False
    assert entry["activation_allowed_now"] is False
    assert entry["ledger_write_policy"] == {
        "mode": "fixture_backed_review_only",
        "reads_env": False,
        "calls_provider": False,
        "stores_raw_prompt": False,
        "stores_provider_response": False,
        "writes_world_state": False,
    }

    ledger = compact_generation_artifact_ledger([entry])
    assert ledger["summary"]["item_count"] == 1
    assert ledger["summary"]["recorded_provider_call_count"] == 1
    assert ledger["summary"]["provider_call_count_by_this_request"] == 0
    assert ledger["summary"]["world_mutation_count_by_this_request"] == 0
    assert ledger["summary"]["promotion_allowed_count"] == 0


def test_generation_scheduler_run_queue_builders_keep_queue_contract():
    plan = {
        "plan_id": "plan_test",
        "authority": {"activation_requires_revalidation": True},
        "items": [
            {
                "schedule_item_id": "sched/demo visual",
                "object_kind": "map_visual",
                "object_ref": "map:demo",
                "latency_class": "background_prefetch",
                "status": "planned",
                "priority": 10,
                "provider_policy": {"max_attempts": 2},
                "player_visible": False,
                "fallback_ref": "fallback:map",
                "commit_policy": {
                    "world_commit": "none",
                    "revalidate_before_activation": True,
                },
            }
        ],
    }
    run_report = {
        "report_id": "report_test",
        "summary": {
            "scheduled_count": 1,
            "provider_call_count": 0,
            "world_mutation_count": 0,
        },
        "items": [
            {
                "schedule_item_id": "sched/demo visual",
                "action": "queue_provider_review",
                "result_status": "scheduled",
                "provider_review_required": True,
            }
        ],
    }

    buffer = build_generation_schedule_buffer(plan, run_report)
    assert buffer["status"] == "fixture_backed_scheduler_buffer_ready"
    assert buffer["provider_review_required_count"] == 1
    assert buffer["activation_requires_revalidation"] is True
    assert buffer["items"][0]["dry_run_status"] == "scheduled"

    run = build_generation_schedule_run_payload(
        "session_test",
        "gsrun_test",
        "2026-07-03T00:00:00Z",
        plan=plan,
        run_report=run_report,
        refs={"plan": "plan.json", "run_report": "report.json"},
    )
    queue_items = build_generation_queue_items_from_run(
        run,
        "2026-07-03T00:00:00Z",
    )

    assert len(queue_items) == 1
    assert queue_items[0]["queue_item_id"] == "gq_gsrun_test_01"
    assert queue_items[0]["status"] == "queued"
    assert queue_items[0]["max_attempts"] == 2
    assert queue_items[0]["provider_review_required"] is True
    assert compact_generation_queue(queue_items)["summary"]["claimable_count"] == 1


def test_generation_scheduler_worker_cache_builder_keeps_safety_contract():
    payload = {
        "run_id": "gsrun_test",
        "session_id": "session_test",
        "schedule_item_id": "sched/demo visual",
        "object_kind": "map_visual",
        "object_ref": "map:demo",
        "latency_class": "background_prefetch",
        "worker_id": "worker-test",
        "attempt_count": 1,
        "max_attempts": 2,
        "status": "waiting_review",
        "provider_review_required": True,
        "revalidate_before_activation": True,
    }

    cache_payload = build_worker_cache_payload(payload, "2026-07-03T00:00:00Z")

    assert cache_payload["cache_id"] == "gcache_gsrun_test_sched_demo_visual"
    assert safe_id_fragment("sched/demo visual") == "sched_demo_visual"
    assert cache_payload["provider_call_performed"] is False
    assert cache_payload["world_mutation_performed"] is False
    assert cache_payload["activation_allowed_now"] is False
    assert cache_payload["activation_gate"]["blocked_reason"] == (
        "review_required_before_activation"
    )
    assert cache_payload["safe_content_policy"] == {
        "reads_env": False,
        "calls_provider": False,
        "writes_world_state": False,
        "stores_raw_prompt": False,
        "stores_provider_response": False,
    }
    compact = compact_worker_cache([cache_payload])
    assert compact["summary"]["item_count"] == 1
    assert compact["summary"]["review_required_count"] == 1


def test_generation_dispatcher_controls_keep_metadata_contract():
    assert requested_max_items({}, default=2, maximum=8) == 2
    assert requested_max_items({"max_items": "3"}, default=2, maximum=8) == 3
    try:
        requested_max_items({"max_items": 9}, default=2, maximum=8)
    except ValueError as exc:
        assert "max_items must be between 1 and 8" in str(exc)
    else:
        raise AssertionError("oversized max_items should fail")

    targeted = {
        "schedule_item_id": "sched_test",
        "authorization_ref": "",
        "receipt_path": "/tmp/receipt.json",
        "note": "safe note",
    }
    assert targeted_metadata_keys(targeted) == [
        "schedule_item_id",
        "receipt_path",
    ]
    try:
        reject_targeted_metadata(targeted, action_label="review-only dispatcher drain")
    except ValueError as exc:
        message = str(exc)
        assert "review-only dispatcher drain does not accept targeted metadata" in message
        assert "schedule_item_id" in message
        assert "receipt_path" in message
    else:
        raise AssertionError("targeted metadata should fail")

    assert dispatcher_step_metadata(
        worker_prefix="worker",
        step_name="dry_run",
        note=None,
        schedule_item_id="sched_test",
        authorization_ref="auth_test",
    ) == {
        "worker_id": "worker_dry_run",
        "note": None,
        "schedule_item_id": "sched_test",
        "authorization_ref": "auth_test",
    }


def test_generation_prefetch_cache_builder_summarizes_queue_and_ledger_refs():
    latest_run = {
        "run_id": "gsrun_test",
        "session_id": "session_test",
        "status": "completed",
        "created_at": "2026-07-03T00:00:00Z",
        "updated_at": "2026-07-03T00:00:00Z",
        "generation_schedule": {},
        "source_report_summary": {},
    }
    queue_items = [
        {
            "schedule_item_id": "sched_ready",
            "object_kind": "map_visual",
            "object_ref": "map:test",
            "latency_class": "background_prefetch",
            "status": "waiting_review",
            "provider_review_required": True,
            "attempt_count": 1,
            "max_attempts": 2,
            "fallback_ref": "fallback:map",
            "revalidate_before_activation": True,
        },
        {
            "schedule_item_id": "sched_queued",
            "object_kind": "support_item",
            "object_ref": "item:test",
            "latency_class": "lazy",
            "status": "queued",
        },
    ]
    ledger_items = [
        {
            "ledger_id": "gled_envelope",
            "artifact_kind": "provider_output_envelope",
            "source_id": "pout_test",
            "status": "recorded_review_only",
            "updated_at": "2026-07-03T00:05:00Z",
            "schedule_item_id": "sched_ready",
            "compact": {
                "provider_call": {"performed": True},
                "activation_gate": {
                    "activation_allowed": False,
                    "blocked_reason": "promotion_required",
                    "required_next_gates": ["promotion_report"],
                },
            },
        },
        {
            "ledger_id": "gled_promotion",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_test",
            "status": "promotion_allowed",
            "updated_at": "2026-07-03T00:06:00Z",
            "schedule_item_id": "sched_ready",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
            },
        },
    ]

    payload = build_generation_prefetch_cache_payload(
        "session_test",
        latest_run,
        queue_items,
        ledger_items,
    )

    summary = payload["generation_prefetch_cache"]["summary"]
    assert summary["item_count"] == 2
    assert summary["cache_status_counts"] == {
        "promotion_allowed_pending_activation": 1,
        "queued": 1,
    }
    assert summary["recorded_provider_call_count"] == 1
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["promotion_allowed_count"] == 1
    items_by_id = {
        item["schedule_item_id"]: item
        for item in payload["generation_prefetch_cache"]["items"]
    }
    assert items_by_id["sched_ready"]["cache_status"] == (
        "promotion_allowed_pending_activation"
    )
    assert items_by_id["sched_ready"]["runtime_ready"] is False
    assert items_by_id["sched_ready"]["review_only"] is True
    assert items_by_id["sched_ready"]["promotion_gate"]["promotion_allowed"] is True
    assert items_by_id["sched_ready"]["activation_gate"]["blocked_reason"] == (
        "promotion_required"
    )
    assert items_by_id["sched_queued"]["cache_status"] == "queued"
    assert ledger_entry_ref(ledger_items[0])["compact"]["provider_call"][
        "performed"
    ] is True
    assert prefetch_cache_status(
        {"queue_status": "waiting_review"},
        {"provider_output_envelope": ledger_entry_ref(ledger_items[0])},
    ) == "review_only_envelope_ready"


def test_provider_artifact_fixture_catalog_resolves_default_profile():
    envelope_path, staging_path, promotion_path, normalized = (
        provider_artifact_fixture_paths("summary", repo_root=_ROOT)
    )

    assert normalized == "default"
    assert _rel(envelope_path) == (
        "examples/provider_artifact_staging/"
        "p1b_provider_artifact_staging.source_envelope.json"
    )
    assert _rel(staging_path) == (
        "examples/provider_artifact_staging/"
        "p1b_provider_artifact_staging.example.json"
    )
    assert _rel(promotion_path) == (
        "examples/provider_artifact_staging/"
        "p1b_provider_artifact_promotion_report.example.json"
    )

    metadata = provider_artifact_fixture_metadata(
        None,
        repo_root=_ROOT,
        load_json=_load_json,
        rel_path=_rel,
    )
    assert metadata == {
        "artifact_profile": "default",
        "schedule_item_id": "sched_next_map_visual_prefetch",
        "authorization_ref": "auth_sched_next_map_visual_prefetch_fixture_001",
        "provider_output_envelope": (
            "examples/provider_artifact_staging/"
            "p1b_provider_artifact_staging.source_envelope.json"
        ),
    }


def test_provider_artifact_fixture_catalog_resolves_image_failure_profile():
    envelope_path, staging_path, promotion_path, normalized = (
        provider_artifact_fixture_paths("image", repo_root=_ROOT)
    )

    assert normalized == "image_failure"
    assert _rel(envelope_path) == (
        "examples/provider_artifact_staging/"
        "p1b_provider_image_artifact_staging.source_envelope.json"
    )
    assert _rel(staging_path) == (
        "examples/provider_artifact_staging/"
        "p1b_provider_image_artifact_staging.example.json"
    )
    assert _rel(promotion_path) == (
        "examples/provider_artifact_staging/"
        "p1b_provider_image_artifact_promotion_report.example.json"
    )

    metadata = provider_artifact_fixture_metadata(
        "image_failure",
        repo_root=_ROOT,
        load_json=_load_json,
        rel_path=_rel,
    )
    assert metadata["artifact_profile"] == "image_failure"
    assert metadata["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert metadata["authorization_ref"] == (
        "auth_sched_next_map_visual_prefetch_image_fixture_001"
    )


def test_provider_artifact_fixture_catalog_rejects_unknown_profile():
    try:
        provider_artifact_fixture_paths("missing", repo_root=_ROOT)
    except ValueError as exc:
        assert "unknown provider artifact profile" in str(exc)
    else:
        raise AssertionError("unknown provider artifact profile should fail")


def test_provider_artifact_review_helpers_validate_cross_file_contract():
    staging = {
        "manifest_id": "pstaging_test",
        "staged_artifacts": [{"artifact_id": "artifact_test"}],
    }
    promotion = {
        "report_id": "ppromo_test",
        "source_staging_id": "pstaging_test",
        "reviewed_artifacts": [{"staged_artifact_id": "artifact_test"}],
        "decision": {"promotion_allowed": True},
    }

    contract = validate_provider_artifact_review_contract(staging, promotion)

    assert contract["staging_manifest_id"] == "pstaging_test"
    assert contract["promotion_report_id"] == "ppromo_test"
    assert contract["staged_artifact_ids"] == ["artifact_test"]
    assert contract["reviewed_staged_artifact_ids"] == ["artifact_test"]
    assert contract["promotion_allowed"] is True
    assert provider_artifact_promotion_allowed(promotion) is True


def test_provider_artifact_review_helpers_reject_unstaged_review_refs():
    staging = {
        "manifest_id": "pstaging_test",
        "staged_artifacts": [{"artifact_id": "artifact_test"}],
    }
    promotion = {
        "report_id": "ppromo_test",
        "source_staging_id": "pstaging_test",
        "reviewed_artifacts": [{"staged_artifact_id": "artifact_missing"}],
        "decision": {"promotion_allowed": False},
    }

    try:
        validate_provider_artifact_review_contract(staging, promotion)
    except ValueError as exc:
        assert "reviewed_artifacts must reference staged_artifacts" in str(exc)
        assert "artifact_missing" in str(exc)
    else:
        raise AssertionError("unstaged reviewed artifact ref should fail")


def test_provider_runner_handoff_outbox_builder_keeps_safe_contract():
    outbox = build_provider_adapter_runner_handoff_outbox(
        session_id="session_test",
        run_id="gsrun_test",
        worker_id="worker-test",
        max_items=2,
        dispatched_count=0,
        stop_reason="no_eligible_items",
        runner_handoffs=[],
        created_at="2026-07-03T00:00:00Z",
    )

    assert validate_provider_adapter_runner_handoff_outbox(outbox) == []
    assert outbox["safety"] == provider_runner_outbox_safety()
    assert outbox["handoff_mode"] == "external_runner_required"
    assert outbox["review_only"] is True
    assert outbox["runner_handoff_count"] == 0
    assert outbox["runner_handoffs"] == []
    assert outbox["import_contract"]["post_import_gate"] == (
        "provider_artifact_staging_or_promotion_review_required"
    )


def test_generation_import_path_allows_envelope_suffix(tmp_path):
    path = tmp_path / "candidate.envelope.json"
    path.write_text("{}", encoding="utf-8")

    resolved = resolve_import_path(
        str(path),
        label="envelope_path",
        repo_root=_ROOT,
    )

    assert resolved == path.resolve()


def test_generation_import_path_rejects_dotenv_path(tmp_path):
    path = tmp_path / ".env" / "candidate.json"
    path.parent.mkdir()
    path.write_text("{}", encoding="utf-8")

    try:
        resolve_import_path(str(path), label="receipt_path", repo_root=_ROOT)
    except ValueError as exc:
        assert "must not reference .env" in str(exc)
    else:
        raise AssertionError("expected .env import path to be rejected")


def _session_state_counts(raw_conn: sqlite3.Connection, sid: str) -> dict[str, int]:
    tables = [
        "generation_schedule_runs",
        "generation_schedule_queue_items",
        "generation_schedule_worker_cache",
        "generation_artifact_ledger",
        "provider_logs",
        "world_instance",
    ]
    return {
        table: raw_conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ?",
            (sid,),
        ).fetchone()[0]
        for table in tables
    }


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _prepare_provider_authorization_chain(
    client,
    sid: str,
    worker_prefix: str,
    authorization_ref: str | None = None,
) -> dict:
    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={
                "worker_id": f"{worker_prefix}-dry-worker",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/live-executor-guard",
            json={
                "worker_id": f"{worker_prefix}-live-guard",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    executor_request = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
            json={
                "worker_id": f"{worker_prefix}-executor-request",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )["generation_executor_run_request"]
    authorization = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/grant-provider-authorization",
            json={
                "worker_id": f"{worker_prefix}-provider-auth",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": authorization_ref,
            },
        )
    )["provider_execution_authorization"]
    return {
        "executor_request": executor_request,
        "authorization": authorization,
    }


def _prepare_provider_artifact_staging_chain(
    client,
    sid: str,
    worker_prefix: str,
    authorization_ref: str | None = None,
) -> dict:
    chain = _prepare_provider_authorization_chain(
        client,
        sid,
        worker_prefix,
        authorization_ref=authorization_ref,
    )
    adapter_receipt = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-provider-adapter-fixture",
            json={
                "worker_id": f"{worker_prefix}-provider-adapter",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": authorization_ref,
            },
        )
    )["provider_adapter_execution_receipt"]
    return {
        "executor_request": chain["executor_request"],
        "authorization": chain["authorization"],
        "adapter_receipt": adapter_receipt,
    }


def _write_runner_outputs(
    tmp_path,
    executor_request: dict,
    authorization: dict,
    *,
    with_artifact_output: bool = False,
) -> dict:
    receipt, envelope = build_dry_run_artifacts(
        executor_request,
        authorization,
        created_at="2026-07-03T00:00:00Z",
        note="test runner output import",
    )
    if with_artifact_output:
        artifact_path = (
            "examples/provider_artifact_staging/artifacts/"
            "p1b_stage05_map_visual_candidate.summary.json"
        )
        receipt["execution"]["status"] = "performed_redacted_live"
        receipt["execution"]["mode"] = "live_redacted_provider_call"
        receipt["execution"]["provider_call_performed_by_receipt_builder"] = True
        receipt["execution"]["finish_reason"] = "completed"
        receipt["execution"][
            "redacted_summary"
        ] = "Live-like local fixture produced a redacted review artifact."
        receipt["adapter_safety"]["reads_env"] = True
        receipt["adapter_safety"]["calls_provider"] = True
        envelope["provider_call"]["status"] = "performed_redacted"
        envelope["provider_call"]["performed"] = True
        envelope["provider_call"]["authorization_granted"] = True
        envelope["provider_call"]["authorization_ref"] = authorization[
            "authorization_ref"
        ]
        envelope["redacted_result_summary"][
            "status"
        ] = "candidate_ready_for_validation"
        envelope["redacted_result_summary"][
            "summary"
        ] = "A local review candidate summary was saved for staging validation."
        envelope["redacted_result_summary"]["result_kind"] = "json_candidate"
        envelope["redacted_result_summary"]["finish_reason"] = "completed"
        envelope["artifact_manifest"]["status"] = "review_only_artifacts_ready"
        envelope["artifact_manifest"]["output_refs"] = [
            {
                "artifact_id": "runner_imported_candidate_summary",
                "kind": "json_candidate",
                "path": artifact_path,
                "content_type": "application/json",
                "media_layer": "processed_media",
            }
        ]
        envelope["artifact_manifest"]["notes"] = [
            "Artifacts remain internal evidence and require staging, validation, review, and promotion."
        ]
        envelope["activation_gate"]["blocked_reason"] = "promotion_required"
    receipt_path = tmp_path / "runner.receipt.json"
    envelope_path = tmp_path / "runner.envelope.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    envelope_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "receipt": receipt,
        "envelope": envelope,
        "receipt_path": receipt_path,
        "envelope_path": envelope_path,
    }


def _write_artifact_review_outputs(
    tmp_path,
    envelope: dict,
    envelope_path: Path,
) -> dict:
    staged_artifact_path = (
        "examples/provider_artifact_staging/artifacts/"
        "p1b_stage05_map_visual_candidate.summary.json"
    )
    envelope_id = str(envelope["envelope_id"])
    staging = {
        "schema_version": "provider_artifact_staging_manifest.v0.1",
        "manifest_id": f"pstaging_import_{envelope_id}",
        "created_at": "2026-07-03T00:00:00Z",
        "source_envelope_ref": str(envelope_path),
        "source_envelope_id": envelope_id,
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "local_ref_required",
            "local_refs_only": True,
            "runtime_claim_policy": "forbidden_before_promotion",
        },
        "staging_status": "review_only_artifacts_staged",
        "staged_artifacts": [
            {
                "artifact_id": "imported_review_artifact_001",
                "source_artifact_id": "runner_imported_candidate_summary",
                "kind": "json_candidate",
                "path": staged_artifact_path,
                "content_type": "application/json",
                "media_layer": "staging_report",
                "role": "runner_import_review_summary",
                "review_status": "staged_for_review",
                "runtime_visible": False,
                "player_visible": False,
            }
        ],
        "validation_results": {
            "source_envelope_gate": {
                "status": "passed",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "local_ref_gate": {
                "status": "passed",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "schema_gate": {
                "status": "passed",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "media_gate": {
                "status": "not_run",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "semantic_gate": {
                "status": "not_run",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "human_review": {
                "status": "not_run",
                "required_before_promotion": True,
                "report_ref": None,
            },
        },
        "promotion_gate": {
            "promotion_allowed": False,
            "blocked_reason": "promotion_report_required",
            "required_next_gates": [
                "media_gate",
                "semantic_gate",
                "human_review",
                "promotion_report",
            ],
        },
    }
    staging_path = tmp_path / "artifact.staging.json"
    promotion = {
        "schema_version": "provider_artifact_promotion_report.v0.1",
        "report_id": f"ppromo_import_{envelope_id}",
        "created_at": "2026-07-03T00:00:00Z",
        "source_staging_ref": str(staging_path),
        "source_staging_id": staging["manifest_id"],
        "authority": {
            "visibility": "internal_evidence",
            "report_only": True,
            "direct_runtime_mutation_allowed": False,
            "direct_world_mutation_allowed": False,
            "player_visible": False,
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "local_ref_required",
        },
        "decision": {
            "promotion_decision": "blocked_review_required",
            "promotion_allowed": False,
            "blocked_reason": "media_semantic_and_human_review_not_complete",
            "required_next_actions": [
                "run_media_gate",
                "run_semantic_gate",
                "complete_human_review",
            ],
        },
        "reviewed_artifacts": [
            {
                "staged_artifact_id": "imported_review_artifact_001",
                "source_artifact_id": "runner_imported_candidate_summary",
                "kind": "json_candidate",
                "path": staged_artifact_path,
                "review_result": "blocked_pending_review",
            }
        ],
        "gate_results": {
            "source_staging_gate": {
                "status": "passed",
                "required_before_promotion": True,
                "report_ref": str(staging_path),
            },
            "local_ref_gate": {
                "status": "passed",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "media_gate": {
                "status": "not_run",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "semantic_gate": {
                "status": "not_run",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "human_review": {
                "status": "not_run",
                "required_before_promotion": True,
                "report_ref": None,
            },
            "simulation_gate": {
                "status": "not_applicable",
                "required_before_promotion": False,
                "report_ref": None,
            },
        },
        "promotion_targets": {
            "target_kind": "none",
            "runtime_package_refs": [],
            "world_transaction_refs": [],
            "published_media_refs": [],
        },
        "safety_summary": {
            "provider_call_count_by_report": 0,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "stores_secret": False,
            "uses_temporary_url": False,
        },
    }
    promotion_path = tmp_path / "artifact.promotion.json"
    staging_path.write_text(
        json.dumps(staging, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    promotion_path.write_text(
        json.dumps(promotion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "staging": staging,
        "promotion": promotion,
        "staging_path": staging_path,
        "promotion_path": promotion_path,
    }


def test_frontend_mock_pack_exposes_generated_media_and_animation_seeds(client):
    sid = _create_session(client)
    payload = _payload(client.get(f"/api/sessions/{sid}/frontend-mock-pack"))

    pack = payload["pack"]
    media_manifest = payload["media_manifest"]
    animation_seed_manifest = payload["animation_seed_manifest"]
    runtime_art_kit = payload["runtime_art_kit"]
    runtime_art_media_manifest = payload["runtime_art_media_manifest"]
    core_artifacts = payload["ai_compile_core_artifacts"]

    assert pack["schema_version"] == "frontend_mock_pack.v0.1"
    assert len(pack["assets"]) == 11
    assert media_manifest["summary"]["generated_count"] == 22
    assert media_manifest["summary"]["processed_count"] == 22
    assert animation_seed_manifest["summary"]["media_count"] == 22
    assert runtime_art_kit["mode"] == "developer_compiled_runtime_art"
    assert len(runtime_art_kit["coverage"]["enemy_archetypes"]) == 3
    assert len(runtime_art_kit["procedural_effects"]) == 5
    assert runtime_art_media_manifest["summary"]["media_count"] == 18
    assert core_artifacts["context_package"]["schema_version"] == "context_package.v0.1"
    assert core_artifacts["fact_entry"]["schema_version"] == "fact_entry.v0.1"
    assert core_artifacts["compiled_game_object_package"]["schema_version"] == (
        "compiled_game_object_package.v0.1"
    )
    assert core_artifacts["world_delta_transaction"]["schema_version"] == (
        "world_state_delta_transaction.v0.1"
    )
    assert core_artifacts["refs"]["context_package"].endswith(
        "mvp_first_battle.context_package.json"
    )
    assert core_artifacts["refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    pack_core_artifacts = pack["core_artifacts"]
    assert pack_core_artifacts["status"] == (
        "frontend_pack_review_only_core_artifacts_ready"
    )
    assert pack_core_artifacts["review_only"] is True
    assert pack_core_artifacts["refs"] == core_artifacts["refs"]
    assert pack_core_artifacts["context_package"]["schema_version"] == (
        "context_package.v0.1"
    )
    assert pack_core_artifacts["fact_entry"]["schema_version"] == "fact_entry.v0.1"
    assert pack_core_artifacts["compiled_game_object_package"]["schema_version"] == (
        "compiled_game_object_package.v0.1"
    )
    assert payload["animation_pipeline_status"] == (
        "multiframe_atlas_ready_video_keyframes_not_generated"
    )
    assert payload["runtime_art_pipeline_status"] == (
        "developer_compiled_multiframe_atlas_ready_video_keyframes_not_generated"
    )

    first_icon = pack["assets"][0]["media_refs"]["generated_roles"]["icon"]["url"]
    media_resp = client.get(first_icon)
    assert media_resp.status_code == 200
    assert media_resp.headers["content-type"] == "image/png"

    runtime_icon = runtime_art_media_manifest["items"][0]["url"]
    runtime_media_resp = client.get(runtime_icon)
    assert runtime_media_resp.status_code == 200
    assert runtime_media_resp.headers["content-type"] == "image/png"


def test_world_instance_opening_map_and_briefing_flow(client, raw_conn: sqlite3.Connection):
    sid = _create_session(client)

    created = _payload(
        client.post(
            f"/api/sessions/{sid}/world-instance",
            json={"selected_options": {"creativity_mode": "experimental"}},
        )
    )
    assert created["world_instance"]["selected_options"]["creativity_mode"] == "experimental"
    assert created["run_world_state"]["progress"]["phase"] == "first_defense"

    world_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM world_instance WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    state_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM campaign_state WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    assert world_rows == 1
    assert state_rows == 1

    opening = _payload(client.get(f"/api/sessions/{sid}/opening"))
    assert opening["opening"]

    animation = _payload(client.get(f"/api/sessions/{sid}/animation-seeds"))
    assert animation["animation_seed_manifest"]["summary"]["media_count"] == 22

    runtime_art = _payload(client.get(f"/api/sessions/{sid}/runtime-art-kit"))
    assert runtime_art["runtime_art_kit"]["schema_version"] == (
        "frontend_battle_mock_art_kit.v0.1"
    )
    assert runtime_art["runtime_art_media_manifest"]["summary"]["asset_count"] == 9

    schedule = _payload(client.get(f"/api/sessions/{sid}/generation-schedule"))
    generation_schedule = schedule["generation_schedule"]
    buffer = generation_schedule["buffer"]
    assert generation_schedule["plan"]["schema_version"] == "generation_schedule_plan.v0.1"
    assert generation_schedule["run_report"]["schema_version"] == (
        "generation_schedule_run_report.v0.1"
    )
    assert generation_schedule["refs"]["plan"].endswith(
        "mvp_generation_schedule_plan.v0.1.json"
    )
    assert buffer["status"] == "fixture_backed_scheduler_buffer_ready"
    assert buffer["control_plane_mode"] == "review_only_dry_run"
    assert buffer["provider_call_count"] == 0
    assert buffer["world_mutation_count"] == 0
    assert buffer["latency_class_counts"]["sync_blocking"] == 3
    assert buffer["latency_class_counts"]["background_prefetch"] == 2
    assert buffer["fallback_selected_count"] == 1
    assert buffer["scheduled_count"] == 4
    assert buffer["activation_requires_revalidation"] is True
    assert {item["latency_class"] for item in buffer["items"]} >= {
        "sync_blocking",
        "background_prefetch",
        "background",
        "lazy",
        "fallback_static",
    }
    assert schedule["latest_generation_schedule_run"] is None

    schedule_run = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run = schedule_run["generation_schedule_run"]
    queue = schedule_run["generation_schedule_queue"]
    assert run["status"] == "completed"
    assert run["scheduler_mode"] == "fixture_backed_dry_run"
    assert run["generation_schedule"]["buffer"]["provider_call_count"] == 0
    assert run["generation_schedule"]["buffer"]["world_mutation_count"] == 0
    assert run["source_report_summary"]["scheduled_count"] == 4
    assert queue["summary"]["item_count"] == 8
    assert queue["summary"]["status_counts"] == {
        "completed": 3,
        "fallback_ready": 1,
        "queued": 4,
    }
    assert queue["summary"]["claimable_count"] == 4
    assert queue["summary"]["provider_review_required_count"] == 4
    schedule_run_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_runs WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    assert schedule_run_rows == 1
    queue_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_queue_items WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    assert queue_rows == 8

    latest_schedule_run = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/runs/latest")
    )
    assert latest_schedule_run["generation_schedule_run"]["run_id"] == run["run_id"]
    assert latest_schedule_run["generation_schedule_queue"]["summary"]["item_count"] == 8

    latest_queue = _payload(client.get(f"/api/sessions/{sid}/generation-schedule/queue"))
    assert latest_queue["generation_schedule_run"]["run_id"] == run["run_id"]
    assert latest_queue["generation_schedule_queue"]["summary"]["status_counts"]["queued"] == 4
    assert latest_queue["generation_schedule_worker_cache_summary"]["item_count"] == 0
    assert {
        item["latency_class"] for item in latest_queue["generation_schedule_queue"]["items"]
    } >= {"background_prefetch", "background", "lazy"}

    initial_worker_cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/worker-cache")
    )
    assert initial_worker_cache["generation_schedule_run"]["run_id"] == run["run_id"]
    assert initial_worker_cache["generation_schedule_worker_cache"]["summary"][
        "item_count"
    ] == 0

    worker_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={
                "worker_id": "dry-worker-test",
                "note": "dry worker smoke test",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    assert worker_step["worker_step"]["status"] == "processed"
    assert worker_step["worker_step"]["provider_call_count"] == 0
    assert worker_step["worker_step"]["world_mutation_count"] == 0
    assert worker_step["generation_schedule_queue_item"]["status"] == "waiting_review"
    assert worker_step["generation_schedule_queue_item"]["worker_id"] == "dry-worker-test"
    assert worker_step["generation_schedule_queue"]["summary"]["waiting_review_count"] == 1
    assert worker_step["generation_schedule_queue"]["summary"]["claimable_count"] == 3
    worker_cache = worker_step["generation_schedule_worker_cache"]
    assert worker_cache["summary"]["item_count"] == 1
    assert worker_cache["summary"]["provider_call_count"] == 0
    assert worker_cache["summary"]["world_mutation_count"] == 0
    assert worker_cache["summary"]["activation_allowed_count"] == 0
    assert worker_cache["summary"]["review_required_count"] == 1
    cache_item = worker_cache["items"][0]
    assert cache_item["schedule_item_id"] == (
        worker_step["generation_schedule_queue_item"]["schedule_item_id"]
    )
    assert cache_item["worker_id"] == "dry-worker-test"
    assert cache_item["status"] == "waiting_review"
    assert cache_item["artifact_placeholder"]["status"] == "review_only_placeholder"
    assert cache_item["artifact_placeholder"]["provider_call_performed"] is False
    assert cache_item["artifact_placeholder"]["world_mutation_performed"] is False
    assert cache_item["artifact_placeholder"]["activation_allowed_now"] is False
    assert cache_item["activation_gate"]["blocked_reason"] == (
        "review_required_before_activation"
    )

    latest_worker_cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/worker-cache")
    )
    assert latest_worker_cache["generation_schedule_worker_cache"]["summary"][
        "item_count"
    ] == 1
    worker_cache_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_worker_cache WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert worker_cache_rows == 1

    pre_guard_executor_request = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
        json={
            "worker_id": "too-early",
            "note": "guard missing",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )
    assert pre_guard_executor_request.status_code == 409

    live_guard = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/live-executor-guard",
            json={
                "worker_id": "live-guard-test",
                "note": "guard before provider",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    assert live_guard["worker_step"]["status"] == "blocked"
    assert live_guard["worker_step"]["provider_call_count"] == 0
    assert live_guard["worker_step"]["world_mutation_count"] == 0
    assert live_guard["live_executor_guard"]["status"] == (
        "blocked_pending_explicit_authorization"
    )
    assert live_guard["live_executor_guard"]["worker_id"] == "live-guard-test"
    assert live_guard["live_executor_guard"]["authorization"]["required"] is True
    assert live_guard["live_executor_guard"]["authorization"]["granted"] is False
    assert live_guard["live_executor_guard"]["provider_call_performed"] is False
    assert live_guard["live_executor_guard"]["world_mutation_performed"] is False
    assert live_guard["live_executor_guard"]["activation_allowed_now"] is False
    assert live_guard["live_executor_guard"]["raw_prompt_stored"] is False
    assert live_guard["live_executor_guard"]["provider_response_stored"] is False
    assert live_guard["provider_guard_logs"]["summary"]["item_count"] == 1
    assert live_guard["provider_guard_logs"]["summary"]["provider_call_count"] == 0
    guarded_cache_item = live_guard["generation_schedule_worker_cache"]["items"][0]
    assert guarded_cache_item["executor_guard"]["status"] == (
        "blocked_pending_explicit_authorization"
    )
    assert guarded_cache_item["activation_gate"]["blocked_reason"] == (
        "explicit_provider_authorization_required"
    )
    provider_log_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM provider_logs WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert provider_log_rows == 1

    executor_request_response = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
            json={
                "worker_id": "executor-request-test",
                "note": "prepare only",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    assert executor_request_response["worker_step"]["status"] == "prepared"
    assert executor_request_response["worker_step"]["provider_call_count"] == 0
    assert executor_request_response["worker_step"]["world_mutation_count"] == 0
    executor_request = executor_request_response["generation_executor_run_request"]
    assert executor_request["schema_version"] == "generation_executor_run_request.v0.1"
    assert executor_request["source"]["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert executor_request["source"]["guard_id"] == live_guard["live_executor_guard"][
        "guard_id"
    ]
    assert executor_request["source"]["worker_id"] == "executor-request-test"
    assert executor_request["authority"]["review_only"] is True
    assert executor_request["authority"]["provider_call_allowed_by_request_builder"] is False
    assert executor_request["authority"]["runtime_activation_allowed"] is False
    assert executor_request["authority"]["world_mutation_allowed"] is False
    assert executor_request["authority"]["player_visible"] is False
    assert executor_request["provider_execution_intent"]["authorization_required"] is True
    assert executor_request["provider_execution_intent"]["authorization_granted"] is False
    assert executor_request["provider_execution_intent"][
        "provider_call_performed_by_request_builder"
    ] is False
    assert executor_request["request_builder_safety"]["reads_env"] is False
    assert executor_request["request_builder_safety"]["calls_provider"] is False
    assert executor_request["request_builder_safety"]["writes_world_state"] is False
    assert executor_request["request_builder_safety"]["activates_runtime"] is False
    assert "explicit_user_authorization" in executor_request["required_gates"][
        "before_provider_execution"
    ]
    assert "provider_output_envelope" in executor_request["required_gates"][
        "after_provider_execution"
    ]
    assert "promotion_report" in executor_request["required_gates"]["before_activation"]
    request_ledger = executor_request_response["generation_artifact_ledger"]
    assert request_ledger["summary"]["item_count"] == 1
    assert request_ledger["summary"]["artifact_kind_counts"][
        "generation_executor_run_request"
    ] == 1
    assert request_ledger["summary"]["provider_call_count_by_this_request"] == 0
    assert request_ledger["summary"]["world_mutation_count_by_this_request"] == 0
    request_ledger_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_artifact_ledger WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert request_ledger_rows == 1

    pre_authorization_stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={"worker_id": "artifact-ledger-test", "note": "missing authorization"},
    )
    assert pre_authorization_stage.status_code == 409
    assert "matching provider execution authorization" in pre_authorization_stage.json()[
        "detail"
    ]

    provider_authorization = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/grant-provider-authorization",
            json={
                "worker_id": "provider-auth-test",
                "note": "authorize provider fixture",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    authorization_ref = "auth_sched_next_map_visual_prefetch_fixture_001"
    assert provider_authorization["worker_step"]["status"] == "authorized"
    assert provider_authorization["worker_step"]["provider_call_count"] == 0
    assert provider_authorization["worker_step"]["world_mutation_count"] == 0
    assert provider_authorization["worker_step"]["activation_allowed_count"] == 0
    assert provider_authorization["worker_step"]["authorization_ref"] == authorization_ref
    assert provider_authorization["worker_step"]["upstream_request_id"] == (
        executor_request["request_id"]
    )
    authorization_record = provider_authorization["provider_execution_authorization"]
    assert authorization_record["schema_version"] == (
        "provider_execution_authorization.v0.1"
    )
    assert authorization_record["authorization_ref"] == authorization_ref
    assert authorization_record["source"]["schedule_item_id"] == (
        "sched_next_map_visual_prefetch"
    )
    assert authorization_record["source"]["executor_request_id"] == (
        executor_request["request_id"]
    )
    assert authorization_record["authorization"]["granted"] is True
    assert authorization_record["authorization"]["scope"] == (
        "provider_adapter_execution_only"
    )
    assert authorization_record["authority"]["provider_execution_authorized"] is True
    assert authorization_record["authority"]["runtime_activation_allowed"] is False
    assert authorization_record["authority"]["world_mutation_allowed"] is False
    assert authorization_record["authorization_builder_safety"]["calls_provider"] is False
    assert authorization_record["authorization_builder_safety"][
        "writes_world_state"
    ] is False
    assert authorization_record["authorization_builder_safety"][
        "activates_runtime"
    ] is False
    authorization_ledger = provider_authorization["generation_artifact_ledger"]
    assert authorization_ledger["summary"]["item_count"] == 2
    assert authorization_ledger["summary"]["artifact_kind_counts"][
        "generation_executor_run_request"
    ] == 1
    assert authorization_ledger["summary"]["artifact_kind_counts"][
        "provider_execution_authorization"
    ] == 1
    authorization_ledger_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_artifact_ledger WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert authorization_ledger_rows == 2

    pre_adapter_stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={"worker_id": "artifact-ledger-test", "note": "missing adapter receipt"},
    )
    assert pre_adapter_stage.status_code == 409
    assert "matching provider adapter execution receipt" in pre_adapter_stage.json()[
        "detail"
    ]

    adapter_receipt_response = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-provider-adapter-fixture",
            json={
                "worker_id": "provider-adapter-test",
                "note": "record provider adapter fixture boundary",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    assert adapter_receipt_response["worker_step"]["status"] == "adapter_recorded"
    assert adapter_receipt_response["worker_step"]["provider_call_count"] == 0
    assert adapter_receipt_response["worker_step"]["world_mutation_count"] == 0
    assert adapter_receipt_response["worker_step"]["activation_allowed_count"] == 0
    assert adapter_receipt_response["worker_step"]["authorization_ref"] == authorization_ref
    assert adapter_receipt_response["worker_step"]["upstream_request_id"] == (
        executor_request["request_id"]
    )
    adapter_receipt = adapter_receipt_response["provider_adapter_execution_receipt"]
    assert adapter_receipt["schema_version"] == (
        "provider_adapter_execution_receipt.v0.1"
    )
    assert adapter_receipt["source"]["schedule_item_id"] == (
        "sched_next_map_visual_prefetch"
    )
    assert adapter_receipt["source"]["authorization_ref"] == authorization_ref
    assert adapter_receipt["source"]["executor_request_id"] == (
        executor_request["request_id"]
    )
    assert adapter_receipt["authority"]["provider_adapter_boundary_entered"] is True
    assert adapter_receipt["authority"]["runtime_activation_allowed"] is False
    assert adapter_receipt["authority"]["world_mutation_allowed"] is False
    assert adapter_receipt["execution"]["mode"] == "fixture_backed_no_provider_call"
    assert adapter_receipt["execution"][
        "provider_call_performed_by_receipt_builder"
    ] is False
    assert adapter_receipt["execution"]["requires_provider_output_envelope"] is True
    assert adapter_receipt["adapter_safety"]["reads_env"] is False
    assert adapter_receipt["adapter_safety"]["calls_provider"] is False
    adapter_ledger = adapter_receipt_response["generation_artifact_ledger"]
    assert adapter_ledger["summary"]["item_count"] == 3
    assert adapter_ledger["summary"]["artifact_kind_counts"][
        "provider_adapter_execution_receipt"
    ] == 1
    adapter_ledger_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_artifact_ledger WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert adapter_ledger_rows == 3

    artifact_stage = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
            json={"worker_id": "artifact-ledger-test", "note": "record safe refs"},
        )
    )
    assert artifact_stage["worker_step"]["status"] == "staged"
    assert artifact_stage["worker_step"]["provider_call_count"] == 0
    assert artifact_stage["worker_step"]["world_mutation_count"] == 0
    assert artifact_stage["worker_step"]["activation_allowed_count"] == 0
    assert artifact_stage["worker_step"]["upstream_request_id"] == (
        executor_request["request_id"]
    )
    assert artifact_stage["worker_step"]["authorization_ref"] == authorization_ref
    assert artifact_stage["generation_executor_run_request"]["request_id"] == (
        executor_request["request_id"]
    )
    assert artifact_stage["provider_execution_authorization"]["authorization_ref"] == (
        authorization_ref
    )
    assert artifact_stage["provider_execution_authorization"]["authorization"][
        "granted"
    ] is True
    assert artifact_stage["provider_adapter_execution_receipt"][
        "execution_receipt_id"
    ] == adapter_receipt["execution_receipt_id"]
    assert artifact_stage["provider_adapter_execution_receipt"]["execution"][
        "authorization_ref"
    ] == authorization_ref
    assert artifact_stage["provider_output_envelope"]["envelope_id"] == (
        "pout_performed_stage05_map_visual_001"
    )
    assert artifact_stage["provider_output_envelope"]["source"]["schedule_item_id"] == (
        "sched_next_map_visual_prefetch"
    )
    assert artifact_stage["provider_output_envelope"]["provider_call"]["performed"] is True
    assert artifact_stage["provider_output_envelope"]["provider_call"][
        "authorization_ref"
    ] == authorization_ref
    assert artifact_stage["provider_artifact_staging"]["manifest_id"] == (
        "pstaging_stage05_map_visual_001"
    )
    assert artifact_stage["provider_artifact_staging"]["promotion_gate"][
        "promotion_allowed"
    ] is False
    assert artifact_stage["provider_artifact_promotion_report"]["report_id"] == (
        "ppromo_stage05_map_visual_001"
    )
    assert artifact_stage["provider_artifact_promotion_report"][
        "promotion_decision"
    ] == "blocked_review_required"
    assert artifact_stage["provider_artifact_promotion_report"][
        "promotion_allowed"
    ] is False
    ledger_summary = artifact_stage["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 6
    assert ledger_summary["artifact_kind_counts"]["generation_executor_run_request"] == 1
    assert ledger_summary["artifact_kind_counts"]["provider_execution_authorization"] == 1
    assert ledger_summary["artifact_kind_counts"]["provider_adapter_execution_receipt"] == 1
    assert ledger_summary["artifact_kind_counts"]["provider_output_envelope"] == 1
    assert ledger_summary["artifact_kind_counts"]["provider_artifact_staging_manifest"] == 1
    assert ledger_summary["artifact_kind_counts"]["provider_artifact_promotion_report"] == 1
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0

    ledger = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/artifact-ledger")
    )
    assert ledger["generation_artifact_ledger"]["summary"]["item_count"] == 6
    assert len(ledger["generation_artifact_ledger"]["items"]) == 6
    assert {
        item["artifact_kind"] for item in ledger["generation_artifact_ledger"]["items"]
    } == {
        "generation_executor_run_request",
        "provider_execution_authorization",
        "provider_adapter_execution_receipt",
        "provider_output_envelope",
        "provider_artifact_staging_manifest",
        "provider_artifact_promotion_report",
    }
    ledger_rows = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_artifact_ledger WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert ledger_rows == 6

    reviewed_item_id = worker_step["generation_schedule_queue_item"]["schedule_item_id"]
    reviewed_complete = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{reviewed_item_id}/complete",
            json={"worker_id": "review-gate", "note": "manual review accepted"},
        )
    )
    assert reviewed_complete["generation_schedule_queue_item"]["status"] == "completed"
    assert (
        reviewed_complete["generation_schedule_queue"]["summary"]["waiting_review_count"] == 0
    )
    assert reviewed_complete["generation_schedule_queue"]["summary"]["status_counts"][
        "completed"
    ] == 4

    queued_item_id = next(
        item["schedule_item_id"]
        for item in reviewed_complete["generation_schedule_queue"]["items"]
        if item["status"] == "queued"
    )
    claimed = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{queued_item_id}/claim",
            json={"worker_id": "test-worker", "note": "claim for smoke test"},
        )
    )
    assert claimed["generation_schedule_queue_item"]["status"] == "claimed"
    assert claimed["generation_schedule_queue_item"]["claimed_by"] == "test-worker"
    assert claimed["generation_schedule_queue"]["summary"]["status_counts"]["claimed"] == 1
    assert claimed["generation_schedule_queue"]["summary"]["claimable_count"] == 2

    completed = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{queued_item_id}/complete",
            json={"worker_id": "test-worker", "note": "complete for smoke test"},
        )
    )
    assert completed["generation_schedule_queue_item"]["status"] == "completed"
    assert completed["generation_schedule_queue"]["summary"]["status_counts"]["completed"] == 5
    assert completed["generation_schedule_queue"]["summary"]["claimable_count"] == 2

    completed_sync_item_id = next(
        item["schedule_item_id"]
        for item in completed["generation_schedule_queue"]["items"]
        if item["dry_run_status"] == "passed"
    )
    conflict = client.post(
        f"/api/sessions/{sid}/generation-schedule/queue/{completed_sync_item_id}/claim"
    )
    assert conflict.status_code == 409
    assert "cannot claim" in conflict.json()["detail"]

    schedule_after_run = _payload(client.get(f"/api/sessions/{sid}/generation-schedule"))
    assert schedule_after_run["latest_generation_schedule_run"]["run_id"] == run["run_id"]

    map_payload = _payload(client.get(f"/api/sessions/{sid}/map"))
    assert map_payload["map"]["display_name"] == "余灯中枢态势图"
    assert map_payload["run_world_state"]["progress"]["phase"] == "first_defense"

    briefing = _payload(
        client.get(f"/api/sessions/{sid}/nodes/gray_lantern_station/briefing")
    )
    assert briefing["briefing"]["node_id"] == "gray_lantern_station"
    assert briefing["suggested_input"]

    reset = client.post(f"/api/sessions/{sid}/reset")
    assert reset.status_code == 200, reset.text
    worker_cache_rows_after_reset = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_schedule_worker_cache WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert worker_cache_rows_after_reset == 0
    provider_log_rows_after_reset = raw_conn.execute(
        "SELECT COUNT(*) FROM provider_logs WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert provider_log_rows_after_reset == 0
    ledger_rows_after_reset = raw_conn.execute(
        "SELECT COUNT(*) FROM generation_artifact_ledger WHERE session_id = ?",
        (sid,),
    ).fetchone()[0]
    assert ledger_rows_after_reset == 0


def test_provider_artifact_staging_requires_matching_executor_request(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    first_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={"worker_id": "wrong-item-worker"},
        )
    )
    assert first_step["generation_schedule_queue_item"]["schedule_item_id"] == (
        "sched_stage05_worldline_prefetch"
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/live-executor-guard",
            json={"worker_id": "wrong-item-guard"},
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
            json={"worker_id": "wrong-item-request"},
        )
    )
    stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={"worker_id": "must-not-stage"},
    )
    assert stage.status_code == 409
    assert "matching generation executor request" in stage.json()["detail"]


def test_provider_adapter_runner_fixture_records_receipt_and_envelope(client):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(client, sid, "runner-bridge")
    runner = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-provider-adapter-runner-fixture",
            json={
                "worker_id": "runner-bridge",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": chain["authorization"]["authorization_ref"],
                "note": "record runner dry-run output",
            },
        )
    )

    worker_step = runner["worker_step"]
    assert worker_step["status"] == "runner_recorded"
    assert worker_step["worker_mode"] == "provider_adapter_runner_fixture"
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["authorization_ref"] == chain["authorization"]["authorization_ref"]
    assert worker_step["upstream_request_id"] == chain["executor_request"]["request_id"]
    assert runner["provider_adapter_execution_receipt"]["execution_receipt_id"] == (
        worker_step["execution_receipt_id"]
    )
    assert runner["provider_adapter_execution_receipt"]["execution"]["mode"] == (
        "fixture_backed_no_provider_call"
    )
    assert runner["provider_adapter_execution_receipt"]["execution"][
        "provider_call_performed_by_receipt_builder"
    ] is False
    assert runner["provider_output_envelope"]["envelope_id"] == worker_step["envelope_id"]
    assert runner["provider_output_envelope"]["provider_call"]["performed"] is False
    assert runner["provider_output_envelope"]["provider_call"]["authorization_ref"] is None
    assert runner["provider_output_envelope"]["activation_gate"][
        "activation_allowed"
    ] is False
    assert runner["provider_output_envelope"]["artifact_manifest"]["status"] == (
        "not_created"
    )

    ledger_summary = runner["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 4
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 1,
        "provider_execution_authorization": 1,
        "provider_adapter_execution_receipt": 1,
        "provider_output_envelope": 1,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0


def test_provider_adapter_runner_handoff_exports_read_only_bundle(
    client,
    raw_conn,
):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(client, sid, "runner-handoff")
    before_counts = _session_state_counts(raw_conn, sid)

    handoff = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/export-provider-adapter-runner-handoff",
            json={
                "worker_id": "runner-handoff",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": chain["authorization"]["authorization_ref"],
                "note": "export external runner handoff",
            },
        )
    )

    assert _session_state_counts(raw_conn, sid) == before_counts
    worker_step = handoff["worker_step"]
    assert worker_step["status"] == "handoff_exported"
    assert worker_step["worker_mode"] == "provider_adapter_runner_handoff_export"
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["authorization_ref"] == chain["authorization"]["authorization_ref"]
    assert worker_step["upstream_request_id"] == chain["executor_request"]["request_id"]

    bundle = handoff["provider_adapter_runner_handoff"]
    assert bundle["schema_version"] == "provider_adapter_runner_handoff.v0.1"
    assert bundle["handoff_mode"] == "external_runner_required"
    assert bundle["review_only"] is True
    assert bundle["runner_inputs"]["executor_request"]["request_id"] == (
        chain["executor_request"]["request_id"]
    )
    assert bundle["runner_inputs"]["provider_execution_authorization"][
        "authorization_ref"
    ] == chain["authorization"]["authorization_ref"]
    assert bundle["suggested_paths"]["executor_request_path"].startswith("/tmp/")
    assert bundle["suggested_paths"]["authorization_path"].startswith("/tmp/")
    assert bundle["command_templates"]["dry_run_fixture"][:2] == [
        "python3",
        "tools/provider_adapter/run_provider_adapter.py",
    ]
    assert "--mode" in bundle["command_templates"]["dry_run_fixture"]
    assert "fixture" in bundle["command_templates"]["dry_run_fixture"]
    assert bundle["command_templates"]["video_boundary"][:2] == [
        "python3",
        "tools/provider_adapter/run_provider_adapter.py",
    ]
    assert "--mode" in bundle["command_templates"]["video_boundary"]
    assert "video" in bundle["command_templates"]["video_boundary"]
    assert "--live" not in bundle["command_templates"]["video_boundary"]
    assert (
        "<authorized-dotenv-path>"
        not in bundle["command_templates"]["video_boundary"]
    )
    assert "--live" in bundle["command_templates"]["live_llm_text"]
    assert "--live" in bundle["command_templates"]["live_image"]
    assert "<authorized-dotenv-path>" in bundle["command_templates"]["live_llm_text"]
    assert "<authorized-dotenv-path>" in bundle["command_templates"]["live_image"]
    assert bundle["import_after_runner"]["body"] == {
        "worker_id": "provider-runner-output-import",
        "schedule_item_id": "sched_next_map_visual_prefetch",
        "authorization_ref": chain["authorization"]["authorization_ref"],
        "receipt_path": bundle["suggested_paths"]["receipt_output_path"],
        "envelope_path": bundle["suggested_paths"]["envelope_output_path"],
    }
    assert bundle["safety"] == {
        "api_reads_env": False,
        "api_calls_provider": False,
        "api_writes_world_state": False,
        "api_activates_runtime": False,
        "prompt_body_included": False,
        "provider_response_body_included": False,
        "live_templates_require_external_explicit_authorization": True,
    }
    forbidden_keys = {"raw_prompt", "provider_response", "provider_body", "api_key", "secret"}
    assert not (set(_walk_keys(bundle)) & forbidden_keys)

    ledger_summary = handoff["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 2
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 1,
        "provider_execution_authorization": 1,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0


def test_provider_adapter_runner_handoff_roundtrip_import_updates_prefetch_cache(
    client,
    raw_conn,
    tmp_path,
):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(client, sid, "runner-handoff-roundtrip")
    handoff = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/export-provider-adapter-runner-handoff",
            json={
                "worker_id": "runner-handoff-roundtrip",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": chain["authorization"]["authorization_ref"],
            },
        )
    )["provider_adapter_runner_handoff"]
    receipt, envelope = build_dry_run_artifacts(
        handoff["runner_inputs"]["executor_request"],
        handoff["runner_inputs"]["provider_execution_authorization"],
        created_at="2026-07-03T00:00:00Z",
        note="handoff roundtrip fixture",
    )
    suggested = handoff["suggested_paths"]
    receipt_path = tmp_path / Path(suggested["receipt_output_path"]).name
    envelope_path = tmp_path / Path(suggested["envelope_output_path"]).name
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    envelope_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    before_counts = _session_state_counts(raw_conn, sid)
    import_body = dict(handoff["import_after_runner"]["body"])
    import_body["receipt_path"] = str(receipt_path)
    import_body["envelope_path"] = str(envelope_path)
    imported = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/import-provider-adapter-runner-output",
            json=import_body,
        )
    )

    after_counts = _session_state_counts(raw_conn, sid)
    assert after_counts["generation_artifact_ledger"] == (
        before_counts["generation_artifact_ledger"] + 2
    )
    for table in (
        "generation_schedule_runs",
        "generation_schedule_queue_items",
        "generation_schedule_worker_cache",
        "provider_logs",
        "world_instance",
    ):
        assert after_counts[table] == before_counts[table]
    worker_step = imported["worker_step"]
    assert worker_step["status"] == "imported"
    assert worker_step["worker_mode"] == "provider_adapter_runner_output_import"
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["authorization_ref"] == chain["authorization"]["authorization_ref"]
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert imported["provider_adapter_execution_receipt"]["execution"]["mode"] == (
        "fixture_backed_no_provider_call"
    )
    assert imported["provider_output_envelope"]["provider_call"]["performed"] is False

    prefetch_cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/prefetch-cache")
    )
    cache_items = {
        item["schedule_item_id"]: item
        for item in prefetch_cache["generation_prefetch_cache"]["items"]
    }
    cache_item = cache_items["sched_next_map_visual_prefetch"]
    assert cache_item["queue_status"] == "waiting_review"
    assert cache_item["cache_status"] == "review_only_envelope_ready"
    assert cache_item["refs"]["generation_executor_run_request"] is not None
    assert cache_item["refs"]["provider_execution_authorization"] is not None
    assert cache_item["refs"]["provider_adapter_execution_receipt"] is not None
    assert cache_item["refs"]["provider_output_envelope"] is not None
    assert cache_item["refs"]["provider_artifact_staging_manifest"] is None
    assert cache_item["refs"]["provider_artifact_promotion_report"] is None
    assert cache_item["provider_call_count_by_this_request"] == 0
    assert cache_item["world_mutation_count_by_this_request"] == 0
    assert cache_item["activation_gate"]["activation_allowed"] is False
    summary = prefetch_cache["generation_prefetch_cache"]["summary"]
    assert summary["review_only_envelope_ready_count"] == 1
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["activation_allowed_count"] == 0
    assert summary["promotion_allowed_count"] == 0


def test_provider_adapter_runner_handoff_requires_authorization(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={
                "worker_id": "runner-handoff-no-auth-dry",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/live-executor-guard",
            json={
                "worker_id": "runner-handoff-no-auth-guard",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
            json={
                "worker_id": "runner-handoff-no-auth-request",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )

    handoff = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/export-provider-adapter-runner-handoff",
        json={
            "worker_id": "runner-handoff-no-auth",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )

    assert handoff.status_code == 409
    assert "matching provider execution authorization" in handoff.json()["detail"]


def test_provider_adapter_runner_fixture_requires_authorization(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={
                "worker_id": "runner-no-auth-dry",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/live-executor-guard",
            json={
                "worker_id": "runner-no-auth-guard",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
            json={
                "worker_id": "runner-no-auth-request",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    runner = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-provider-adapter-runner-fixture",
        json={
            "worker_id": "runner-no-auth",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )
    assert runner.status_code == 409
    assert "matching provider execution authorization" in runner.json()["detail"]


def test_review_only_dispatcher_step_records_runner_envelope_without_staging(
    client,
    raw_conn,
):
    sid = _create_session(client)
    dispatched = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-step",
            json={
                "worker_id": "dispatcher-smoke",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "note": "dispatch one review-only provider runner step",
            },
        )
    )

    worker_step = dispatched["worker_step"]
    assert worker_step["status"] == "dispatched_review_only"
    assert worker_step["worker_mode"] == "review_only_dispatcher_step"
    assert worker_step["created_generation_schedule_run"] is True
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["authorization_ref"] == (
        "auth_sched_next_map_visual_prefetch_fixture_001"
    )
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["promotion_allowed_count"] == 0
    assert worker_step["staging_performed"] is False
    assert worker_step["promotion_performed"] is False
    assert worker_step["queue_completed"] is False
    assert "provider_artifact_staging" not in dispatched
    assert "provider_artifact_promotion_report" not in dispatched

    assert dispatched["steps"]["dry_run_step"]["status"] == "processed"
    assert dispatched["steps"]["live_executor_guard"]["status"] == "blocked"
    assert dispatched["steps"]["generation_executor_run_request"]["status"] == (
        "prepared"
    )
    assert dispatched["steps"]["provider_execution_authorization"]["status"] == (
        "authorized"
    )
    assert dispatched["steps"]["provider_adapter_runner"]["status"] == (
        "runner_recorded"
    )
    assert dispatched["generation_schedule_queue_item"]["status"] == "waiting_review"
    assert dispatched["provider_adapter_execution_receipt"]["execution"][
        "mode"
    ] == "fixture_backed_no_provider_call"
    assert dispatched["provider_adapter_execution_receipt"]["execution"][
        "provider_call_performed_by_receipt_builder"
    ] is False
    assert dispatched["provider_output_envelope"]["provider_call"][
        "performed"
    ] is False
    assert dispatched["provider_output_envelope"]["artifact_manifest"]["status"] == (
        "not_created"
    )
    assert dispatched["provider_output_envelope"]["activation_gate"][
        "activation_allowed"
    ] is False
    assert dispatched["provider_output_envelope"]["envelope_id"] == worker_step[
        "envelope_id"
    ]

    ledger_summary = dispatched["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 4
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 1,
        "provider_execution_authorization": 1,
        "provider_adapter_execution_receipt": 1,
        "provider_output_envelope": 1,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0

    ledger_kinds = {
        row["artifact_kind"]
        for row in raw_conn.execute(
            "SELECT artifact_kind FROM generation_artifact_ledger WHERE session_id = ?",
            (sid,),
        ).fetchall()
    }
    assert ledger_kinds == {
        "generation_executor_run_request",
        "provider_execution_authorization",
        "provider_adapter_execution_receipt",
        "provider_output_envelope",
    }


def test_review_only_dispatcher_step_can_use_next_queued_item(client):
    sid = _create_session(client)
    dispatched = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-step",
            json={"worker_id": "dispatcher-next"},
        )
    )

    worker_step = dispatched["worker_step"]
    assert worker_step["status"] == "dispatched_review_only"
    assert worker_step["schedule_item_id"] == "sched_stage05_worldline_prefetch"
    assert dispatched["generation_schedule_queue_item"]["status"] == "waiting_review"
    assert dispatched["generation_artifact_ledger"]["summary"]["item_count"] == 4


def test_review_only_dispatcher_step_rejects_already_processed_item(client):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-step",
            json={
                "worker_id": "dispatcher-repeat",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )

    repeated = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-step",
        json={
            "worker_id": "dispatcher-repeat",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )
    assert repeated.status_code == 409
    assert "must be queued" in repeated.json()["detail"]


def test_review_only_dispatcher_drain_dispatches_multiple_without_staging(
    client,
    raw_conn,
):
    sid = _create_session(client)
    drained = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
            json={
                "worker_id": "dispatcher-drain",
                "max_items": 2,
                "note": "drain two review-only items",
            },
        )
    )

    worker_step = drained["worker_step"]
    assert worker_step["status"] == "drained_review_only"
    assert worker_step["worker_mode"] == "review_only_dispatcher_drain"
    assert worker_step["created_generation_schedule_run"] is True
    assert worker_step["max_items"] == 2
    assert worker_step["dispatched_count"] == 2
    assert worker_step["idle_reached"] is False
    assert worker_step["stop_reason"] == "budget_exhausted"
    assert worker_step["remaining_eligible_count"] == 2
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["promotion_allowed_count"] == 0
    assert worker_step["staging_performed"] is False
    assert worker_step["promotion_performed"] is False
    assert worker_step["queue_completed_count"] == 0
    assert [step["schedule_item_id"] for step in drained["dispatcher_steps"]] == [
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
    ]
    assert all(step["queue_completed"] is False for step in drained["dispatcher_steps"])
    assert all(
        step["provider_call_count"] == 0 for step in drained["dispatcher_steps"]
    )
    assert "provider_artifact_staging" not in drained
    assert "provider_artifact_promotion_report" not in drained

    queue_by_id = {
        item["schedule_item_id"]: item
        for item in drained["generation_schedule_queue"]["items"]
    }
    assert queue_by_id["sched_stage05_worldline_prefetch"]["status"] == (
        "waiting_review"
    )
    assert queue_by_id["sched_next_map_visual_prefetch"]["status"] == (
        "waiting_review"
    )
    assert queue_by_id["sched_video_frame_background_compile"]["status"] == "queued"
    assert queue_by_id["sched_frontend_mock_sprite_repair_lazy"]["status"] == "queued"
    queue_summary = drained["generation_schedule_queue"]["summary"]
    assert queue_summary["waiting_review_count"] == 2
    assert queue_summary["claimable_count"] == 2

    ledger_summary = drained["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 8
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 2,
        "provider_execution_authorization": 2,
        "provider_adapter_execution_receipt": 2,
        "provider_output_envelope": 2,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0

    ledger_kinds = {
        row["artifact_kind"]
        for row in raw_conn.execute(
            "SELECT artifact_kind FROM generation_artifact_ledger WHERE session_id = ?",
            (sid,),
        ).fetchall()
    }
    assert ledger_kinds == {
        "generation_executor_run_request",
        "provider_execution_authorization",
        "provider_adapter_execution_receipt",
        "provider_output_envelope",
    }


def test_generation_prefetch_cache_requires_session(client):
    missing = client.get(
        "/api/sessions/missing-session/generation-schedule/prefetch-cache"
    )
    assert missing.status_code == 404


def test_generation_prefetch_cache_empty_without_run(client, raw_conn):
    sid = _create_session(client)
    before_counts = _session_state_counts(raw_conn, sid)

    cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/prefetch-cache")
    )

    assert cache["generation_schedule_run"] is None
    summary = cache["generation_prefetch_cache"]["summary"]
    assert summary["item_count"] == 0
    assert summary["cache_status_counts"] == {}
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["activation_allowed_count"] == 0
    assert summary["promotion_allowed_count"] == 0
    assert cache["generation_prefetch_cache"]["items"] == []
    assert _session_state_counts(raw_conn, sid) == before_counts


def test_generation_prefetch_cache_tracks_dispatcher_drain_outputs(
    client,
    raw_conn,
):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
            json={
                "worker_id": "dispatcher-drain-for-cache",
                "max_items": 2,
            },
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/prefetch-cache")
    )
    second_cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/prefetch-cache")
    )

    assert _session_state_counts(raw_conn, sid) == before_counts
    assert second_cache == cache
    summary = cache["generation_prefetch_cache"]["summary"]
    assert summary["item_count"] == 8
    assert summary["review_only_envelope_ready_count"] == 2
    assert summary["staged_or_reviewed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    assert summary["recorded_provider_call_count"] == 0
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["activation_allowed_count"] == 0
    assert summary["promotion_allowed_count"] == 0

    items_by_id = {
        item["schedule_item_id"]: item
        for item in cache["generation_prefetch_cache"]["items"]
    }
    assert set(items_by_id) == {
        "sched_session_frontend_mock_bootstrap",
        "sched_first_battle_map_runtime_package",
        "sched_runtime_art_atlas_ready",
        "sched_static_fallback_runtime_route",
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
        "sched_video_frame_background_compile",
        "sched_frontend_mock_sprite_repair_lazy",
    }
    for schedule_item_id in (
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
    ):
        item = items_by_id[schedule_item_id]
        assert item["cache_status"] == "review_only_envelope_ready"
        assert item["queue_status"] == "waiting_review"
        assert item["runtime_ready"] is False
        assert item["review_only"] is True
        assert item["recorded_provider_call_count"] == 0
        assert item["provider_call_count_by_this_request"] == 0
        assert item["world_mutation_count_by_this_request"] == 0
        assert item["activation_gate"]["activation_allowed"] is False
        assert item["promotion_gate"]["promotion_allowed"] is False
        assert item["refs"]["generation_executor_run_request"] is not None
        assert item["refs"]["provider_execution_authorization"] is not None
        assert item["refs"]["provider_adapter_execution_receipt"] is not None
        assert item["refs"]["provider_output_envelope"] is not None
        assert item["refs"]["provider_artifact_staging_manifest"] is None
        assert item["refs"]["provider_artifact_promotion_report"] is None


def test_generation_prefetch_cache_reflects_staging_review_report(
    client,
    raw_conn,
):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-fixture-executor-chain",
            json={"worker_id": "executor-chain-for-cache"},
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    cache = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/prefetch-cache")
    )

    assert _session_state_counts(raw_conn, sid) == before_counts
    summary = cache["generation_prefetch_cache"]["summary"]
    assert summary["item_count"] == 8
    assert summary["staged_or_reviewed_count"] == 1
    assert summary["activation_allowed_count"] == 0
    assert summary["promotion_allowed_count"] == 0
    item = {
        cache_item["schedule_item_id"]: cache_item
        for cache_item in cache["generation_prefetch_cache"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == "promotion_blocked"
    assert item["queue_status"] == "waiting_review"
    assert item["runtime_ready"] is False
    assert item["activation_gate"]["activation_allowed"] is False
    assert item["promotion_gate"]["promotion_allowed"] is False
    assert item["promotion_gate"]["promotion_decision"] == "blocked_review_required"
    assert item["refs"]["provider_artifact_staging_manifest"] is not None
    assert item["refs"]["provider_artifact_promotion_report"] is not None


def test_generation_activation_gate_builder_blocks_promotion_allowed_candidate():
    payload = build_generation_activation_gate_payload(
        {
            "session_id": "sess_test",
            "mode": "frontend_mock_fixture",
            "generation_schedule_run": {"run_id": "gsrun_test"},
            "generation_prefetch_cache": {
                "summary": {
                    "recorded_provider_call_count": 1,
                    "provider_call_count_by_this_request": 0,
                    "world_mutation_count_by_this_request": 0,
                },
                "items": [
                    {
                        "schedule_item_id": "sched_ready",
                        "object_kind": "map_visual_layer",
                        "object_ref": "map.old_signal_tower",
                        "latency_class": "background_prefetch",
                        "queue_status": "waiting_review",
                        "cache_status": "promotion_allowed_pending_activation",
                        "recorded_provider_call_count": 1,
                        "promotion_gate": {"promotion_allowed": True},
                        "activation_gate": {
                            "activation_allowed": False,
                            "blocked_reason": "runtime_package_required",
                            "required_next_gates": ["activation_revalidation"],
                        },
                        "refs": {
                            "provider_artifact_promotion_report": {"ledger_id": "ledg_1"}
                        },
                    },
                    {
                        "schedule_item_id": "sched_static",
                        "object_kind": "runtime_package",
                        "object_ref": "runtime.gray_lantern_station",
                        "latency_class": "sync_blocking",
                        "queue_status": "completed",
                        "cache_status": "completed",
                        "promotion_gate": {"promotion_allowed": False},
                        "activation_gate": {"activation_allowed": False},
                        "refs": {},
                    },
                ],
            },
        }
    )

    gate = payload["generation_activation_gate"]
    summary = gate["summary"]
    assert summary["item_count"] == 2
    assert summary["activation_allowed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    assert summary["promotion_allowed_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["not_applicable_count"] == 1
    assert summary["recorded_provider_call_count"] == 1
    assert gate["safety"] == {
        "reads_env": False,
        "calls_provider": False,
        "stages_artifacts": False,
        "promotes_artifacts": False,
        "completes_queue_items": False,
        "writes_world_state": False,
        "activates_runtime": False,
        "source_read_model": "generation_prefetch_cache",
    }
    items_by_id = {item["schedule_item_id"]: item for item in gate["items"]}
    assert items_by_id["sched_ready"]["activation_status"] == (
        "blocked_runtime_package_or_world_delta_required"
    )
    assert items_by_id["sched_ready"]["activation_allowed"] is False
    assert items_by_id["sched_ready"]["promotion_allowed"] is True
    assert "activation_revalidation" in items_by_id["sched_ready"][
        "required_next_gates"
    ]
    assert items_by_id["sched_static"]["activation_status"] == (
        "not_applicable_locked_or_fallback_source"
    )


def test_shared_prefetch_cache_builders_only_index_promotion_allowed_candidates():
    activation_gate_payload = build_generation_activation_gate_payload(
        {
            "session_id": "sess_shared",
            "mode": "frontend_mock_fixture",
            "generation_schedule_run": {"run_id": "gsrun_shared"},
            "generation_prefetch_cache": {
                "summary": {"recorded_provider_call_count": 1},
                "items": [
                    {
                        "schedule_item_id": "sched_ready",
                        "object_kind": "map_visual_layer",
                        "object_ref": "map.old_signal_tower",
                        "latency_class": "background_prefetch",
                        "queue_status": "waiting_review",
                        "cache_status": "promotion_allowed_pending_activation",
                        "recorded_provider_call_count": 1,
                        "promotion_gate": {"promotion_allowed": True},
                        "activation_gate": {
                            "activation_allowed": False,
                            "required_next_gates": ["activation_revalidation"],
                        },
                        "refs": {
                            "provider_artifact_promotion_report": {"ledger_id": "ledg_1"}
                        },
                    },
                    {
                        "schedule_item_id": "sched_blocked",
                        "object_kind": "map_visual_layer",
                        "object_ref": "map.blocked",
                        "latency_class": "background_prefetch",
                        "queue_status": "waiting_review",
                        "cache_status": "promotion_blocked",
                        "promotion_gate": {"promotion_allowed": False},
                        "activation_gate": {"activation_allowed": False},
                        "refs": {},
                    },
                ],
            },
        }
    )

    records = build_shared_prefetch_cache_records(
        activation_gate_payload, indexed_at="2026-07-03T00:00:00Z"
    )

    assert len(records) == 1
    record = records[0]
    assert record["schema_version"] == "generation_shared_prefetch_cache_record.v0.1"
    assert record["cache_key"].startswith("gshared_")
    assert record["source"] == {
        "source_session_id": "sess_shared",
        "source_run_id": "gsrun_shared",
        "source_schedule_item_id": "sched_ready",
    }
    assert record["lifecycle_status"] == "promotion_allowed_pending_runtime_build"
    assert record["promotion_allowed"] is True
    assert record["activation_allowed"] is False
    assert record["runtime_ready"] is False
    assert record["safety"]["calls_provider"] is False
    assert record["safety"]["writes_world_state"] is False
    compact = compact_shared_prefetch_cache(records)
    assert compact["summary"]["record_count"] == 1
    assert compact["summary"]["activation_allowed_count"] == 0
    assert compact["summary"]["runtime_ready_count"] == 0


def test_shared_prefetch_cache_repository_upserts_global_records(client):
    _create_session(client)
    record = build_shared_prefetch_cache_records(
        build_generation_activation_gate_payload(
            {
                "session_id": "sess_shared_repo",
                "generation_schedule_run": {"run_id": "gsrun_shared_repo"},
                "generation_prefetch_cache": {
                    "items": [
                        {
                            "schedule_item_id": "sched_ready",
                            "object_kind": "map_visual_layer",
                            "object_ref": "map.old_signal_tower",
                            "latency_class": "background_prefetch",
                            "queue_status": "waiting_review",
                            "cache_status": "promotion_allowed_pending_activation",
                            "promotion_gate": {"promotion_allowed": True},
                            "activation_gate": {"activation_allowed": False},
                            "refs": {},
                        }
                    ]
                },
            }
        ),
        indexed_at="2026-07-03T00:00:00Z",
    )[0]

    upsert_shared_prefetch_cache_records([record])
    updated = {**record, "updated_at": "2026-07-03T00:01:00Z"}
    updated["source"] = {
        **record["source"],
        "source_session_id": "sess_shared_repo_second",
    }
    upsert_shared_prefetch_cache_records([updated])

    records = load_shared_prefetch_cache_records()
    assert len(records) == 1
    assert records[0]["cache_key"] == record["cache_key"]
    assert records[0]["created_at"] == "2026-07-03T00:00:00Z"
    assert records[0]["updated_at"] == "2026-07-03T00:01:00Z"
    assert records[0]["source"]["source_session_id"] == "sess_shared_repo_second"


def test_shared_prefetch_cache_hit_builder_matches_current_queue_items():
    prefetch_payload = {
        "session_id": "sess_hit",
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": {"run_id": "gsrun_hit"},
        "generation_prefetch_cache": {
            "items": [
                {
                    "schedule_item_id": "sched_match",
                    "object_kind": "map_visual_layer",
                    "object_ref": "map.old_signal_tower",
                    "latency_class": "background_prefetch",
                    "queue_status": "queued",
                    "cache_status": "queued",
                },
                {
                    "schedule_item_id": "sched_miss",
                    "object_kind": "story_node",
                    "object_ref": "story.missing",
                    "latency_class": "background",
                    "queue_status": "queued",
                    "cache_status": "queued",
                },
            ]
        },
    }
    records = [
        {
            "cache_key": "gshared_hit",
            "object_kind": "map_visual_layer",
            "object_ref": "map.old_signal_tower",
            "lifecycle_status": "promotion_allowed_pending_runtime_build",
            "source": {
                "source_session_id": "sess_source",
                "source_run_id": "gsrun_source",
                "source_schedule_item_id": "sched_source",
            },
            "required_next_gates": ["runtime_package_validation"],
            "promotion_allowed": True,
            "activation_allowed": False,
            "runtime_ready": False,
        },
        {
            "cache_key": "gshared_ignored",
            "object_kind": "story_node",
            "object_ref": "story.missing",
            "lifecycle_status": "revoked",
        },
    ]

    payload = build_shared_prefetch_cache_hit_payload(prefetch_payload, records)

    hit_view = payload["generation_shared_prefetch_cache_hits"]
    summary = hit_view["summary"]
    assert summary["schedule_item_count"] == 2
    assert summary["shared_record_count"] == 2
    assert summary["hit_count"] == 1
    assert summary["activation_allowed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    assert summary["hit_status_counts"] == {
        "no_shared_candidate": 1,
        "shared_candidate_available_pending_runtime_build": 1,
    }
    items = {item["schedule_item_id"]: item for item in hit_view["items"]}
    assert items["sched_match"]["hit_count"] == 1
    assert items["sched_match"]["hit_status"] == (
        "shared_candidate_available_pending_runtime_build"
    )
    assert items["sched_match"]["hits"][0]["activation_allowed"] is False
    assert items["sched_match"]["hits"][0]["runtime_ready"] is False
    assert items["sched_miss"]["hit_status"] == "no_shared_candidate"
    assert hit_view["safety"]["calls_provider"] is False
    assert hit_view["safety"]["activates_runtime"] is False


def test_shared_cache_reuse_candidate_builder_keeps_review_only_gate():
    candidate = build_shared_cache_reuse_candidate(
        session_id="sess_reuse_builder",
        latest_run={"run_id": "gsrun_reuse_builder"},
        queue_item={
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "object_kind": "map_visual_layer",
            "object_ref": "map_compile_package:old_signal_tower_pressure",
            "latency_class": "background_prefetch",
        },
        hit={
            "cache_key": "gshared_reuse_builder",
            "lifecycle_status": "promotion_allowed_pending_runtime_build",
            "source": {
                "source_session_id": "sess_source",
                "source_run_id": "gsrun_source",
                "source_schedule_item_id": "sched_next_map_visual_prefetch",
            },
            "required_next_gates": ["runtime_package_validation"],
            "promotion_allowed": True,
        },
        ts="2026-07-03T00:00:00Z",
        worker_id="test_reuse_builder",
        note="builder smoke",
    )

    compact = compact_shared_cache_reuse_candidate(candidate)

    assert candidate["schema_version"] == (
        "generation_shared_prefetch_cache_reuse_candidate.v0.1"
    )
    assert candidate["candidate_id"].startswith("gshared_reuse_")
    assert compact["reuse_status"] == "review_only_reuse_candidate"
    assert compact["shared_cache_ref"]["promotion_allowed"] is True
    assert compact["shared_cache_ref"]["activation_allowed"] is False
    assert compact["shared_cache_ref"]["runtime_ready"] is False
    assert compact["reuse_gate"]["reuse_available"] is True
    assert compact["reuse_gate"]["activation_allowed"] is False
    assert compact["reuse_gate"]["runtime_ready"] is False
    assert "runtime_package_validation" in compact["reuse_gate"]["required_next_gates"]
    assert (
        "world_state_delta_transaction_validation"
        in compact["reuse_gate"]["required_next_gates"]
    )
    assert compact["safety"]["calls_provider"] is False
    assert compact["safety"]["writes_world_state"] is False
    assert compact["safety"]["activates_runtime"] is False


def test_runtime_build_request_builder_records_review_only_source():
    request = build_runtime_build_request(
        session_id="sess_runtime_build",
        latest_run={"run_id": "gsrun_runtime_build"},
        queue_item={
            "schedule_item_id": "sched_runtime_build",
            "object_kind": "map_compile_package",
            "object_ref": "map_compile_package:test",
            "latency_class": "background_prefetch",
        },
        source_ref={
            "ledger_id": "gled_promo",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_test",
            "status": "promotion_allowed",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {
                    "required_next_gates": ["semantic_gate_revalidation"],
                },
            },
        },
        ts="2026-07-03T00:01:00Z",
        worker_id="runtime-build-preparer",
        note="prepare builder",
    )

    assert request["schema_version"] == "generation_runtime_build_request.v0.1"
    assert request["request_id"].startswith("gruntime_build_")
    assert request["request_status"] == RUNTIME_BUILD_REQUEST_LEDGER_STATUS
    assert request["source_candidate_ref"] == {
        "artifact_kind": "provider_artifact_promotion_report",
        "ledger_id": "gled_promo",
        "source_id": "ppromo_test",
        "status": "promotion_allowed",
        "updated_at": "2026-07-03T00:00:00Z",
    }
    assert request["build_targets"] == {
        "runtime_package_build_requested": True,
        "world_state_delta_transaction_build_requested": True,
        "published_media_update_requested": False,
        "runtime_activation_requested": False,
        "queue_completion_requested": False,
    }
    assert request["build_gate"]["runtime_ready"] is False
    assert request["build_gate"]["activation_allowed"] is False
    assert request["build_gate"]["world_mutation_allowed"] is False
    assert "runtime_package_or_world_delta_transaction_builder" in request[
        "build_gate"
    ]["required_next_gates"]
    assert "semantic_gate_revalidation" in request["build_gate"][
        "required_next_gates"
    ]
    compact = compact_runtime_build_request(request)
    assert compact["request_id"] == request["request_id"]
    assert compact["safety"]["calls_provider"] is False
    assert compact["safety"]["writes_world_state"] is False
    assert compact["safety"]["activates_runtime"] is False


def test_runtime_artifact_build_report_resolves_review_only_targets():
    request = build_runtime_build_request(
        session_id="sess_runtime_artifacts",
        latest_run={"run_id": "gsrun_runtime_artifacts"},
        queue_item={
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "object_kind": "map_visual_prefetch",
            "object_ref": "map_compile_package:old_signal_tower_pressure",
            "latency_class": "background_prefetch",
        },
        source_ref={
            "ledger_id": "gled_reuse",
            "artifact_kind": REUSE_CANDIDATE_LEDGER_KIND,
            "source_id": "greuse_test",
            "status": REUSE_CANDIDATE_LEDGER_STATUS,
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "reuse_gate": {
                    "required_next_gates": ["runtime_package_validation"],
                },
            },
        },
        ts="2026-07-03T00:01:00Z",
        worker_id="runtime-build-preparer",
        note=None,
    )
    resolved = resolve_runtime_artifact_targets(
        {
            "object_kind": "map_visual_prefetch",
            "object_ref": "map_compile_package:old_signal_tower_pressure",
        },
        repo_root=_ROOT,
    )
    report = build_runtime_artifact_build_report(
        session_id="sess_runtime_artifacts",
        latest_run={"run_id": "gsrun_runtime_artifacts"},
        queue_item={
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "object_kind": "map_visual_prefetch",
            "object_ref": "map_compile_package:old_signal_tower_pressure",
            "latency_class": "background_prefetch",
        },
        runtime_build_request_ref={
            "ledger_id": "gled_runtime_request",
            "artifact_kind": RUNTIME_BUILD_REQUEST_LEDGER_KIND,
            "source_id": request["request_id"],
            "status": RUNTIME_BUILD_REQUEST_LEDGER_STATUS,
            "updated_at": "2026-07-03T00:01:00Z",
            "compact": compact_runtime_build_request(request),
        },
        resolved_targets=resolved,
        ts="2026-07-03T00:02:00Z",
        worker_id="runtime-artifact-report-builder",
        note="resolve targets",
    )

    assert report["schema_version"] == (
        "generation_runtime_artifact_build_report.v0.1"
    )
    assert report["report_id"].startswith("gruntime_artifacts_")
    assert report["report_status"] == RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS
    assert report["resolved_targets"]["build_status"] == "resolved_review_only"
    assert report["resolved_targets"]["target_count"] == 2
    assert report["resolved_targets"]["map_runtime_package_refs"][0][
        "artifact_id"
    ] == "map_pkg_old_signal_tower_v0_1"
    assert report["resolved_targets"]["published_media_update_refs"][0][
        "ref_kind"
    ] == "map_compile_package"
    assert report["build_gate"]["runtime_ready"] is False
    assert report["build_gate"]["activation_allowed"] is False
    assert report["build_gate"]["world_mutation_allowed"] is False
    assert "explicit_activation_gate" in report["build_gate"][
        "required_next_gates"
    ]
    compact = compact_runtime_artifact_build_report(report)
    assert compact["report_id"] == report["report_id"]
    assert compact["safety"]["calls_provider"] is False
    assert compact["safety"]["writes_world_state"] is False
    assert compact["safety"]["activates_runtime"] is False


def test_generation_activation_gate_requires_session(client):
    missing = client.get(
        "/api/sessions/missing-session/generation-schedule/activation-gate"
    )
    assert missing.status_code == 404


def test_generation_activation_gate_empty_without_run(client, raw_conn):
    sid = _create_session(client)
    before_counts = _session_state_counts(raw_conn, sid)

    gate = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/activation-gate")
    )

    assert gate["generation_schedule_run"] is None
    activation_gate = gate["generation_activation_gate"]
    summary = activation_gate["summary"]
    assert summary["item_count"] == 0
    assert summary["gate_status_counts"] == {}
    assert summary["blocked_count"] == 0
    assert summary["runtime_ready_count"] == 0
    assert summary["activation_allowed_count"] == 0
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert activation_gate["items"] == []
    assert activation_gate["safety"]["source_read_model"] == "generation_prefetch_cache"
    assert _session_state_counts(raw_conn, sid) == before_counts


def test_generation_activation_gate_tracks_dispatcher_drain_outputs(
    client,
    raw_conn,
):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
            json={
                "worker_id": "dispatcher-drain-for-activation-gate",
                "max_items": 2,
            },
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    gate = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/activation-gate")
    )
    second_gate = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/activation-gate")
    )

    assert second_gate == gate
    assert _session_state_counts(raw_conn, sid) == before_counts
    summary = gate["generation_activation_gate"]["summary"]
    assert summary["item_count"] == 8
    assert summary["activation_allowed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    assert summary["promotion_allowed_count"] == 0
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["gate_status_counts"][
        "blocked_staging_or_promotion_required"
    ] == 2

    items_by_id = {
        item["schedule_item_id"]: item
        for item in gate["generation_activation_gate"]["items"]
    }
    for schedule_item_id in (
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
    ):
        item = items_by_id[schedule_item_id]
        assert item["cache_status"] == "review_only_envelope_ready"
        assert item["activation_status"] == "blocked_staging_or_promotion_required"
        assert item["activation_allowed"] is False
        assert item["runtime_ready"] is False
        assert item["refs_present"]["provider_output_envelope"] is True
        assert "provider_artifact_staging_manifest" in item["required_next_gates"]
        assert "provider_artifact_promotion_report" in item["required_next_gates"]


def test_generation_activation_gate_reflects_staging_review_report(
    client,
    raw_conn,
):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-fixture-executor-chain",
            json={"worker_id": "executor-chain-for-activation-gate"},
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    gate = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/activation-gate")
    )

    assert _session_state_counts(raw_conn, sid) == before_counts
    summary = gate["generation_activation_gate"]["summary"]
    assert summary["item_count"] == 8
    assert summary["activation_allowed_count"] == 0
    assert summary["promotion_allowed_count"] == 0
    assert summary["gate_status_counts"]["blocked_promotion_report"] == 1
    item = {
        gate_item["schedule_item_id"]: gate_item
        for gate_item in gate["generation_activation_gate"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == "promotion_blocked"
    assert item["activation_status"] == "blocked_promotion_report"
    assert item["activation_allowed"] is False
    assert item["promotion_allowed"] is False
    assert item["blocked_reason"] == "media_semantic_and_human_review_not_complete"
    assert item["refs_present"]["provider_artifact_staging_manifest"] is True
    assert item["refs_present"]["provider_artifact_promotion_report"] is True


def test_generation_daemon_readiness_requires_session(client):
    missing = client.get(
        "/api/sessions/missing-session/generation-schedule/daemon-readiness"
    )
    assert missing.status_code == 404


def test_generation_daemon_readiness_allows_initial_manual_tick_without_run(
    client,
    raw_conn,
):
    sid = _create_session(client)
    before_counts = _session_state_counts(raw_conn, sid)

    readiness = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/daemon-readiness")
    )

    assert _session_state_counts(raw_conn, sid) == before_counts
    assert readiness["generation_schedule_run"] is None
    daemon = readiness["generation_daemon_readiness"]
    assert daemon["schema_version"] == "generation_daemon_readiness.v0.1"
    assert daemon["readiness_mode"] == "review_only_control_plane"
    assert daemon["automatic_daemon_status"] == "blocked_not_enabled_in_mvp"
    assert daemon["manual_tick_status"] == "ready_initial_tick_can_create_run"
    assert daemon["manual_tick_ready"] is True
    summary = daemon["summary"]
    assert summary["has_generation_schedule_run"] is False
    assert summary["schedule_item_count"] == 0
    assert summary["queued_provider_review_required_count"] == 0
    assert summary["shared_cache_hit_count"] == 0
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["activation_allowed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    actions = daemon["recommended_next_actions"]
    assert actions[0]["action"] == "run_review_only_background_handoff_tick"
    assert "run-review-only-background-handoff-tick" in actions[0]["endpoint"]
    gates = {gate["gate"]: gate for gate in daemon["readiness_gates"]}
    assert gates["automatic_daemon_enabled"]["status"] == "blocked"
    assert gates["session_generation_schedule_run"]["status"] == (
        "missing_but_manual_tick_can_create"
    )
    assert daemon["safety"] == {
        "reads_env": False,
        "calls_provider": False,
        "runs_always_on_loop": False,
        "auto_provider_dispatch_allowed": False,
        "external_runner_required_for_provider_calls": True,
        "stores_raw_prompt": False,
        "stores_provider_response": False,
        "stages_artifacts": False,
        "promotes_artifacts": False,
        "completes_queue_items": False,
        "writes_world_state": False,
        "activates_runtime": False,
        "source_read_models": [
            "generation_prefetch_cache",
            "generation_activation_gate",
            "generation_shared_prefetch_cache_hits",
        ],
    }


def test_generation_daemon_readiness_tracks_manual_background_tick(
    client,
    raw_conn,
):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "run-review-only-background-handoff-tick",
            json={"worker_id": "readiness-background-tick", "max_items": 2},
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    readiness = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/daemon-readiness")
    )
    second_readiness = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/daemon-readiness")
    )

    assert second_readiness == readiness
    assert _session_state_counts(raw_conn, sid) == before_counts
    daemon = readiness["generation_daemon_readiness"]
    assert daemon["automatic_daemon_status"] == "blocked_not_enabled_in_mvp"
    assert daemon["manual_tick_status"] == (
        "ready_to_dispatch_queued_provider_review_items"
    )
    assert daemon["manual_tick_ready"] is True
    summary = daemon["summary"]
    assert summary["has_generation_schedule_run"] is True
    assert summary["schedule_item_count"] == 8
    assert summary["queued_provider_review_required_count"] == 2
    assert summary["waiting_review_count"] == 2
    assert summary["review_only_envelope_ready_count"] == 2
    assert summary["staged_or_reviewed_count"] == 0
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    assert summary["activation_allowed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    actions = [action["action"] for action in daemon["recommended_next_actions"]]
    assert actions[:2] == [
        "run_review_only_background_handoff_tick",
        "import_provider_artifact_review_output",
    ]
    gates = {gate["gate"]: gate for gate in daemon["readiness_gates"]}
    assert gates["queued_provider_review_work"]["status"] == "ready"
    assert gates["provider_dispatch"]["status"] == "blocked_external_runner_required"
    assert gates["artifact_promotion"]["status"] == (
        "blocked_explicit_review_required"
    )
    assert gates["runtime_activation"]["status"] == (
        "blocked_explicit_activation_required"
    )


def test_generation_daemon_readiness_surfaces_shared_cache_hits(client):
    source_sid = _create_session(client)
    source_run = _payload(
        client.post(f"/api/sessions/{source_sid}/generation-schedule/runs")
    )
    source_run_id = source_run["generation_schedule_run"]["run_id"]
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{source_sid}_provider_artifact_promotion_readiness",
            "run_id": source_run_id,
            "session_id": source_sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_shared_cache_readiness",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    indexed = _payload(
        client.post(
            f"/api/sessions/{source_sid}/generation-schedule/workers/"
            "index-shared-prefetch-cache"
        )
    )
    assert indexed["shared_prefetch_cache_index"]["indexed_count"] == 1

    target_sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{target_sid}/generation-schedule/runs"))

    readiness = _payload(
        client.get(f"/api/sessions/{target_sid}/generation-schedule/daemon-readiness")
    )

    daemon = readiness["generation_daemon_readiness"]
    assert daemon["summary"]["shared_cache_hit_count"] == 1
    assert daemon["summary"]["queued_provider_review_required_count"] == 4
    actions = {action["action"]: action for action in daemon["recommended_next_actions"]}
    assert "run_review_only_background_handoff_tick" in actions
    assert "record_shared_prefetch_cache_reuse_candidate" in actions
    assert actions["record_shared_prefetch_cache_reuse_candidate"][
        "provider_call_count_by_this_request"
    ] == 0
    gates = {gate["gate"]: gate for gate in daemon["readiness_gates"]}
    assert gates["shared_prefetch_cache_reuse"]["status"] == "ready"
    assert daemon["safety"]["calls_provider"] is False
    assert daemon["safety"]["writes_world_state"] is False


def test_generation_shared_prefetch_cache_requires_session(client):
    missing = client.get(
        "/api/sessions/missing-session/generation-schedule/shared-prefetch-cache"
    )
    assert missing.status_code == 404
    missing_index = client.post(
        "/api/sessions/missing-session/generation-schedule/workers/index-shared-prefetch-cache"
    )
    assert missing_index.status_code == 404


def test_generation_shared_prefetch_cache_indexes_promotion_allowed_candidates(
    client,
    raw_conn,
):
    sid = _create_session(client)
    run_payload = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run_id = run_payload["generation_schedule_run"]["run_id"]
    ts = "2026-07-03T00:00:00Z"
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{sid}_provider_artifact_promotion_report_shared",
            "run_id": run_id,
            "session_id": sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_shared_cache",
            "status": "promotion_allowed",
            "created_at": ts,
            "updated_at": ts,
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    before_counts = _session_state_counts(raw_conn, sid)

    indexed = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/index-shared-prefetch-cache"
        )
    )

    assert _session_state_counts(raw_conn, sid) == before_counts
    index_summary = indexed["shared_prefetch_cache_index"]
    assert index_summary == {
        "indexed_count": 1,
        "source_read_model": "generation_activation_gate",
        "provider_call_count_by_this_request": 0,
        "world_mutation_count_by_this_request": 0,
        "activation_allowed_count": 0,
        "runtime_ready_count": 0,
    }
    cache = indexed["generation_shared_prefetch_cache"]
    assert cache["summary"]["record_count"] == 1
    assert cache["summary"]["promotion_allowed_count"] == 1
    assert cache["summary"]["activation_allowed_count"] == 0
    assert cache["summary"]["runtime_ready_count"] == 0
    record = cache["records"][0]
    assert record["object_ref"] == "map_compile_package:old_signal_tower_pressure"
    assert record["source"]["source_session_id"] == sid
    assert record["source"]["source_run_id"] == run_id
    assert record["source"]["source_schedule_item_id"] == (
        "sched_next_map_visual_prefetch"
    )
    assert record["lifecycle_status"] == "promotion_allowed_pending_runtime_build"
    assert record["activation_allowed"] is False
    assert record["runtime_ready"] is False

    other_sid = _create_session(client)
    cross_session = _payload(
        client.get(
            f"/api/sessions/{other_sid}/generation-schedule/shared-prefetch-cache"
        )
    )
    assert cross_session["generation_shared_prefetch_cache"]["summary"][
        "record_count"
    ] == 1

    reset = client.post(f"/api/sessions/{sid}/reset")
    assert reset.status_code == 200, reset.text
    after_reset = _payload(
        client.get(
            f"/api/sessions/{other_sid}/generation-schedule/shared-prefetch-cache"
        )
    )
    assert after_reset["generation_shared_prefetch_cache"]["summary"][
        "record_count"
    ] == 1


def test_generation_shared_prefetch_cache_ignores_blocked_candidates(client):
    sid = _create_session(client)
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-fixture-executor-chain",
            json={"worker_id": "executor-chain-for-shared-cache"},
        )
    )

    indexed = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/index-shared-prefetch-cache"
        )
    )

    assert indexed["shared_prefetch_cache_index"]["indexed_count"] == 0
    assert indexed["generation_shared_prefetch_cache"]["summary"]["record_count"] == 0


def test_generation_shared_prefetch_cache_hits_require_session(client):
    missing = client.get(
        "/api/sessions/missing-session/generation-schedule/shared-prefetch-cache/hits"
    )
    assert missing.status_code == 404


def test_generation_shared_prefetch_cache_hits_match_current_run(
    client,
    raw_conn,
):
    source_sid = _create_session(client)
    source_run = _payload(
        client.post(f"/api/sessions/{source_sid}/generation-schedule/runs")
    )
    source_run_id = source_run["generation_schedule_run"]["run_id"]
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{source_sid}_provider_artifact_promotion_report_hit",
            "run_id": source_run_id,
            "session_id": source_sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_shared_cache_hit",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    indexed = _payload(
        client.post(
            f"/api/sessions/{source_sid}/generation-schedule/workers/index-shared-prefetch-cache"
        )
    )
    assert indexed["shared_prefetch_cache_index"]["indexed_count"] == 1

    target_sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{target_sid}/generation-schedule/runs"))
    before_counts = _session_state_counts(raw_conn, target_sid)

    hits = _payload(
        client.get(
            f"/api/sessions/{target_sid}/generation-schedule/shared-prefetch-cache/hits"
        )
    )

    assert _session_state_counts(raw_conn, target_sid) == before_counts
    hit_view = hits["generation_shared_prefetch_cache_hits"]
    summary = hit_view["summary"]
    assert summary["schedule_item_count"] == 8
    assert summary["shared_record_count"] == 1
    assert summary["hit_count"] == 1
    assert summary["activation_allowed_count"] == 0
    assert summary["runtime_ready_count"] == 0
    assert summary["provider_call_count_by_this_request"] == 0
    assert summary["world_mutation_count_by_this_request"] == 0
    items = {item["schedule_item_id"]: item for item in hit_view["items"]}
    item = items["sched_next_map_visual_prefetch"]
    assert item["hit_status"] == "shared_candidate_available_pending_runtime_build"
    assert item["hit_count"] == 1
    assert item["activation_allowed"] is False
    assert item["runtime_ready"] is False
    hit = item["hits"][0]
    assert hit["source"]["source_session_id"] == source_sid
    assert hit["source"]["source_run_id"] == source_run_id
    assert hit["source"]["source_schedule_item_id"] == (
        "sched_next_map_visual_prefetch"
    )
    assert hit["activation_allowed"] is False
    assert hit["runtime_ready"] is False
    assert item["object_ref"] == "map_compile_package:old_signal_tower_pressure"


def test_generation_shared_prefetch_cache_hits_empty_without_run(client):
    sid = _create_session(client)

    hits = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/shared-prefetch-cache/hits")
    )

    summary = hits["generation_shared_prefetch_cache_hits"]["summary"]
    assert summary["schedule_item_count"] == 0
    assert summary["hit_count"] == 0
    assert hits["generation_schedule_run"] is None


def test_record_shared_prefetch_cache_reuse_candidate_requires_session_and_hit(client):
    missing = client.post(
        "/api/sessions/missing-session/generation-schedule/workers/"
        "record-shared-prefetch-cache-reuse-candidate"
    )
    assert missing.status_code == 404

    sid = _create_session(client)
    no_run = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "record-shared-prefetch-cache-reuse-candidate"
    )
    assert no_run.status_code == 409
    assert "generation schedule run is required" in no_run.text

    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    no_hit = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "record-shared-prefetch-cache-reuse-candidate"
    )
    assert no_hit.status_code == 409
    assert "no shared prefetch cache hit" in no_hit.text


def test_record_shared_prefetch_cache_reuse_candidate_writes_review_only_ledger(
    client,
    raw_conn,
):
    source_sid = _create_session(client)
    source_run = _payload(
        client.post(f"/api/sessions/{source_sid}/generation-schedule/runs")
    )
    source_run_id = source_run["generation_schedule_run"]["run_id"]
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{source_sid}_provider_artifact_promotion_report_reuse",
            "run_id": source_run_id,
            "session_id": source_sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_shared_cache_reuse",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    indexed = _payload(
        client.post(
            f"/api/sessions/{source_sid}/generation-schedule/workers/"
            "index-shared-prefetch-cache"
        )
    )
    assert indexed["shared_prefetch_cache_index"]["indexed_count"] == 1

    target_sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{target_sid}/generation-schedule/runs"))
    before_counts = _session_state_counts(raw_conn, target_sid)

    recorded = _payload(
        client.post(
            f"/api/sessions/{target_sid}/generation-schedule/workers/"
            "record-shared-prefetch-cache-reuse-candidate",
            json={
                "worker_id": "reuse-recorder-test",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )

    after_counts = _session_state_counts(raw_conn, target_sid)
    assert after_counts == {
        **before_counts,
        "generation_artifact_ledger": before_counts["generation_artifact_ledger"] + 1,
    }
    worker_step = recorded["worker_step"]
    assert worker_step["status"] == "recorded_review_only"
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["source_session_id"] == source_sid
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    candidate = recorded["shared_prefetch_cache_reuse_candidate"]
    assert candidate["reuse_status"] == "review_only_reuse_candidate"
    assert candidate["shared_cache_ref"]["source"]["source_session_id"] == source_sid
    assert candidate["reuse_gate"]["activation_allowed"] is False
    assert candidate["reuse_gate"]["runtime_ready"] is False
    ledger = recorded["generation_artifact_ledger"]
    assert ledger["summary"]["artifact_kind_counts"][REUSE_CANDIDATE_LEDGER_KIND] == 1
    assert ledger["summary"]["status_counts"][REUSE_CANDIDATE_LEDGER_STATUS] == 1
    assert ledger["summary"]["activation_allowed_count"] == 0
    assert ledger["summary"]["recorded_provider_call_count"] == 0

    prefetch = recorded["generation_prefetch_cache"]
    assert prefetch["summary"]["shared_cache_reuse_candidate_count"] == 1
    items = {item["schedule_item_id"]: item for item in prefetch["items"]}
    item = items["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == REUSE_CANDIDATE_CACHE_STATUS
    assert item["activation_allowed"] is False
    assert item["runtime_ready"] is False
    assert item["promotion_allowed"] is False
    assert (
        item["refs"][REUSE_CANDIDATE_LEDGER_KIND]["artifact_kind"]
        == REUSE_CANDIDATE_LEDGER_KIND
    )
    assert item["shared_cache_reuse"]["reuse_candidate_recorded"] is True
    assert item["shared_cache_reuse"]["reuse_available"] is True
    assert item["shared_cache_reuse"]["activation_allowed"] is False
    assert item["shared_cache_reuse"]["runtime_ready"] is False
    assert "runtime_package_validation" in item["shared_cache_reuse"][
        "required_next_gates"
    ]

    recorded_again = _payload(
        client.post(
            f"/api/sessions/{target_sid}/generation-schedule/workers/"
            "record-shared-prefetch-cache-reuse-candidate",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )

    assert _session_state_counts(raw_conn, target_sid) == after_counts
    assert recorded_again["generation_artifact_ledger"]["summary"]["item_count"] == 1


def test_prepare_runtime_build_request_requires_eligible_candidate(client):
    missing = client.post(
        "/api/sessions/missing-session/generation-schedule/workers/"
        "prepare-runtime-build-request"
    )
    assert missing.status_code == 404

    sid = _create_session(client)
    no_run = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "prepare-runtime-build-request"
    )
    assert no_run.status_code == 409
    assert "generation schedule run is required" in no_run.text

    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    no_candidate = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "prepare-runtime-build-request"
    )
    assert no_candidate.status_code == 409
    assert "no promotion-allowed or shared-cache reuse candidate" in no_candidate.text


def test_prepare_runtime_build_request_from_promotion_allowed_report(
    client,
    raw_conn,
):
    sid = _create_session(client)
    run_payload = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run_id = run_payload["generation_schedule_run"]["run_id"]
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{sid}_provider_artifact_promotion_report_runtime_build",
            "run_id": run_id,
            "session_id": sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_runtime_build",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    before_counts = _session_state_counts(raw_conn, sid)

    prepared = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "prepare-runtime-build-request",
            json={
                "worker_id": "runtime-build-preparer-test",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )

    after_counts = _session_state_counts(raw_conn, sid)
    assert after_counts == {
        **before_counts,
        "generation_artifact_ledger": before_counts["generation_artifact_ledger"] + 1,
    }
    worker_step = prepared["worker_step"]
    assert worker_step["status"] == "prepared_review_only"
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["source_artifact_kind"] == "provider_artifact_promotion_report"
    assert worker_step["source_id"] == "ppromo_runtime_build"
    assert worker_step["runtime_build_request_cache_status"] == (
        RUNTIME_BUILD_REQUEST_CACHE_STATUS
    )
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0

    request = prepared["generation_runtime_build_request"]
    assert request["request_status"] == RUNTIME_BUILD_REQUEST_LEDGER_STATUS
    assert request["source_candidate_ref"]["artifact_kind"] == (
        "provider_artifact_promotion_report"
    )
    assert request["build_gate"]["runtime_ready"] is False
    assert request["build_gate"]["activation_allowed"] is False
    assert request["build_gate"]["world_mutation_allowed"] is False
    assert "runtime_package_validation" in request["build_gate"][
        "required_next_gates"
    ]
    assert request["safety"]["calls_provider"] is False
    assert request["safety"]["writes_world_state"] is False

    ledger = prepared["generation_artifact_ledger"]
    assert ledger["summary"]["artifact_kind_counts"][
        RUNTIME_BUILD_REQUEST_LEDGER_KIND
    ] == 1
    assert ledger["summary"]["status_counts"][
        RUNTIME_BUILD_REQUEST_LEDGER_STATUS
    ] == 1
    assert ledger["summary"]["activation_allowed_count"] == 0

    prefetch = prepared["generation_prefetch_cache"]
    item = {
        cache_item["schedule_item_id"]: cache_item
        for cache_item in prefetch["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == RUNTIME_BUILD_REQUEST_CACHE_STATUS
    assert item["runtime_build_request"]["request_recorded"] is True
    assert item["runtime_build_request"]["runtime_ready"] is False
    assert item["runtime_build_request"]["activation_allowed"] is False
    assert item["refs"][RUNTIME_BUILD_REQUEST_LEDGER_KIND]["artifact_kind"] == (
        RUNTIME_BUILD_REQUEST_LEDGER_KIND
    )
    gate = {
        gate_item["schedule_item_id"]: gate_item
        for gate_item in prepared["generation_activation_gate"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert gate["activation_status"] == "blocked_runtime_builder_execution_required"
    assert gate["activation_allowed"] is False

    prepared_again = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "prepare-runtime-build-request",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    assert _session_state_counts(raw_conn, sid) == after_counts
    assert prepared_again["generation_artifact_ledger"]["summary"][
        "artifact_kind_counts"
    ][RUNTIME_BUILD_REQUEST_LEDGER_KIND] == 1


def test_runtime_artifact_build_report_requires_runtime_build_request(client):
    missing = client.post(
        "/api/sessions/missing-session/generation-schedule/workers/"
        "run-runtime-artifact-build-report"
    )
    assert missing.status_code == 404

    sid = _create_session(client)
    no_run = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "run-runtime-artifact-build-report"
    )
    assert no_run.status_code == 409
    assert "generation schedule run is required" in no_run.text

    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    no_request = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "run-runtime-artifact-build-report"
    )
    assert no_request.status_code == 409
    assert "no runtime build request" in no_request.text


def test_runtime_artifact_build_report_from_runtime_build_request(
    client,
    raw_conn,
):
    sid = _create_session(client)
    run_payload = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run_id = run_payload["generation_schedule_run"]["run_id"]
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{sid}_provider_artifact_promotion_report_artifact_build",
            "run_id": run_id,
            "session_id": sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_artifact_build",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "prepare-runtime-build-request",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    built = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "run-runtime-artifact-build-report",
            json={
                "worker_id": "runtime-artifact-report-test",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )

    after_counts = _session_state_counts(raw_conn, sid)
    assert after_counts == {
        **before_counts,
        "generation_artifact_ledger": before_counts["generation_artifact_ledger"] + 1,
    }
    worker_step = built["worker_step"]
    assert worker_step["status"] == "recorded_review_only"
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["runtime_artifact_build_report_cache_status"] == (
        RUNTIME_ARTIFACT_BUILD_REPORT_CACHE_STATUS
    )
    assert worker_step["target_count"] == 2
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0

    report = built["generation_runtime_artifact_build_report"]
    assert report["report_status"] == RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS
    assert report["source_request_ref"]["artifact_kind"] == (
        RUNTIME_BUILD_REQUEST_LEDGER_KIND
    )
    assert report["resolved_targets"]["build_status"] == "resolved_review_only"
    assert report["resolved_targets"]["target_count"] == 2
    assert report["resolved_targets"]["map_runtime_package_refs"][0][
        "artifact_id"
    ] == "map_pkg_old_signal_tower_v0_1"
    assert report["build_gate"]["activation_allowed"] is False
    assert report["build_gate"]["world_mutation_allowed"] is False
    assert report["safety"]["writes_runtime_package"] is False
    assert report["safety"]["writes_world_state"] is False

    ledger = built["generation_artifact_ledger"]
    assert ledger["summary"]["artifact_kind_counts"][
        RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND
    ] == 1
    assert ledger["summary"]["status_counts"][
        RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS
    ] == 1
    item = {
        cache_item["schedule_item_id"]: cache_item
        for cache_item in built["generation_prefetch_cache"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == RUNTIME_ARTIFACT_BUILD_REPORT_CACHE_STATUS
    assert item["runtime_artifact_build_report"]["report_recorded"] is True
    assert item["runtime_artifact_build_report"]["target_count"] == 2
    assert item["refs"][RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND][
        "artifact_kind"
    ] == RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND
    gate = {
        gate_item["schedule_item_id"]: gate_item
        for gate_item in built["generation_activation_gate"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert gate["activation_status"] == "blocked_explicit_activation_required"
    assert gate["activation_allowed"] is False

    daemon = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/daemon-readiness")
    )["generation_daemon_readiness"]
    actions = {action["action"] for action in daemon["recommended_next_actions"]}
    assert "wait_for_explicit_runtime_activation_gate" in actions
    assert "run_runtime_artifact_build_report" not in actions

    built_again = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "run-runtime-artifact-build-report",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    assert _session_state_counts(raw_conn, sid) == after_counts
    assert built_again["generation_artifact_ledger"]["summary"][
        "artifact_kind_counts"
    ][RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND] == 1


def test_runtime_activation_authorization_requires_artifact_report(client):
    missing = client.post(
        "/api/sessions/missing-session/generation-schedule/workers/"
        "record-runtime-activation-authorization"
    )
    assert missing.status_code == 404

    sid = _create_session(client)
    no_run = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "record-runtime-activation-authorization"
    )
    assert no_run.status_code == 409
    assert "generation schedule run is required" in no_run.text

    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    no_report = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "record-runtime-activation-authorization"
    )
    assert no_report.status_code == 409
    assert "no runtime artifact build report" in no_report.text


def test_runtime_activation_authorization_records_review_only_gate(
    client,
    raw_conn,
):
    sid = _create_session(client)
    run_payload = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run_id = run_payload["generation_schedule_run"]["run_id"]
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{sid}_provider_artifact_promotion_report_activation",
            "run_id": run_id,
            "session_id": sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_activation_auth",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "prepare-runtime-build-request",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "run-runtime-artifact-build-report",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    before_counts = _session_state_counts(raw_conn, sid)

    authorized = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "record-runtime-activation-authorization",
            json={
                "worker_id": "runtime-activation-auth-test",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "activation_decision": "approved_for_manual_apply",
            },
        )
    )

    after_counts = _session_state_counts(raw_conn, sid)
    assert after_counts == {
        **before_counts,
        "generation_artifact_ledger": before_counts["generation_artifact_ledger"] + 1,
    }
    worker_step = authorized["worker_step"]
    assert worker_step["status"] == "recorded_review_only"
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["runtime_activation_authorization_cache_status"] == (
        RUNTIME_ACTIVATION_AUTHORIZATION_CACHE_STATUS
    )
    assert worker_step["activation_decision"] == "approved_for_manual_apply"
    assert worker_step["developer_approval_recorded"] is True
    assert worker_step["target_count"] == 2
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0

    authorization = authorized["generation_runtime_activation_authorization"]
    assert authorization["authorization_status"] == (
        RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_STATUS
    )
    assert authorization["source_report_ref"]["artifact_kind"] == (
        RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND
    )
    assert authorization["decision"]["developer_approval_recorded"] is True
    assert authorization["activation_gate"]["activation_allowed"] is False
    assert authorization["activation_gate"]["runtime_apply_allowed"] is False
    assert authorization["activation_gate"]["world_mutation_allowed"] is False
    assert authorization["safety"]["activates_runtime"] is False

    ledger = authorized["generation_artifact_ledger"]
    assert ledger["summary"]["artifact_kind_counts"][
        RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_KIND
    ] == 1
    assert ledger["summary"]["status_counts"][
        RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_STATUS
    ] == 1
    assert ledger["summary"]["activation_allowed_count"] == 0
    item = {
        cache_item["schedule_item_id"]: cache_item
        for cache_item in authorized["generation_prefetch_cache"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == RUNTIME_ACTIVATION_AUTHORIZATION_CACHE_STATUS
    assert item["runtime_activation_authorization"]["authorization_recorded"] is True
    assert item["runtime_activation_authorization"]["activation_allowed"] is False
    assert item["runtime_activation_authorization"]["runtime_apply_allowed"] is False
    gate = {
        gate_item["schedule_item_id"]: gate_item
        for gate_item in authorized["generation_activation_gate"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert gate["activation_status"] == "blocked_runtime_activation_apply_required"
    assert gate["activation_allowed"] is False

    daemon = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/daemon-readiness")
    )["generation_daemon_readiness"]
    actions = {action["action"] for action in daemon["recommended_next_actions"]}
    assert "wait_for_runtime_activation_apply_gate" in actions
    assert "record_runtime_activation_authorization" not in actions
    assert daemon["summary"]["runtime_activation_authorization_count"] == 1
    assert daemon["summary"]["activation_allowed_count"] == 0

    authorized_again = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "record-runtime-activation-authorization",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    assert _session_state_counts(raw_conn, sid) == after_counts
    assert authorized_again["generation_artifact_ledger"]["summary"][
        "artifact_kind_counts"
    ][RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_KIND] == 1


def test_runtime_activation_readiness_chain_runs_three_review_only_steps(
    client,
    raw_conn,
):
    missing = client.post(
        "/api/sessions/missing-session/generation-schedule/workers/"
        "run-runtime-activation-readiness-chain"
    )
    assert missing.status_code == 404

    sid = _create_session(client)
    no_run = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "run-runtime-activation-readiness-chain"
    )
    assert no_run.status_code == 409
    assert "generation schedule run is required" in no_run.text

    run_payload = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    run_id = run_payload["generation_schedule_run"]["run_id"]
    no_candidate = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/"
        "run-runtime-activation-readiness-chain"
    )
    assert no_candidate.status_code == 409
    assert "no promotion-allowed or shared-cache reuse candidate" in no_candidate.text

    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{sid}_provider_artifact_promotion_report_chain",
            "run_id": run_id,
            "session_id": sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_runtime_chain",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    before_counts = _session_state_counts(raw_conn, sid)

    chained = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "run-runtime-activation-readiness-chain",
            json={
                "worker_id": "runtime-readiness-chain-test",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )

    after_counts = _session_state_counts(raw_conn, sid)
    assert after_counts == {
        **before_counts,
        "generation_artifact_ledger": before_counts["generation_artifact_ledger"] + 3,
    }
    worker_step = chained["worker_step"]
    assert worker_step["status"] == "completed_review_only"
    assert worker_step["worker_mode"] == "generation_runtime_activation_readiness_chain"
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["step_count"] == 3
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0

    assert [step["name"] for step in chained["chain_steps"]] == [
        "prepare_runtime_build_request",
        "run_runtime_artifact_build_report",
        "record_runtime_activation_authorization",
    ]
    assert all(step["provider_call_count"] == 0 for step in chained["chain_steps"])
    assert all(step["world_mutation_count"] == 0 for step in chained["chain_steps"])
    assert chained["generation_runtime_build_request"]["request_status"] == (
        RUNTIME_BUILD_REQUEST_LEDGER_STATUS
    )
    assert chained["generation_runtime_artifact_build_report"]["report_status"] == (
        RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS
    )
    assert chained["generation_runtime_activation_authorization"][
        "authorization_status"
    ] == RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_STATUS

    ledger_summary = chained["generation_artifact_ledger"]["summary"]
    assert ledger_summary["artifact_kind_counts"][RUNTIME_BUILD_REQUEST_LEDGER_KIND] == 1
    assert ledger_summary["artifact_kind_counts"][
        RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND
    ] == 1
    assert ledger_summary["artifact_kind_counts"][
        RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_KIND
    ] == 1
    assert ledger_summary["activation_allowed_count"] == 0
    item = {
        cache_item["schedule_item_id"]: cache_item
        for cache_item in chained["generation_prefetch_cache"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == RUNTIME_ACTIVATION_AUTHORIZATION_CACHE_STATUS
    gate = {
        gate_item["schedule_item_id"]: gate_item
        for gate_item in chained["generation_activation_gate"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert gate["activation_status"] == "blocked_runtime_activation_apply_required"
    assert gate["activation_allowed"] is False

    daemon = _payload(
        client.get(f"/api/sessions/{sid}/generation-schedule/daemon-readiness")
    )["generation_daemon_readiness"]
    actions = {action["action"] for action in daemon["recommended_next_actions"]}
    assert "wait_for_runtime_activation_apply_gate" in actions
    assert "run_runtime_activation_readiness_chain" not in actions

    chained_again = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/"
            "run-runtime-activation-readiness-chain",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    assert _session_state_counts(raw_conn, sid) == after_counts
    assert chained_again["generation_artifact_ledger"]["summary"]["item_count"] == (
        ledger_summary["item_count"]
    )


def test_prepare_runtime_build_request_from_shared_cache_reuse_candidate(client):
    source_sid = _create_session(client)
    source_run = _payload(
        client.post(f"/api/sessions/{source_sid}/generation-schedule/runs")
    )
    upsert_generation_artifact_ledger(
        {
            "schema_version": "generation_artifact_ledger_entry.v0.1",
            "ledger_id": f"gled_{source_sid}_provider_artifact_promotion_report_runtime_reuse",
            "run_id": source_run["generation_schedule_run"]["run_id"],
            "session_id": source_sid,
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "artifact_kind": "provider_artifact_promotion_report",
            "source_id": "ppromo_runtime_reuse",
            "status": "promotion_allowed",
            "created_at": "2026-07-03T00:00:00Z",
            "updated_at": "2026-07-03T00:00:00Z",
            "compact": {
                "promotion_allowed": True,
                "promotion_decision": "approved_for_runtime_package_build",
                "required_next_actions": ["runtime_package_build"],
                "promotion_gate": {"blocked_reason": None},
            },
        }
    )
    _payload(
        client.post(
            f"/api/sessions/{source_sid}/generation-schedule/workers/"
            "index-shared-prefetch-cache"
        )
    )

    target_sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{target_sid}/generation-schedule/runs"))
    _payload(
        client.post(
            f"/api/sessions/{target_sid}/generation-schedule/workers/"
            "record-shared-prefetch-cache-reuse-candidate",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )
    prepared = _payload(
        client.post(
            f"/api/sessions/{target_sid}/generation-schedule/workers/"
            "prepare-runtime-build-request",
            json={"schedule_item_id": "sched_next_map_visual_prefetch"},
        )
    )

    worker_step = prepared["worker_step"]
    assert worker_step["source_artifact_kind"] == REUSE_CANDIDATE_LEDGER_KIND
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    request = prepared["generation_runtime_build_request"]
    assert request["source_candidate_ref"]["artifact_kind"] == REUSE_CANDIDATE_LEDGER_KIND
    assert request["build_targets"][
        "world_state_delta_transaction_build_requested"
    ] is True
    prefetch_summary = prepared["generation_prefetch_cache"]["summary"]
    assert prefetch_summary["shared_cache_reuse_candidate_count"] == 1
    assert prefetch_summary["runtime_build_request_count"] == 1
    item = {
        cache_item["schedule_item_id"]: cache_item
        for cache_item in prepared["generation_prefetch_cache"]["items"]
    }["sched_next_map_visual_prefetch"]
    assert item["cache_status"] == RUNTIME_BUILD_REQUEST_CACHE_STATUS
    assert item["runtime_build_request"]["source_candidate_ref"]["artifact_kind"] == (
        REUSE_CANDIDATE_LEDGER_KIND
    )
    daemon = _payload(
        client.get(
            f"/api/sessions/{target_sid}/generation-schedule/daemon-readiness"
        )
    )["generation_daemon_readiness"]
    assert daemon["manual_tick_status"] == "ready_to_dispatch_queued_provider_review_items"
    assert "run_runtime_artifact_build_report" in {
        action["action"] for action in daemon["recommended_next_actions"]
    }


def test_review_only_dispatcher_drain_stops_when_no_items_remain(client):
    sid = _create_session(client)
    drained = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
            json={"worker_id": "dispatcher-drain-all", "max_items": 10},
        )
    )

    worker_step = drained["worker_step"]
    assert worker_step["status"] == "drained_review_only"
    assert worker_step["dispatched_count"] == 4
    assert worker_step["idle_reached"] is True
    assert worker_step["stop_reason"] == "no_eligible_items"
    assert worker_step["remaining_eligible_count"] == 0
    assert drained["generation_schedule_queue"]["summary"]["claimable_count"] == 0
    assert drained["generation_schedule_queue"]["summary"]["waiting_review_count"] == 4
    assert drained["generation_artifact_ledger"]["summary"]["item_count"] == 16

    drained_again = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
            json={"worker_id": "dispatcher-drain-empty"},
        )
    )
    assert drained_again["worker_step"]["status"] == "idle"
    assert drained_again["worker_step"]["dispatched_count"] == 0
    assert drained_again["worker_step"]["idle_reached"] is True
    assert drained_again["worker_step"]["stop_reason"] == "no_eligible_items"
    assert drained_again["worker_step"]["remaining_eligible_count"] == 0
    assert drained_again["generation_artifact_ledger"]["summary"]["item_count"] == 16


def test_review_only_dispatcher_drain_rejects_targeted_metadata(client):
    sid = _create_session(client)
    rejected = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
        json={
            "worker_id": "dispatcher-drain-targeted",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )
    assert rejected.status_code == 409
    assert "does not accept targeted metadata" in rejected.json()["detail"]

    rejected_auth = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
        json={
            "worker_id": "dispatcher-drain-auth",
            "authorization_ref": "auth_should_not_be_reused",
        },
    )
    assert rejected_auth.status_code == 409
    assert "authorization_ref" in rejected_auth.json()["detail"]


def test_review_only_dispatcher_drain_rejects_invalid_budget(client):
    sid = _create_session(client)
    too_small = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
        json={"worker_id": "dispatcher-drain-small", "max_items": 0},
    )
    assert too_small.status_code == 422

    too_large = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-dispatcher-drain",
        json={"worker_id": "dispatcher-drain-large", "max_items": 17},
    )
    assert too_large.status_code == 422


def test_review_only_background_executor_tick_wraps_dispatcher_drain(
    client,
    raw_conn,
):
    sid = _create_session(client)
    tick = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-background-executor-tick",
            json={"worker_id": "background-tick", "note": "bounded tick"},
        )
    )

    worker_step = tick["worker_step"]
    assert worker_step["status"] == "ticked_review_only"
    assert worker_step["worker_mode"] == "review_only_background_executor_tick"
    assert worker_step["trigger"] == "manual_api_tick"
    assert worker_step["created_generation_schedule_run"] is True
    assert worker_step["max_items"] == 2
    assert worker_step["dispatched_count"] == 2
    assert worker_step["stop_reason"] == "budget_exhausted"
    assert worker_step["remaining_eligible_count"] == 2
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["promotion_allowed_count"] == 0
    assert worker_step["staging_performed"] is False
    assert worker_step["promotion_performed"] is False
    assert worker_step["queue_completed_count"] == 0
    assert [step["schedule_item_id"] for step in tick["dispatcher_steps"]] == [
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
    ]

    background_tick = tick["background_executor_tick"]
    assert background_tick["tick_mode"] == "review_only_background_executor_tick"
    assert background_tick["dispatcher_worker_step"]["worker_mode"] == (
        "review_only_dispatcher_drain"
    )
    assert background_tick["safety"] == {
        "api_reads_env": False,
        "api_calls_provider": False,
        "api_stages_provider_artifacts": False,
        "api_promotes_provider_artifacts": False,
        "api_completes_queue_items": False,
        "api_writes_world_state": False,
        "api_activates_runtime": False,
        "prompt_body_stored": False,
        "provider_response_body_stored": False,
    }

    prefetch_summary = tick["generation_prefetch_cache"]["summary"]
    assert prefetch_summary["item_count"] == 8
    assert prefetch_summary["review_only_envelope_ready_count"] == 2
    assert prefetch_summary["staged_or_reviewed_count"] == 0
    assert prefetch_summary["runtime_ready_count"] == 0
    assert prefetch_summary["provider_call_count_by_this_request"] == 0
    assert prefetch_summary["world_mutation_count_by_this_request"] == 0
    assert prefetch_summary["activation_allowed_count"] == 0
    assert prefetch_summary["promotion_allowed_count"] == 0
    assert background_tick["prefetch_cache_summary"] == prefetch_summary

    ledger_summary = tick["generation_artifact_ledger"]["summary"]
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 2,
        "provider_execution_authorization": 2,
        "provider_adapter_execution_receipt": 2,
        "provider_output_envelope": 2,
    }
    assert "provider_artifact_staging" not in tick
    assert "provider_artifact_promotion_report" not in tick

    queue_statuses = {
        item["schedule_item_id"]: item["status"]
        for item in tick["generation_schedule_queue"]["items"]
    }
    assert queue_statuses["sched_stage05_worldline_prefetch"] == "waiting_review"
    assert queue_statuses["sched_next_map_visual_prefetch"] == "waiting_review"
    assert queue_statuses["sched_video_frame_background_compile"] == "queued"
    assert queue_statuses["sched_frontend_mock_sprite_repair_lazy"] == "queued"
    ledger_kinds = {
        row["artifact_kind"]
        for row in raw_conn.execute(
            "SELECT artifact_kind FROM generation_artifact_ledger WHERE session_id = ?",
            (sid,),
        ).fetchall()
    }
    assert ledger_kinds == {
        "generation_executor_run_request",
        "provider_execution_authorization",
        "provider_adapter_execution_receipt",
        "provider_output_envelope",
    }


def test_review_only_background_executor_tick_rejects_unsafe_metadata(client):
    sid = _create_session(client)
    targeted = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-background-executor-tick",
        json={
            "worker_id": "background-tick-targeted",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )
    assert targeted.status_code == 409
    assert "does not accept targeted metadata" in targeted.json()["detail"]

    too_large = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-background-executor-tick",
        json={"worker_id": "background-tick-large", "max_items": 9},
    )
    assert too_large.status_code == 409
    assert "max_items must be between 1 and 8" in too_large.json()["detail"]


def test_review_only_background_handoff_tick_exports_runner_outbox(
    client,
    raw_conn,
):
    sid = _create_session(client)
    handoff_tick = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-background-handoff-tick",
            json={"worker_id": "background-handoff-tick", "note": "export outbox"},
        )
    )

    worker_step = handoff_tick["worker_step"]
    assert worker_step["status"] == "handoff_tick_exported"
    assert worker_step["worker_mode"] == "review_only_background_handoff_tick"
    assert worker_step["max_items"] == 2
    assert worker_step["dispatched_count"] == 2
    assert worker_step["runner_handoff_count"] == 2
    assert worker_step["stop_reason"] == "budget_exhausted"
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["promotion_allowed_count"] == 0
    assert worker_step["staging_performed"] is False
    assert worker_step["promotion_performed"] is False
    assert worker_step["queue_completed_count"] == 0

    background_handoff = handoff_tick["background_handoff_tick"]
    assert background_handoff["tick_mode"] == "review_only_background_handoff_tick"
    assert background_handoff["handoff_mode"] == "external_runner_required"
    assert background_handoff["runner_handoff_count"] == 2
    assert background_handoff["background_executor_tick"]["tick_mode"] == (
        "review_only_background_executor_tick"
    )
    assert background_handoff["safety"] == {
        "api_reads_env": False,
        "api_calls_provider": False,
        "api_runs_provider_adapter": False,
        "api_stages_provider_artifacts": False,
        "api_promotes_provider_artifacts": False,
        "api_completes_queue_items": False,
        "api_writes_world_state": False,
        "api_activates_runtime": False,
        "prompt_body_included": False,
        "provider_response_body_included": False,
        "live_templates_require_external_explicit_authorization": True,
    }

    handoffs = handoff_tick["runner_handoffs"]
    assert [handoff["source"]["schedule_item_id"] for handoff in handoffs] == [
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
    ]
    outbox = handoff_tick["provider_adapter_runner_handoff_outbox"]
    assert validate_provider_adapter_runner_handoff_outbox(outbox) == []
    assert outbox["schema_version"] == "provider_adapter_runner_handoff_outbox.v0.1"
    assert outbox["handoff_mode"] == "external_runner_required"
    assert outbox["review_only"] is True
    assert outbox["source"]["worker_mode"] == "review_only_background_handoff_tick"
    assert outbox["source"]["run_id"] == worker_step["run_id"]
    assert outbox["source"]["max_items"] == 2
    assert outbox["source"]["dispatched_count"] == 2
    assert outbox["runner_handoff_count"] == 2
    assert outbox["runner_handoffs"] == handoffs
    assert outbox["import_contract"] == {
        "endpoint": (
            "/api/sessions/{session_id}/generation-schedule/workers/"
            "import-provider-adapter-runner-output"
        ),
        "method": "POST",
        "required_body_fields": [
            "schedule_item_id",
            "authorization_ref",
            "receipt_path",
            "envelope_path",
        ],
        "post_import_gate": "provider_artifact_staging_or_promotion_review_required",
    }
    assert all(handoff["schema_version"] == "provider_adapter_runner_handoff.v0.1" for handoff in handoffs)
    assert all(handoff["handoff_mode"] == "external_runner_required" for handoff in handoffs)
    assert all(handoff["review_only"] is True for handoff in handoffs)
    assert all(
        handoff["runner_inputs"]["executor_request"]["source"][
            "schedule_item_id"
        ]
        == handoff["source"]["schedule_item_id"]
        for handoff in handoffs
    )
    assert all(
        handoff["runner_inputs"]["provider_execution_authorization"][
            "authorization_ref"
        ]
        == handoff["source"]["authorization_ref"]
        for handoff in handoffs
    )
    assert all(
        handoff["import_after_runner"]["body"]["schedule_item_id"]
        == handoff["source"]["schedule_item_id"]
        for handoff in handoffs
    )
    assert all(
        handoff["import_after_runner"]["body"]["authorization_ref"]
        == handoff["source"]["authorization_ref"]
        for handoff in handoffs
    )
    assert all(
        handoff["suggested_paths"]["executor_request_path"].startswith("/tmp/")
        for handoff in handoffs
    )
    assert all(
        "--live" in handoff["command_templates"]["live_llm_text"]
        and "--live" in handoff["command_templates"]["live_image"]
        for handoff in handoffs
    )
    assert all(
        "--mode" in handoff["command_templates"]["video_boundary"]
        and "video" in handoff["command_templates"]["video_boundary"]
        and "--live" not in handoff["command_templates"]["video_boundary"]
        and "<authorized-dotenv-path>"
        not in handoff["command_templates"]["video_boundary"]
        for handoff in handoffs
    )
    forbidden_keys = {"raw_prompt", "provider_response", "provider_body", "api_key", "secret"}
    assert not (set(_walk_keys(handoff_tick)) & forbidden_keys)

    ledger_summary = handoff_tick["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 8
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 2,
        "provider_execution_authorization": 2,
        "provider_adapter_execution_receipt": 2,
        "provider_output_envelope": 2,
    }
    ledger_kinds = {
        row["artifact_kind"]
        for row in raw_conn.execute(
            "SELECT artifact_kind FROM generation_artifact_ledger WHERE session_id = ?",
            (sid,),
        ).fetchall()
    }
    assert ledger_kinds == {
        "generation_executor_run_request",
        "provider_execution_authorization",
        "provider_adapter_execution_receipt",
        "provider_output_envelope",
    }


def test_review_only_background_handoff_tick_rejects_unsafe_metadata(client):
    sid = _create_session(client)
    targeted = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-background-handoff-tick",
        json={
            "worker_id": "background-handoff-targeted",
            "authorization_ref": "auth_should_not_be_reused",
        },
    )
    assert targeted.status_code == 409
    assert "does not accept targeted metadata" in targeted.json()["detail"]

    too_large = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-review-only-background-handoff-tick",
        json={"worker_id": "background-handoff-large", "max_items": 9},
    )
    assert too_large.status_code == 409
    assert "max_items must be between 1 and 8" in too_large.json()["detail"]


def test_provider_adapter_runner_output_import_records_local_files(client, tmp_path):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(client, sid, "runner-import")
    outputs = _write_runner_outputs(
        tmp_path,
        chain["executor_request"],
        chain["authorization"],
    )

    imported = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/import-provider-adapter-runner-output",
            json={
                "worker_id": "runner-output-import",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": chain["authorization"]["authorization_ref"],
                "receipt_path": str(outputs["receipt_path"]),
                "envelope_path": str(outputs["envelope_path"]),
            },
        )
    )

    worker_step = imported["worker_step"]
    assert worker_step["status"] == "imported"
    assert worker_step["worker_mode"] == "provider_adapter_runner_output_import"
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["authorization_ref"] == chain["authorization"]["authorization_ref"]
    assert worker_step["upstream_request_id"] == chain["executor_request"]["request_id"]
    assert worker_step["execution_receipt_id"] == outputs["receipt"][
        "execution_receipt_id"
    ]
    assert worker_step["envelope_id"] == outputs["envelope"]["envelope_id"]
    assert worker_step["import_refs"]["receipt_path"] == str(outputs["receipt_path"])
    assert worker_step["import_refs"]["envelope_path"] == str(outputs["envelope_path"])
    assert imported["provider_adapter_execution_receipt"]["execution"]["mode"] == (
        "fixture_backed_no_provider_call"
    )
    assert imported["provider_output_envelope"]["provider_call"]["performed"] is False
    assert imported["provider_output_envelope"]["activation_gate"][
        "activation_allowed"
    ] is False

    ledger_summary = imported["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 4
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 1,
        "provider_execution_authorization": 1,
        "provider_adapter_execution_receipt": 1,
        "provider_output_envelope": 1,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0


def test_provider_adapter_runner_output_import_rejects_mismatch(client, tmp_path):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(client, sid, "runner-import-mismatch")
    outputs = _write_runner_outputs(
        tmp_path,
        chain["executor_request"],
        chain["authorization"],
    )
    envelope = outputs["envelope"].copy()
    envelope["source"] = {**envelope["source"], "schedule_item_id": "wrong_item"}
    bad_envelope_path = tmp_path / "runner.bad_envelope.json"
    bad_envelope_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    imported = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/import-provider-adapter-runner-output",
        json={
            "worker_id": "runner-output-import-mismatch",
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "authorization_ref": chain["authorization"]["authorization_ref"],
            "receipt_path": str(outputs["receipt_path"]),
            "envelope_path": str(bad_envelope_path),
        },
    )
    assert imported.status_code == 409
    assert "do not match ledger authorization chain" in imported.json()["detail"]


def test_provider_adapter_runner_output_import_rejects_sensitive_keys(client, tmp_path):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(client, sid, "runner-import-sensitive")
    outputs = _write_runner_outputs(
        tmp_path,
        chain["executor_request"],
        chain["authorization"],
    )
    receipt = outputs["receipt"].copy()
    receipt["raw_prompt"] = "must not be accepted"
    bad_receipt_path = tmp_path / "runner.bad_receipt.json"
    bad_receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    imported = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/import-provider-adapter-runner-output",
        json={
            "worker_id": "runner-output-import-sensitive",
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "authorization_ref": chain["authorization"]["authorization_ref"],
            "receipt_path": str(bad_receipt_path),
            "envelope_path": str(outputs["envelope_path"]),
        },
    )
    assert imported.status_code == 409
    assert "forbidden sensitive keys" in imported.json()["detail"]


def test_provider_artifact_review_output_import_records_staging_and_promotion(
    client,
    tmp_path,
):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(
        client,
        sid,
        "artifact-review-import",
    )
    outputs = _write_runner_outputs(
        tmp_path,
        chain["executor_request"],
        chain["authorization"],
        with_artifact_output=True,
    )
    runner_import = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/import-provider-adapter-runner-output",
            json={
                "worker_id": "runner-output-before-review-import",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": chain["authorization"]["authorization_ref"],
                "receipt_path": str(outputs["receipt_path"]),
                "envelope_path": str(outputs["envelope_path"]),
            },
        )
    )
    review_outputs = _write_artifact_review_outputs(
        tmp_path,
        outputs["envelope"],
        outputs["envelope_path"],
    )

    imported = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/import-provider-artifact-review-output",
            json={
                "worker_id": "artifact-review-output-import",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "staging_path": str(review_outputs["staging_path"]),
                "promotion_report_path": str(review_outputs["promotion_path"]),
            },
        )
    )

    worker_step = imported["worker_step"]
    assert worker_step["status"] == "imported"
    assert worker_step["worker_mode"] == "provider_artifact_review_output_import"
    assert worker_step["provider_call_count"] == 0
    assert worker_step["world_mutation_count"] == 0
    assert worker_step["activation_allowed_count"] == 0
    assert worker_step["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert worker_step["source_envelope_id"] == outputs["envelope"]["envelope_id"]
    assert worker_step["staging_manifest_id"] == review_outputs["staging"][
        "manifest_id"
    ]
    assert worker_step["promotion_report_id"] == review_outputs["promotion"][
        "report_id"
    ]
    assert worker_step["promotion_allowed"] is False
    assert worker_step["import_refs"]["staging_path"] == str(
        review_outputs["staging_path"]
    )
    assert worker_step["import_refs"]["promotion_report_path"] == str(
        review_outputs["promotion_path"]
    )
    assert imported["provider_output_envelope"]["envelope_id"] == (
        outputs["envelope"]["envelope_id"]
    )
    assert imported["provider_artifact_staging"]["manifest_id"] == (
        review_outputs["staging"]["manifest_id"]
    )
    assert imported["provider_artifact_staging"]["promotion_gate"][
        "promotion_allowed"
    ] is False
    assert imported["provider_artifact_promotion_report"]["report_id"] == (
        review_outputs["promotion"]["report_id"]
    )
    assert imported["provider_artifact_promotion_report"][
        "promotion_decision"
    ] == "blocked_review_required"
    assert imported["provider_artifact_promotion_report"][
        "promotion_allowed"
    ] is False

    ledger_summary = imported["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 6
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 1,
        "provider_execution_authorization": 1,
        "provider_adapter_execution_receipt": 1,
        "provider_output_envelope": 1,
        "provider_artifact_staging_manifest": 1,
        "provider_artifact_promotion_report": 1,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0


def test_provider_artifact_review_output_import_requires_matching_envelope(
    client,
    tmp_path,
):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(
        client,
        sid,
        "artifact-review-missing-envelope",
    )
    outputs = _write_runner_outputs(
        tmp_path,
        chain["executor_request"],
        chain["authorization"],
        with_artifact_output=True,
    )
    review_outputs = _write_artifact_review_outputs(
        tmp_path,
        outputs["envelope"],
        outputs["envelope_path"],
    )

    imported = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/import-provider-artifact-review-output",
        json={
            "worker_id": "artifact-review-output-import",
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "staging_path": str(review_outputs["staging_path"]),
            "promotion_report_path": str(review_outputs["promotion_path"]),
        },
    )

    assert imported.status_code == 409
    assert "matching provider output envelope" in imported.json()["detail"]


def test_provider_artifact_review_output_import_rejects_staging_ref_mismatch(
    client,
    tmp_path,
):
    sid = _create_session(client)
    chain = _prepare_provider_authorization_chain(
        client,
        sid,
        "artifact-review-staging-mismatch",
    )
    outputs = _write_runner_outputs(
        tmp_path,
        chain["executor_request"],
        chain["authorization"],
        with_artifact_output=True,
    )
    runner_import = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/import-provider-adapter-runner-output",
            json={
                "worker_id": "runner-output-before-review-mismatch",
                "schedule_item_id": "sched_next_map_visual_prefetch",
                "authorization_ref": chain["authorization"]["authorization_ref"],
                "receipt_path": str(outputs["receipt_path"]),
                "envelope_path": str(outputs["envelope_path"]),
            },
        )
    )
    review_outputs = _write_artifact_review_outputs(
        tmp_path,
        outputs["envelope"],
        outputs["envelope_path"],
    )
    wrong_staging_path = tmp_path / "wrong-artifact.staging.json"
    wrong_staging_path.write_text(
        json.dumps(review_outputs["staging"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    imported = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/import-provider-artifact-review-output",
        json={
            "worker_id": "artifact-review-output-import",
            "schedule_item_id": "sched_next_map_visual_prefetch",
            "staging_path": str(wrong_staging_path),
            "promotion_report_path": str(review_outputs["promotion_path"]),
        },
    )

    assert imported.status_code == 409
    assert "source_staging_ref must reference staging_path" in imported.json()["detail"]


def test_provider_artifact_staging_supports_image_failure_profile(client):
    sid = _create_session(client)
    image_authorization_ref = "auth_sched_next_map_visual_prefetch_image_fixture_001"
    chain = _prepare_provider_artifact_staging_chain(
        client,
        sid,
        "image-failure-profile",
        authorization_ref=image_authorization_ref,
    )
    artifact_stage = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
            json={
                "worker_id": "image-failure-ledger",
                "note": "stage image failure evidence",
                "artifact_profile": "image_failure",
            },
        )
    )

    assert artifact_stage["worker_step"]["status"] == "staged"
    assert artifact_stage["worker_step"]["artifact_profile"] == "image_failure"
    assert artifact_stage["worker_step"]["authorization_ref"] == image_authorization_ref
    assert artifact_stage["worker_step"]["provider_call_count"] == 0
    assert artifact_stage["worker_step"]["world_mutation_count"] == 0
    assert artifact_stage["worker_step"]["activation_allowed_count"] == 0
    assert artifact_stage["worker_step"]["fixture_refs"] == {
        "provider_output_envelope": (
            "examples/provider_artifact_staging/"
            "p1b_provider_image_artifact_staging.source_envelope.json"
        ),
        "provider_artifact_staging": (
            "examples/provider_artifact_staging/"
            "p1b_provider_image_artifact_staging.example.json"
        ),
        "provider_artifact_promotion_report": (
            "examples/provider_artifact_staging/"
            "p1b_provider_image_artifact_promotion_report.example.json"
        ),
    }
    assert artifact_stage["generation_executor_run_request"]["request_id"] == (
        chain["executor_request"]["request_id"]
    )
    assert artifact_stage["provider_execution_authorization"]["authorization_ref"] == (
        image_authorization_ref
    )
    assert artifact_stage["provider_adapter_execution_receipt"][
        "execution_receipt_id"
    ] == chain["adapter_receipt"]["execution_receipt_id"]
    assert artifact_stage["provider_output_envelope"]["envelope_id"] == (
        "pout_image_candidate_old_signal_tower_001"
    )
    assert artifact_stage["provider_output_envelope"]["provider_call"][
        "authorization_ref"
    ] == image_authorization_ref
    assert artifact_stage["provider_artifact_staging"]["manifest_id"] == (
        "pstaging_old_signal_tower_image_001"
    )
    assert artifact_stage["provider_artifact_staging"]["staging_status"] == (
        "validation_failed"
    )
    assert artifact_stage["provider_artifact_staging"]["gate_statuses"][
        "media_gate"
    ] == "failed"
    assert artifact_stage["provider_artifact_staging"]["gate_statuses"][
        "semantic_gate"
    ] == "failed"
    assert artifact_stage["provider_artifact_promotion_report"]["report_id"] == (
        "ppromo_old_signal_tower_image_001"
    )
    assert artifact_stage["provider_artifact_promotion_report"][
        "promotion_decision"
    ] == "blocked_validation_failed"
    assert artifact_stage["provider_artifact_promotion_report"][
        "promotion_allowed"
    ] is False

    ledger_summary = artifact_stage["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 6
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 1,
        "provider_execution_authorization": 1,
        "provider_adapter_execution_receipt": 1,
        "provider_output_envelope": 1,
        "provider_artifact_staging_manifest": 1,
        "provider_artifact_promotion_report": 1,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0


def test_provider_artifact_staging_rejects_unknown_profile(client):
    sid = _create_session(client)
    _prepare_provider_artifact_staging_chain(client, sid, "unknown-profile")
    stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={
            "worker_id": "unknown-profile-ledger",
            "artifact_profile": "not_a_profile",
        },
    )
    assert stage.status_code == 409
    assert "unknown provider artifact profile" in stage.json()["detail"]


def test_fixture_executor_chain_runs_default_profile_end_to_end(client):
    sid = _create_session(client)
    chain = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-fixture-executor-chain",
            json={
                "worker_id": "default-chain",
                "artifact_profile": "default",
                "note": "run default fixture chain",
            },
        )
    )

    executor_chain = chain["executor_chain"]
    assert executor_chain["status"] == "completed_review_only_promotion_blocked"
    assert executor_chain["created_generation_schedule_run"] is True
    assert executor_chain["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert executor_chain["artifact_profile"] == "default"
    assert executor_chain["authorization_ref"] == (
        "auth_sched_next_map_visual_prefetch_fixture_001"
    )
    assert executor_chain["provider_call_count"] == 0
    assert executor_chain["world_mutation_count"] == 0
    assert executor_chain["activation_allowed_count"] == 0
    assert executor_chain["promotion_allowed_count"] == 0
    assert chain["steps"]["dry_run_step"]["status"] == "processed"
    assert chain["steps"]["live_executor_guard"]["status"] == "blocked"
    assert chain["steps"]["generation_executor_run_request"]["status"] == "prepared"
    assert chain["steps"]["provider_execution_authorization"]["status"] == "authorized"
    assert chain["steps"]["provider_adapter_execution_receipt"]["status"] == (
        "adapter_recorded"
    )
    assert chain["steps"]["provider_artifact_staging"]["status"] == "staged"
    assert chain["provider_output_envelope"]["envelope_id"] == (
        "pout_performed_stage05_map_visual_001"
    )
    assert chain["provider_artifact_promotion_report"]["promotion_allowed"] is False

    ledger_summary = chain["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 6
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0


def test_fixture_executor_chain_supports_image_failure_profile(client):
    sid = _create_session(client)
    chain = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-fixture-executor-chain",
            json={
                "worker_id": "image-failure-chain",
                "artifact_profile": "image_failure",
            },
        )
    )

    executor_chain = chain["executor_chain"]
    assert executor_chain["artifact_profile"] == "image_failure"
    assert executor_chain["schedule_item_id"] == "sched_next_map_visual_prefetch"
    assert executor_chain["authorization_ref"] == (
        "auth_sched_next_map_visual_prefetch_image_fixture_001"
    )
    assert chain["provider_output_envelope"]["envelope_id"] == (
        "pout_image_candidate_old_signal_tower_001"
    )
    assert chain["provider_artifact_staging"]["staging_status"] == (
        "validation_failed"
    )
    assert chain["provider_artifact_staging"]["gate_statuses"][
        "media_gate"
    ] == "failed"
    assert chain["provider_artifact_promotion_report"]["promotion_decision"] == (
        "blocked_validation_failed"
    )
    assert chain["provider_artifact_promotion_report"]["promotion_allowed"] is False
    assert chain["generation_artifact_ledger"]["summary"]["item_count"] == 6


def test_fixture_executor_chain_rejects_mismatched_schedule_item(client):
    sid = _create_session(client)
    stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/run-fixture-executor-chain",
        json={
            "worker_id": "mismatch-chain",
            "artifact_profile": "image_failure",
            "schedule_item_id": "sched_stage05_worldline_prefetch",
        },
    )
    assert stage.status_code == 409
    assert "does not match requested schedule_item_id" in stage.json()["detail"]

    latest = _payload(client.get(f"/api/sessions/{sid}/generation-schedule/runs/latest"))
    assert latest["generation_schedule_run"] is None


def test_campaign_router_prefetches_next_node_without_provider_calls(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    router_payload = _payload(client.get(f"/api/sessions/{sid}/campaign-router"))
    router = router_payload["campaign_router"]
    assert router["schema_version"] == "campaign_router.v0.1"
    assert router["router_mode"] == "fixture_backed_thin_router"
    assert router["current"]["node_id"] == "gray_lantern_station"
    assert router["current"]["playable"] is True
    assert router["next"]["node_id"] == "lamp_wick_store"
    assert router["next"]["asset_handle"]["status"] == "ready"
    assert router["scheduler_signal"]["latest_run_id"] is None
    assert router["boundary"]["provider_calls"] is False
    assert router["boundary"]["world_mutations"] is False

    prefetch_payload = _payload(
        client.post(f"/api/sessions/{sid}/campaign-router/prefetch-next")
    )
    request = prefetch_payload["prefetch_request"]
    assert request["target_node_id"] == "lamp_wick_store"
    assert request["created_generation_schedule_run"] is True
    assert request["provider_call_count"] == 0
    assert request["world_mutation_count"] == 0
    assert prefetch_payload["worker_step"]["status"] == "processed"
    assert prefetch_payload["generation_schedule_queue_item"]["status"] in {
        "completed",
        "waiting_review",
    }
    assert prefetch_payload["campaign_router"]["scheduler_signal"]["latest_run_id"]

    _payload(client.post(f"/api/sessions/{sid}/battles/gray_lantern_station/results"))
    after_battle_payload = _payload(client.get(f"/api/sessions/{sid}/campaign-router"))
    after_router = after_battle_payload["campaign_router"]
    assert after_router["run_progress"]["phase"] == "post_first_defense"
    assert after_router["current"]["node_id"] == "lamp_wick_store"
    assert after_router["next"]["node_id"] == "old_signal_tower"


def test_campaign_router_dispatcher_prefetch_drains_review_only_items(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    prefetch_payload = _payload(
        client.post(
            f"/api/sessions/{sid}/campaign-router/prefetch-next-dispatcher-drain",
            json={"worker_id": "router-dispatcher-prefetch", "max_items": 2},
        )
    )
    request = prefetch_payload["prefetch_request"]
    assert request["status"] == "requested"
    assert request["target_node_id"] == "lamp_wick_store"
    assert request["created_generation_schedule_run"] is True
    assert request["prefetch_mode"] == "review_only_dispatcher_drain"
    assert request["max_items"] == 2
    assert request["dispatched_count"] == 2
    assert request["stop_reason"] == "budget_exhausted"
    assert request["remaining_eligible_count"] == 2
    assert request["provider_call_count"] == 0
    assert request["world_mutation_count"] == 0
    assert request["activation_allowed_count"] == 0
    assert request["promotion_allowed_count"] == 0

    worker_step = prefetch_payload["worker_step"]
    assert worker_step["status"] == "drained_review_only"
    assert worker_step["worker_mode"] == "review_only_dispatcher_drain"
    assert worker_step["dispatched_count"] == 2
    assert [step["schedule_item_id"] for step in prefetch_payload["dispatcher_steps"]] == [
        "sched_stage05_worldline_prefetch",
        "sched_next_map_visual_prefetch",
    ]
    queue_summary = prefetch_payload["generation_schedule_queue"]["summary"]
    assert queue_summary["waiting_review_count"] == 2
    assert queue_summary["claimable_count"] == 2
    ledger_summary = prefetch_payload["generation_artifact_ledger"]["summary"]
    assert ledger_summary["item_count"] == 8
    assert ledger_summary["artifact_kind_counts"] == {
        "generation_executor_run_request": 2,
        "provider_execution_authorization": 2,
        "provider_adapter_execution_receipt": 2,
        "provider_output_envelope": 2,
    }
    assert ledger_summary["provider_call_count_by_this_request"] == 0
    assert ledger_summary["world_mutation_count_by_this_request"] == 0
    assert ledger_summary["activation_allowed_count"] == 0
    assert ledger_summary["promotion_allowed_count"] == 0
    assert prefetch_payload["campaign_router"]["scheduler_signal"]["latest_run_id"]
    assert "provider_artifact_staging" not in prefetch_payload
    assert "provider_artifact_promotion_report" not in prefetch_payload


def test_campaign_router_dispatcher_prefetch_rejects_targeted_metadata(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    rejected = client.post(
        f"/api/sessions/{sid}/campaign-router/prefetch-next-dispatcher-drain",
        json={
            "worker_id": "router-dispatcher-prefetch-targeted",
            "schedule_item_id": "sched_next_map_visual_prefetch",
        },
    )
    assert rejected.status_code == 409
    assert "does not accept targeted metadata" in rejected.json()["detail"]


def test_campaign_router_dispatcher_prefetch_rejects_invalid_budget(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    too_small = client.post(
        f"/api/sessions/{sid}/campaign-router/prefetch-next-dispatcher-drain",
        json={"worker_id": "router-dispatcher-small", "max_items": 0},
    )
    assert too_small.status_code == 422

    too_large = client.post(
        f"/api/sessions/{sid}/campaign-router/prefetch-next-dispatcher-drain",
        json={"worker_id": "router-dispatcher-large", "max_items": 17},
    )
    assert too_large.status_code == 422


def test_multinode_battle_results_advance_campaign_without_mislabeling(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))

    _payload(client.post(f"/api/sessions/{sid}/battles/gray_lantern_station/results"))
    wick_briefing = _payload(client.get(f"/api/sessions/{sid}/nodes/lamp_wick_store/briefing"))
    assert wick_briefing["briefing"]["node_id"] == "lamp_wick_store"
    assert wick_briefing["briefing"]["available_materials"]
    assert all(
        item.get("material_id") and isinstance(item.get("quantity"), int)
        for item in wick_briefing["briefing"]["available_materials"]
    )
    wick_battle = _payload(client.get(f"/api/sessions/{sid}/battles/lamp_wick_store/config"))
    assert wick_battle["map_runtime_package"]["node_id"] == "lamp_wick_store"
    wick = _payload(
        client.post(
            f"/api/sessions/{sid}/battles/lamp_wick_store/results",
            json={
                "result": "victory",
                "protected_core_hp": 6,
                "deployed_asset_ids": ["asset_ash_burst_lantern"],
            },
        )
    )
    wick_settlement = wick["settlement"]
    assert wick_settlement["settlement_mode"] == "transaction"
    assert wick_settlement["world_delta"]["source"] == "battle_result"
    assert wick_settlement["world_delta_transaction"]["source"] == "battle_result"
    assert wick_settlement["world_delta_transaction"]["transaction_id"] == (
        "tx_stage_04_wick_store_pressure_battle_001"
    )
    assert wick_settlement["core_artifact_refs"]["world_delta_transaction"].endswith(
        "stage_04_wick_store_pressure_battle.world_delta_transaction.json"
    )
    assert wick_settlement["run_world_state"]["progress"]["phase"] == (
        "post_wick_store_defense"
    )
    assert wick_settlement["primary_sample_name"] == "灯灰爆鸣塔"
    assert wick_settlement["primary_deployed_asset"]["object_id"] == (
        "asset_ash_burst_lantern"
    )
    assert "范围" in wick_settlement["sample_performance"]

    tower_route = _payload(client.get(f"/api/sessions/{sid}/campaign-router"))
    assert tower_route["campaign_router"]["current"]["node_id"] == "old_signal_tower"
    tower_briefing = _payload(client.get(f"/api/sessions/{sid}/nodes/old_signal_tower/briefing"))
    assert tower_briefing["briefing"]["node_id"] == "old_signal_tower"
    tower = _payload(
        client.post(
            f"/api/sessions/{sid}/battles/old_signal_tower/results",
            json={"result": "victory", "protected_core_hp": 5},
        )
    )
    tower_settlement = tower["settlement"]
    assert tower_settlement["settlement_mode"] == "fixture_bridge"
    assert tower_settlement["world_delta"] is None
    assert tower_settlement["world_delta_transaction"]["source"] == "research_job"
    assert tower_settlement["fixture_baseline"]["baseline_type"] == "research_job"
    assert tower_settlement["fixture_baseline"]["baseline_ref"].endswith(
        "demo_after_stage_06_signal_resonance.run_world_state.json"
    )
    assert tower_settlement["run_world_state"]["progress"]["phase"] == (
        "signal_resonance_trial"
    )


def test_battle_runtime_settlement_and_evidence_flow(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/world-instance"))
    schedule_run = _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))
    premature_stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={"worker_id": "too-early", "note": "executor request missing"},
    )
    assert premature_stage.status_code == 409
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={
                "worker_id": "evidence-dry-worker",
                "note": "prepare evidence queue",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/live-executor-guard",
            json={
                "worker_id": "evidence-live-guard",
                "note": "guard evidence stage",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/prepare-executor-request",
            json={
                "worker_id": "evidence-executor-request",
                "note": "prepare staging",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    pre_authorization_stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={"worker_id": "evidence-ledger", "note": "authorization missing"},
    )
    assert pre_authorization_stage.status_code == 409
    assert "matching provider execution authorization" in pre_authorization_stage.json()[
        "detail"
    ]
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/grant-provider-authorization",
            json={
                "worker_id": "evidence-provider-auth",
                "note": "authorize provider fixture for evidence",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    pre_adapter_stage = client.post(
        f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
        json={"worker_id": "evidence-ledger", "note": "adapter receipt missing"},
    )
    assert pre_adapter_stage.status_code == 409
    assert "matching provider adapter execution receipt" in pre_adapter_stage.json()[
        "detail"
    ]
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/run-provider-adapter-fixture",
            json={
                "worker_id": "evidence-provider-adapter",
                "note": "record provider adapter fixture for evidence",
                "schedule_item_id": "sched_next_map_visual_prefetch",
            },
        )
    )
    _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/stage-provider-artifacts",
            json={"worker_id": "evidence-ledger", "note": "stage before evidence"},
        )
    )

    battle = _payload(client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/config"))
    assert battle["battle_config"]["sample_asset"]["delivery_delay_ms"] == 30000
    assert battle["map_runtime_package"]["schema_version"] == "map_runtime_package.v0.1"
    assert battle["map_runtime_package"]["build_slots"]
    render_bundle = battle["map_render_plan_bundle"]
    assert render_bundle["procedural_map_render_plan"]["schema_version"] == (
        "procedural_map_render_plan.v0.1"
    )
    assert render_bundle["semantic_visual_consistency_report"]["status"] == "passed"
    assert "debug_control_overlay" in render_bundle["procedural_map_render_plan"][
        "debug_layer_ids"
    ]
    assert "debug_control_overlay" not in render_bundle["procedural_map_render_plan"][
        "player_default_layer_ids"
    ]
    assert battle["toolbar_assets"]
    assert battle["sample_delivery_asset"]["stable_internal_id"] == "asset_mirror_lure_trap_001"
    assert battle["animation_pipeline_status"] == (
        "multiframe_atlas_ready_video_keyframes_not_generated"
    )
    assert battle["runtime_art_kit"]["coverage"]["battle_nodes"] == ["gray_lantern_station"]

    runtime = _payload(
        client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/runtime-package")
    )
    assert runtime["runtime_package"]["schema_version"] == "runtime_package.v0.1"
    assert runtime["map_runtime_package"]["node_id"] == "gray_lantern_station"
    assert runtime["map_render_plan_bundle"]["refs"][
        "procedural_map_render_plan"
    ].endswith("mvp_first_battle.procedural_map_render_plan.json")
    assert runtime["sample_delivery_asset"]["media_refs"]["mode"] == "generated"
    assert runtime["runtime_art_media_manifest"]["summary"]["media_count"] == 18

    map_runtime = _payload(
        client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/map-runtime-package")
    )
    map_package = map_runtime["map_runtime_package"]
    assert map_package["schema_version"] == "map_runtime_package.v0.1"
    assert len(map_package["path_routes"]) == 1
    assert len(map_package["build_slots"]) >= 8
    first_visual_url = map_package["visual_layers"][0]["url"]
    assert first_visual_url.startswith("/assets/map_visual_reference/")
    visual_resp = client.get(first_visual_url)
    assert visual_resp.status_code == 200
    assert visual_resp.headers["content-type"] == "image/png"

    map_render_plan = _payload(
        client.get(f"/api/sessions/{sid}/battles/gray_lantern_station/map-render-plan")
    )
    plan_bundle = map_render_plan["map_render_plan_bundle"]
    assert plan_bundle["map_style_pack"]["schema_version"] == "map_style_pack.v0.1"
    assert plan_bundle["procedural_map_render_plan"]["layers"]
    assert plan_bundle["semantic_visual_consistency_report"]["summary"][
        "failed_count"
    ] == 0

    settlement = _payload(
        client.post(
            f"/api/sessions/{sid}/battles/gray_lantern_station/results",
            json={
                "result": "victory",
                "protected_core_hp": 7,
                "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
                "leaked_enemy_count": 1,
            },
        )
    )
    assert settlement["settlement"]["result"] == "victory"
    assert settlement["settlement"]["world_delta"]["delta_id"] == (
        "delta_run_demo_001_gray_lantern_station_2_battle_result_repaired"
    )
    assert settlement["settlement"]["world_delta_transaction"]["transaction_id"] == (
        "tx_first_battle_result_repaired_001"
    )
    assert settlement["settlement"]["core_artifact_refs"]["fact_entry"].endswith(
        "mvp_gray_lantern.fact_entry.json"
    )
    assert settlement["settlement"]["core_artifact_refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    settlement_core = settlement["settlement"]["core_artifacts"]
    assert settlement_core["status"] == "native_settlement_committed"
    assert settlement_core["refs"] == settlement["settlement"]["core_artifact_refs"]
    assert settlement_core["context_package"]["purpose"] == "world_delta"
    assert settlement_core["fact_entry"]["commit_state"] == "committed"
    assert settlement_core["fact_entry"]["source_tx_id"] == (
        "tx_first_battle_result_repaired_001"
    )
    assert settlement_core["compiled_game_object_package"]["runtime_contract"][
        "world_delta_refs"
    ][0]["path"] == settlement["settlement"]["core_artifact_refs"]["world_delta"]
    assert settlement_core["world_delta"]["delta_id"] == settlement["settlement"][
        "world_delta"
    ]["delta_id"]
    assert settlement_core["world_delta_transaction"]["transaction_id"] == settlement[
        "settlement"
    ]["world_delta_transaction"]["transaction_id"]
    assert settlement["settlement"]["run_world_state"]["progress"]["phase"] == (
        "post_first_defense"
    )

    latest = _payload(client.get(f"/api/sessions/{sid}/settlement/latest"))
    assert latest["settlement"]["world_delta"]["source"] == "battle_result"

    evidence = _payload(client.get(f"/api/sessions/{sid}/evidence"))
    assert evidence["audit_summary"]["overall_status"] == "passed"
    assert evidence["battle_result"]["settlement"]["node_id"] == "gray_lantern_station"
    assert evidence["battle_result"]["settlement"]["core_artifacts"]["status"] == (
        "native_settlement_committed"
    )
    assert evidence["ai_compile_core_artifacts"]["context_package"]["schema_version"] == (
        "context_package.v0.1"
    )
    assert evidence["ai_compile_core_artifacts"]["refs"]["compiled_game_object_package"].endswith(
        "mvp_light_snare.compiled_game_object_package.json"
    )
    assert evidence["ai_compile_core_artifacts"]["refs"]["world_delta_transaction"].endswith(
        "first_battle_result.world_delta_transaction.json"
    )
    assert evidence["generation_scheduler"]["refs"]["run_report"].endswith(
        "mvp_generation_schedule_run_report.v0.1.json"
    )
    assert evidence["generation_scheduler"]["buffer"]["provider_call_count"] == 0
    assert evidence["generation_scheduler"]["buffer"]["world_mutation_count"] == 0
    assert evidence["generation_scheduler"]["latest_run"]["run_id"] == (
        schedule_run["generation_schedule_run"]["run_id"]
    )
    assert evidence["generation_scheduler"]["latest_run"]["scheduler_mode"] == (
        "fixture_backed_dry_run"
    )
    assert evidence["generation_scheduler"]["latest_queue"]["summary"]["item_count"] == 8
    assert evidence["generation_scheduler"]["latest_queue"]["summary"]["claimable_count"] == 3
    assert evidence["generation_scheduler"]["latest_artifact_ledger"]["summary"][
        "item_count"
    ] == 6
    assert evidence["generation_scheduler"]["latest_artifact_ledger"]["summary"][
        "artifact_kind_counts"
    ]["generation_executor_run_request"] == 1
    assert evidence["generation_scheduler"]["latest_artifact_ledger"]["summary"][
        "artifact_kind_counts"
    ]["provider_execution_authorization"] == 1
    assert evidence["generation_scheduler"]["latest_artifact_ledger"]["summary"][
        "artifact_kind_counts"
    ]["provider_adapter_execution_receipt"] == 1
    assert evidence["generation_scheduler"]["latest_artifact_ledger"]["summary"][
        "promotion_allowed_count"
    ] == 0


def test_generation_scheduler_retry_budget_and_fallback_flow(client):
    sid = _create_session(client)
    _payload(client.post(f"/api/sessions/{sid}/generation-schedule/runs"))

    first_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={"worker_id": "budget-worker"},
        )
    )
    item_id = first_step["generation_schedule_queue_item"]["schedule_item_id"]
    assert first_step["generation_schedule_queue_item"]["status"] == "waiting_review"
    assert first_step["generation_schedule_queue_item"]["attempt_count"] == 1
    assert first_step["generation_schedule_queue_item"]["max_attempts"] == 2

    first_fail = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/fail",
            json={"worker_id": "budget-worker", "note": "first attempt rejected"},
        )
    )
    assert first_fail["generation_schedule_queue_item"]["status"] == "failed"

    retry = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/retry",
            json={"worker_id": "budget-worker", "note": "retry within budget"},
        )
    )
    assert retry["generation_schedule_queue_item"]["status"] == "queued"
    assert retry["generation_schedule_queue"]["summary"]["claimable_count"] == 4

    second_step = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/workers/dry-run-step",
            json={"worker_id": "budget-worker"},
        )
    )
    assert second_step["generation_schedule_queue_item"]["schedule_item_id"] == item_id
    assert second_step["generation_schedule_queue_item"]["attempt_count"] == 2
    assert second_step["generation_schedule_queue_item"]["attempt_budget_exhausted"] is True

    second_fail = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/fail",
            json={"worker_id": "budget-worker", "note": "second attempt rejected"},
        )
    )
    assert second_fail["generation_schedule_queue_item"]["status"] == "failed"

    retry_conflict = client.post(
        f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/retry",
        json={"worker_id": "budget-worker"},
    )
    assert retry_conflict.status_code == 409
    assert "cannot retry" in retry_conflict.json()["detail"]

    fallback = _payload(
        client.post(
            f"/api/sessions/{sid}/generation-schedule/queue/{item_id}/fallback",
            json={"worker_id": "budget-worker", "note": "use reviewed fallback"},
        )
    )
    assert fallback["generation_schedule_queue_item"]["status"] == "fallback_ready"
    assert fallback["generation_schedule_queue_item"]["fallback_ref"]
    assert fallback["generation_schedule_queue"]["summary"]["fallback_ready_count"] == 2


def test_all_battle_nodes_expose_map_runtime_and_render_plan_packages(client):
    sid = _create_session(client)
    expected = {
        "gray_lantern_station": (
            "map_pkg_gray_lantern_station_v0_1",
            "render_plan_gray_lantern_station_v0_1",
        ),
        "lamp_wick_store": (
            "map_pkg_lamp_wick_store_v0_1",
            "render_plan_lamp_wick_store_v0_1",
        ),
        "old_signal_tower": (
            "map_pkg_old_signal_tower_v0_1",
            "render_plan_old_signal_tower_v0_1",
        ),
    }
    for node_id, (package_id, render_plan_id) in expected.items():
        battle = _payload(client.get(f"/api/sessions/{sid}/battles/{node_id}/config"))
        assert battle["battle_config"]["node_id"] == node_id
        assert battle["map_runtime_package"]["package_id"] == package_id
        assert battle["map_runtime_package"]["node_id"] == node_id
        assert battle["map_runtime_package"]["path_routes"]
        assert battle["map_runtime_package"]["build_slots"]
        assert battle["map_render_plan_bundle"]["node_id"] == node_id
        assert battle["map_render_plan_bundle"]["procedural_map_render_plan"][
            "plan_id"
        ] == render_plan_id
        assert battle["map_render_plan_bundle"][
            "semantic_visual_consistency_report"
        ]["status"] == "passed"

        runtime = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-runtime-package")
        )
        map_package = runtime["map_runtime_package"]
        assert map_package["package_id"] == package_id
        assert map_package["node_id"] == node_id
        roles = {layer["role"] for layer in map_package["visual_layers"]}
        assert "battle_runtime_background" in roles

        render_plan = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-render-plan")
        )
        plan_bundle = render_plan["map_render_plan_bundle"]
        assert plan_bundle["procedural_map_render_plan"]["plan_id"] == render_plan_id
        assert plan_bundle["semantic_visual_consistency_report"]["summary"][
            "failed_count"
        ] == 0
        assert "debug_control_overlay" not in plan_bundle[
            "procedural_map_render_plan"
        ]["player_default_layer_ids"]


def test_all_battle_nodes_expose_review_only_map_v02_preview(client):
    sid = _create_session(client)
    expected = {
        "gray_lantern_station": "map_pkg_gray_lantern_station_v0_2",
        "lamp_wick_store": "map_pkg_lamp_wick_store_v0_2",
        "old_signal_tower": "map_pkg_old_signal_tower_v0_2",
    }
    for node_id, package_id in expected.items():
        preview = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-v02-preview")
        )
        assert preview["preview_mode"] == "review_only_map_v02"
        assert preview["review_only"] is True
        assert preview["runtime_activation_allowed"] is False
        assert preview["usage_policy"] == [
            "review_only",
            "not_player_runtime",
            "not_published_visual_layer",
            "does_not_modify_map_runtime_package",
        ]
        assert preview["source_refs"]["map_runtime_package_v02"].endswith(
            ".map_runtime_package_v02.json"
        )
        assert preview["preview_svg_ref"].endswith(".procedural_map_preview.svg")
        assert preview["safety"]["player_default_runtime_mutation"] is False
        assert preview["safety"]["provider_call_count"] == 0
        assert preview["safety"]["reads_env"] is False

        map_package = preview["map_runtime_package_v02"]
        assert map_package["schema_version"] == "map_runtime_package.v0.2"
        assert map_package["package_id"] == package_id
        assert map_package["node_id"] == node_id
        assert len(map_package["resource_nodes"]) == 1
        assert len(map_package["hazard_zones"]) == 1
        assert len(map_package["defense_anchors"]) == 1
        assert len(map_package["blocked_areas"]) == 1

        bundle = preview["map_render_plan_bundle_v02"]
        assert bundle["review_only"] is True
        assert bundle["runtime_activation_allowed"] is False
        assert bundle["procedural_map_render_plan"]["schema_version"] == (
            "procedural_map_render_plan.v0.1"
        )
        assert bundle["semantic_visual_consistency_report"]["status"] == "passed"
        assert bundle["procedural_map_preview_report"]["status"] == (
            "preview_ready_review_only"
        )
        render_summary = bundle["procedural_map_preview_report"]["render_summary"]
        assert render_summary["resource_node_count"] == 1
        assert render_summary["hazard_zone_count"] == 1
        assert render_summary["defense_anchor_count"] == 1
        assert render_summary["blocked_area_count"] == 1
        assert preview["preview_report_v02"] == bundle["procedural_map_preview_report"]

        runtime = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-runtime-package")
        )
        assert runtime["map_runtime_package"]["schema_version"] == (
            "map_runtime_package.v0.1"
        )
        assert "resource_nodes" not in runtime["map_runtime_package"]


def test_approved_map_v02_activation_selector_updates_default_surfaces(
    client, tmp_path, monkeypatch
):
    approved_report = _write_approved_map_runtime_authorization_report(tmp_path)
    from app.services import map_runtime_service as app_map_runtime_service
    from backend.app.services import map_runtime_service as backend_map_runtime_service

    monkeypatch.setattr(
        app_map_runtime_service,
        "_MAP_RUNTIME_ACTIVATION_AUTHORIZATION_REPORT",
        approved_report,
    )
    monkeypatch.setattr(
        backend_map_runtime_service,
        "_MAP_RUNTIME_ACTIVATION_AUTHORIZATION_REPORT",
        approved_report,
        raising=False,
    )

    sid = _create_session(client)
    expected = {
        "gray_lantern_station": "map_pkg_gray_lantern_station_v0_2",
        "lamp_wick_store": "map_pkg_lamp_wick_store_v0_2",
        "old_signal_tower": "map_pkg_old_signal_tower_v0_2",
    }
    for node_id, package_id in expected.items():
        config = _payload(client.get(f"/api/sessions/{sid}/battles/{node_id}/config"))
        runtime = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/runtime-package")
        )
        direct = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-runtime-package")
        )
        render = _payload(
            client.get(f"/api/sessions/{sid}/battles/{node_id}/map-render-plan")
        )

        for payload in (config, runtime, direct):
            map_package = payload["map_runtime_package"]
            selection = payload["runtime_selection"]
            assert map_package["schema_version"] == "map_runtime_package.v0.2"
            assert map_package["package_id"] == package_id
            assert map_package["node_id"] == node_id
            assert len(map_package["resource_nodes"]) == 1
            assert len(map_package["hazard_zones"]) == 1
            assert len(map_package["defense_anchors"]) == 1
            assert len(map_package["blocked_areas"]) == 1
            assert selection["selection_mode"] == "developer_authorization_selector"
            assert selection["selected_schema_version"] == "map_runtime_package.v0.2"
            assert selection["activation_applied"] is True
            assert selection["authorization"]["authorization_status"] == (
                "approved_for_gate_review"
            )
            assert selection["authorization"]["target_matches_candidate"] is True
            assert selection["safety"]["provider_call_count"] == 0
            assert selection["safety"]["reads_env"] is False

        plan_bundle = render["map_render_plan_bundle"]
        assert render["runtime_selection"]["activation_applied"] is True
        assert plan_bundle["review_only"] is False
        assert plan_bundle["runtime_activation_allowed"] is True
        assert plan_bundle["activation_surface"] == (
            "developer_authorized_default_runtime_selector"
        )
        assert plan_bundle["semantic_visual_consistency_report"]["status"] == "passed"
        assert plan_bundle["procedural_map_preview_report"]["render_summary"][
            "resource_node_count"
        ] == 1


def test_map_v02_preview_unknown_node_returns_404(client):
    sid = _create_session(client)
    resp = client.get(f"/api/sessions/{sid}/battles/unknown/map-v02-preview")
    assert resp.status_code == 404
    assert "map runtime package not found" in resp.json()["detail"]


def test_frontend_mock_endpoints_require_existing_session(client):
    resp = client.get("/api/sessions/missing/frontend-mock-pack")
    assert resp.status_code == 404
    assert "session not found" in resp.json()["detail"].lower()


def test_unknown_node_returns_404(client):
    sid = _create_session(client)
    resp = client.get(f"/api/sessions/{sid}/nodes/unknown/briefing")
    assert resp.status_code == 404
    assert "mock fixture not found" in resp.json()["detail"]
