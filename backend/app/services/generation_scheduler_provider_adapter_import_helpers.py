"""Pure contract helpers for ProviderAdapterRunner output imports."""

from __future__ import annotations

from typing import Any


def payload_section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    return section if isinstance(section, dict) else {}


def provider_adapter_runner_import_alignment_checks(
    receipt_payload: dict[str, Any],
    envelope_payload: dict[str, Any],
    *,
    schedule_item_id: str,
    authorization_ref: str,
    executor_request_id: str | None,
) -> dict[str, bool]:
    receipt_source = payload_section(receipt_payload, "source")
    envelope_source = payload_section(envelope_payload, "source")
    provider_call = payload_section(envelope_payload, "provider_call")
    execution = payload_section(receipt_payload, "execution")

    alignment_checks = {
        "receipt_schedule_item_id": receipt_source.get("schedule_item_id")
        == schedule_item_id,
        "receipt_authorization_ref": receipt_source.get("authorization_ref")
        == authorization_ref,
        "receipt_executor_request_id": receipt_source.get("executor_request_id")
        == executor_request_id,
        "envelope_schedule_item_id": envelope_source.get("schedule_item_id")
        == schedule_item_id,
        "envelope_object_kind": envelope_source.get("object_kind")
        == receipt_source.get("object_kind"),
        "envelope_object_ref": envelope_source.get("object_ref")
        == receipt_source.get("object_ref"),
        "envelope_provider_profile": envelope_source.get("provider_profile")
        == receipt_source.get("provider_profile"),
        "envelope_provider_mode": envelope_source.get("provider_mode")
        == receipt_source.get("provider_mode"),
        "provider_performed_matches_receipt": provider_call.get("performed")
        == execution.get("provider_call_performed_by_receipt_builder"),
    }
    if provider_call.get("performed") is True:
        alignment_checks["performed_authorization_ref"] = (
            provider_call.get("authorization_ref") == authorization_ref
        )
    return alignment_checks


def validate_provider_adapter_runner_import_contract(
    receipt_payload: dict[str, Any],
    envelope_payload: dict[str, Any],
    *,
    schedule_item_id: str,
    authorization_ref: str,
    executor_request_id: str | None,
    error_cls: type[Exception] = ValueError,
) -> dict[str, Any]:
    alignment_checks = provider_adapter_runner_import_alignment_checks(
        receipt_payload,
        envelope_payload,
        schedule_item_id=schedule_item_id,
        authorization_ref=authorization_ref,
        executor_request_id=executor_request_id,
    )
    failed = [name for name, passed in alignment_checks.items() if not passed]
    if failed:
        raise error_cls(
            "provider adapter runner outputs do not match ledger authorization chain: "
            + ", ".join(failed)
        )

    return {
        "receipt_source": payload_section(receipt_payload, "source"),
        "envelope_source": payload_section(envelope_payload, "source"),
        "provider_call": payload_section(envelope_payload, "provider_call"),
        "execution": payload_section(receipt_payload, "execution"),
        "alignment_checks": alignment_checks,
    }
