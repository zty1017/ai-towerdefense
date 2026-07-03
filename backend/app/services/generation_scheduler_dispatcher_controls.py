"""Pure control helpers for review-only dispatcher/tick endpoints."""

from __future__ import annotations

from typing import Any


TARGETED_METADATA_KEYS = (
    "schedule_item_id",
    "authorization_ref",
    "artifact_profile",
    "receipt_path",
    "envelope_path",
    "staging_path",
    "promotion_report_path",
)


def requested_max_items(
    metadata: dict[str, Any] | None,
    *,
    default: int,
    maximum: int,
    error_cls: type[Exception] = ValueError,
) -> int:
    if not isinstance(metadata, dict) or metadata.get("max_items") is None:
        return default
    try:
        value = int(metadata["max_items"])
    except (TypeError, ValueError) as exc:
        raise error_cls("max_items must be an integer") from exc
    if value < 1 or value > maximum:
        raise error_cls(f"max_items must be between 1 and {maximum}")
    return value


def targeted_metadata_keys(
    metadata: dict[str, Any] | None,
    keys: tuple[str, ...] = TARGETED_METADATA_KEYS,
) -> list[str]:
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    return [key for key in keys if safe_metadata.get(key) not in (None, "")]


def reject_targeted_metadata(
    metadata: dict[str, Any] | None,
    *,
    action_label: str,
    error_cls: type[Exception] = ValueError,
) -> None:
    unsupported_keys = targeted_metadata_keys(metadata)
    if unsupported_keys:
        raise error_cls(
            f"{action_label} does not accept targeted metadata: "
            + ", ".join(unsupported_keys)
        )


def dispatcher_step_metadata(
    *,
    worker_prefix: str,
    step_name: str,
    note: Any = None,
    schedule_item_id: str | None = None,
    authorization_ref: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "worker_id": f"{worker_prefix}_{step_name}",
        "note": note,
    }
    if schedule_item_id:
        metadata["schedule_item_id"] = schedule_item_id
    if authorization_ref:
        metadata["authorization_ref"] = authorization_ref
    return metadata
