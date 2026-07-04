#!/usr/bin/env python3
"""Build a developer-approved MapComponent replacement manifest/report.

This apply layer is deliberately narrow: it only accepts SVG replacement
patches already marked ready_for_developer_apply by
MapComponentManifestPatchPlan v0.1. It does not call providers, read .env,
change frontend defaults, or mutate MapRuntimePackage / StylePack / RenderPlan.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import validate_map_component_manifest_patch_plan as patch_plan_validator  # noqa: E402


REPORT_VERSION = "map_component_manifest_apply_report.v0.1"
DEFAULT_PATCH_PLAN = ROOT / "examples/review_packs/map_component_manifest_patch_plan.v0.1.json"
DEFAULT_APPROVAL_PLAN = ROOT / "examples/review_packs/map_component_manifest_apply_approval_plan.v0.1.json"
DEFAULT_OUTPUT_REPORT = ROOT / "examples/review_packs/map_component_manifest_apply_report.v0.1.json"
USAGE_POLICY = [
    "developer_explicit_manifest_apply_approval_only",
    "svg_replacement_only",
    "replacement_manifest_artifact_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_style_pack_or_render_plan_mutation",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
    "no_secret_material",
]
FALSE_RUNTIME_EFFECT = {
    "style_pack_modified": False,
    "render_plan_modified": False,
    "frontend_default_modified": False,
    "runtime_map_truth_modified": False,
}
APPROVAL_SCOPE_VALUES = {"manifest_apply", "map_component_manifest_apply"}
APPROVAL_PLAN_VERSION = "map_component_manifest_apply_approval_plan.v0.1"
PLAN_ROOT_KEYS = {
    "schema_version",
    "approval_id",
    "plan_id",
    "usage_policy",
    "approved_patches",
    "approvals",
}
PLAN_ENTRY_KEYS = {
    "patch_id",
    "candidate_id",
    "approval_status",
    "approval_scope",
    "approved_at",
    "reviewer",
    "rationale",
}
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
    "prompt",
    "raw_prompt",
    "full_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
    "temporary_url",
)
EXTERNAL_URL_MARKERS = ("http://", "https://", "://")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel_or_abs(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed in approval plan")
            scan_forbidden_key_fragments(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_key_fragments(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_external_urls(child, f"{path}.{key}" if path else key, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in EXTERNAL_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def approved_entries(approval_plan: Any) -> tuple[str, set[str], set[str], list[str]]:
    errors: list[str] = []
    if not isinstance(approval_plan, dict):
        return "invalid_approval_plan", set(), set(), ["approval plan root must be an object"]
    unexpected_root_keys = sorted(set(approval_plan) - PLAN_ROOT_KEYS)
    for key in unexpected_root_keys:
        errors.append(f"approval plan root contains unsupported field: {key}")
    if approval_plan.get("schema_version") != APPROVAL_PLAN_VERSION:
        errors.append(f"approval plan schema_version must be {APPROVAL_PLAN_VERSION}")
    if "approved_patches" in approval_plan and "approvals" in approval_plan:
        errors.append("approval plan must use only one of approved_patches or approvals")
    scan_forbidden_key_fragments(approval_plan, "", errors)
    scan_external_urls(approval_plan, "", errors)
    approval_id = str(
        approval_plan.get("approval_id")
        or approval_plan.get("plan_id")
        or approval_plan.get("schema_version")
        or "map_component_manifest_apply_approval_plan"
    )
    entries = approval_plan.get("approved_patches", approval_plan.get("approvals", []))
    if not isinstance(entries, list):
        return approval_id, set(), set(), ["approval plan approved_patches/approvals must be an array"]

    approved_patch_ids: set[str] = set()
    approved_candidate_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"approved_patches[{index}] must be an object")
            continue
        unexpected_entry_keys = sorted(set(entry) - PLAN_ENTRY_KEYS)
        for key in unexpected_entry_keys:
            errors.append(f"approved_patches[{index}] contains unsupported field: {key}")
        if entry.get("approval_status") != "approved":
            continue
        scopes = set(map(str, as_list(entry.get("approval_scope"))))
        if not scopes.intersection(APPROVAL_SCOPE_VALUES):
            errors.append(
                f"approved_patches[{index}].approval_scope must include manifest_apply "
                "or map_component_manifest_apply"
            )
            continue
        patch_id = entry.get("patch_id")
        candidate_id = entry.get("candidate_id")
        if isinstance(patch_id, str) and patch_id.strip():
            approved_patch_ids.add(patch_id)
        elif isinstance(candidate_id, str) and candidate_id.strip():
            approved_candidate_ids.add(candidate_id)
        else:
            errors.append(f"approved_patches[{index}] must include patch_id or candidate_id")
    if len(approved_patch_ids) + len(approved_candidate_ids) != len(
        set(approved_patch_ids) | set(approved_candidate_ids)
    ):
        errors.append("approval plan contains duplicate approved patch/candidate ids")
    return approval_id, approved_patch_ids, approved_candidate_ids, errors


def manifest_items_by_stable_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("stable_internal_id") or ""): item
        for item in as_list(manifest.get("items"))
        if isinstance(item, dict)
    }


def is_patch_approved(
    patch: dict[str, Any],
    *,
    approved_patch_ids: set[str],
    approved_candidate_ids: set[str],
) -> bool:
    return (
        str(patch.get("patch_id") or "") in approved_patch_ids
        or str(patch.get("candidate_id") or "") in approved_candidate_ids
    )


def base_patch_result(patch: dict[str, Any], *, approval_status: str) -> dict[str, Any]:
    target = as_obj(patch.get("target_manifest_item"))
    replacement = as_obj(patch.get("replacement_source"))
    return {
        "patch_id": patch.get("patch_id"),
        "candidate_id": patch.get("candidate_id"),
        "component_id": patch.get("component_id"),
        "stable_internal_id": patch.get("stable_internal_id"),
        "approval_status": approval_status,
        "apply_status": "skipped_not_approved",
        "reason": "patch was not listed in the developer approval plan",
        "candidate_local_path": replacement.get("candidate_local_path"),
        "candidate_sha256": replacement.get("candidate_sha256"),
        "target_local_path": patch.get("proposed_processed_local_path") or target.get("local_path"),
        "target_public_url": patch.get("proposed_public_url") or target.get("url"),
        "target_sha256_before": target.get("sha256"),
        "target_sha256_after": target.get("sha256"),
        "candidate_file_copied": False,
    }


def block_result(result: dict[str, Any], reason: str) -> dict[str, Any]:
    result["apply_status"] = "blocked"
    result["reason"] = reason
    result["candidate_file_copied"] = False
    return result


def apply_ready_patch(
    patch: dict[str, Any],
    *,
    replacement_manifest: dict[str, Any],
    manifest_items: dict[str, dict[str, Any]],
    copy_files: bool,
) -> dict[str, Any]:
    result = base_patch_result(patch, approval_status="approved")
    replacement = as_obj(patch.get("replacement_source"))
    target = as_obj(patch.get("target_manifest_item"))

    if patch.get("patch_status") != "ready_for_developer_apply":
        return block_result(result, "patch_status must be ready_for_developer_apply")
    if replacement.get("file_type") != "svg":
        return block_result(result, "replacement_source.file_type must be svg")

    candidate_path_value = replacement.get("candidate_local_path")
    candidate_sha = replacement.get("candidate_sha256")
    if not isinstance(candidate_path_value, str) or not candidate_path_value.strip():
        return block_result(result, "replacement_source.candidate_local_path is required")
    if not isinstance(candidate_sha, str) or not candidate_sha.strip():
        return block_result(result, "replacement_source.candidate_sha256 is required")
    candidate_path = resolve_path(candidate_path_value)
    if not candidate_path.exists() or not candidate_path.is_file():
        return block_result(result, f"candidate file does not exist: {candidate_path_value}")
    if candidate_path.suffix.lower() != ".svg":
        return block_result(result, "candidate file must have .svg extension")
    if sha256_file(candidate_path) != candidate_sha:
        return block_result(result, "candidate file sha256 does not match replacement_source")

    stable_id = str(patch.get("stable_internal_id") or "")
    item = manifest_items.get(stable_id)
    if item is None:
        return block_result(result, "target stable_internal_id was not found in source manifest")
    if target.get("local_path") != item.get("local_path") or patch.get("proposed_processed_local_path") != item.get("local_path"):
        return block_result(result, "proposed_processed_local_path must match current manifest item")
    if target.get("url") != item.get("url") or patch.get("proposed_public_url") != item.get("url"):
        return block_result(result, "proposed_public_url must match current manifest item")
    if target.get("sha256") != item.get("sha256"):
        return block_result(result, "target_manifest_item sha256 must match current manifest item")

    if copy_files:
        target_path = resolve_path(str(item.get("local_path")))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate_path, target_path)
        result["candidate_file_copied"] = True

    replacement_item = manifest_items_by_stable_id(replacement_manifest).get(stable_id)
    if replacement_item is None:
        return block_result(result, "target stable_internal_id was not found in replacement manifest")
    replacement_item["sha256"] = candidate_sha
    if isinstance(replacement.get("width"), int):
        replacement_item["width"] = replacement["width"]
    if isinstance(replacement.get("height"), int):
        replacement_item["height"] = replacement["height"]

    result["apply_status"] = "applied_to_replacement_manifest"
    result["reason"] = "approved SVG patch applied to replacement manifest artifact"
    result["target_sha256_after"] = candidate_sha
    return result


def build_report(
    *,
    patch_plan_path: Path,
    approval_plan_path: Path,
    output_manifest_path: Path | None,
    output_report_path: Path,
    created_at: str | None,
    copy_files: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    patch_plan = as_obj(load_json(patch_plan_path))
    schema = load_json(patch_plan_validator.DEFAULT_SCHEMA)
    patch_errors = patch_plan_validator.validate_report(patch_plan, schema if isinstance(schema, dict) else None)
    if patch_errors:
        raise ValueError("source patch plan is invalid: " + "; ".join(patch_errors))

    approval_plan = load_json(approval_plan_path)
    approval_id, approved_patch_ids, approved_candidate_ids, approval_errors = approved_entries(approval_plan)
    if approval_errors:
        raise ValueError("approval plan is invalid: " + "; ".join(approval_errors))

    source_manifest_path = resolve_path(str(patch_plan.get("source_manifest_path") or ""))
    source_manifest = as_obj(load_json(source_manifest_path))
    replacement_manifest = copy.deepcopy(source_manifest)
    source_manifest_sha = sha256_file(source_manifest_path)
    manifest_items = manifest_items_by_stable_id(source_manifest)

    patch_results: list[dict[str, Any]] = []
    patches = [patch for patch in as_list(patch_plan.get("patches")) if isinstance(patch, dict)]
    known_patch_ids = {str(patch.get("patch_id") or "") for patch in patches}
    known_candidate_ids = {str(patch.get("candidate_id") or "") for patch in patches}
    unknown_patch_ids = sorted(approved_patch_ids - known_patch_ids)
    unknown_candidate_ids = sorted(approved_candidate_ids - known_candidate_ids)
    if unknown_patch_ids or unknown_candidate_ids:
        parts: list[str] = []
        if unknown_patch_ids:
            parts.append("unknown patch_id: " + ", ".join(unknown_patch_ids))
        if unknown_candidate_ids:
            parts.append("unknown candidate_id: " + ", ".join(unknown_candidate_ids))
        raise ValueError("approval plan references source patch plan entries that do not exist: " + "; ".join(parts))
    if (approved_patch_ids or approved_candidate_ids) and output_manifest_path is None:
        raise ValueError("--output-manifest is required when approval plan approves patches")

    for patch in patches:
        approved = is_patch_approved(
            patch,
            approved_patch_ids=approved_patch_ids,
            approved_candidate_ids=approved_candidate_ids,
        )
        if not approved:
            patch_results.append(base_patch_result(patch, approval_status="not_approved"))
            continue
        patch_results.append(
            apply_ready_patch(
                patch,
                replacement_manifest=replacement_manifest,
                manifest_items=manifest_items,
                copy_files=copy_files,
            )
        )

    status_counts = Counter(str(result.get("apply_status")) for result in patch_results)
    applied_count = status_counts.get("applied_to_replacement_manifest", 0)
    skipped_count = status_counts.get("skipped_not_approved", 0)
    blocked_count = status_counts.get("blocked", 0)
    approved_patch_count = applied_count + blocked_count
    manifest_written = output_manifest_path is not None and applied_count > 0 and blocked_count == 0
    if manifest_written:
        replacement_manifest["validation"] = {
            "validator": "tools/media/validate_map_component_media_pack.py",
            "commands": [
                f"python3 tools/media/validate_map_component_media_pack.py {rel_or_abs(output_manifest_path)}"
            ],
        }
        write_json(output_manifest_path, replacement_manifest)

    replacement_content_sha = sha256_json(replacement_manifest)
    replacement_file_sha = sha256_file(output_manifest_path) if manifest_written and output_manifest_path else None
    if blocked_count:
        status = "blocked"
    elif applied_count:
        status = "replacement_manifest_built"
    else:
        status = "no_approved_patches"

    runtime_effect = {
        "manifest_replacement_written": manifest_written,
        **FALSE_RUNTIME_EFFECT,
        "candidate_file_copied": any(bool(result.get("candidate_file_copied")) for result in patch_results),
    }
    summary = {
        "source_patch_count": len(patches),
        "approved_patch_count": approved_patch_count,
        "applied_patch_count": applied_count,
        "skipped_patch_count": skipped_count,
        "blocked_patch_count": blocked_count,
        "ready_patch_count": sum(1 for patch in patches if patch.get("patch_status") == "ready_for_developer_apply"),
        "manifest_item_count": len(as_list(source_manifest.get("items"))),
    }
    report = {
        "schema_version": REPORT_VERSION,
        "report_id": "map_component_manifest_apply_report_v0_1",
        "created_at": created_at or str(patch_plan.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_patch_plan_path": rel_or_abs(patch_plan_path),
        "source_manifest_path": rel_or_abs(source_manifest_path),
        "source_approval_plan_path": rel_or_abs(approval_plan_path),
        "approval_id": approval_id,
        "output_manifest_path": rel_or_abs(output_manifest_path) if manifest_written and output_manifest_path else None,
        "status": status,
        "usage_policy": USAGE_POLICY,
        "summary": summary,
        "runtime_effect": runtime_effect,
        "manifest_sha": {
            "source_manifest_file_sha256_before": source_manifest_sha,
            "replacement_manifest_content_sha256_after": replacement_content_sha,
            "replacement_manifest_file_sha256_after": replacement_file_sha,
        },
        "patch_results": patch_results,
        "validation": {
            "validator": "tools/media/validate_map_component_manifest_apply_report.py",
            "commands": [
                f"python3 tools/media/validate_map_component_manifest_apply_report.py {rel_or_abs(output_report_path)}"
            ],
        },
    }
    return report, replacement_manifest if output_manifest_path else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply approved MapComponentManifestPatchPlan SVG replacements.")
    parser.add_argument("--patch-plan", default=str(DEFAULT_PATCH_PLAN))
    parser.add_argument("--approval-plan", default=str(DEFAULT_APPROVAL_PLAN))
    parser.add_argument("--output-manifest", default=None)
    parser.add_argument("--output-report", default=str(DEFAULT_OUTPUT_REPORT))
    parser.add_argument("--copy-files", action="store_true")
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    patch_plan_path = resolve_path(args.patch_plan)
    approval_plan_path = resolve_path(args.approval_plan)
    output_manifest_path = resolve_path(args.output_manifest) if args.output_manifest else None
    output_report_path = resolve_path(args.output_report)
    try:
        report, _ = build_report(
            patch_plan_path=patch_plan_path,
            approval_plan_path=approval_plan_path,
            output_manifest_path=output_manifest_path,
            output_report_path=output_report_path,
            created_at=args.created_at,
            copy_files=args.copy_files,
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    write_json(output_report_path, report)
    summary = as_obj(report.get("summary"))
    print(f"OK: wrote {output_report_path}")
    if report.get("output_manifest_path"):
        print(f"OK: wrote replacement manifest {output_manifest_path}")
    print(f"- status: {report.get('status')}")
    print(f"- applied_patch_count: {summary.get('applied_patch_count')}")
    print(f"- skipped_patch_count: {summary.get('skipped_patch_count')}")
    print(f"- blocked_patch_count: {summary.get('blocked_patch_count')}")
    return 0 if report.get("status") != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
