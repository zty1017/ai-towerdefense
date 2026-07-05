#!/usr/bin/env python3
"""Validate MapComponentManifestApplyReport v0.2."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import apply_map_component_manifest_patch_plan_v02 as apply_builder  # noqa: E402
import validate_map_component_manifest_patch_plan_v02 as patch_plan_validator  # noqa: E402
import validate_map_component_media_pack_v02 as manifest_validator  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_manifest_apply_report.v0.2.schema.json"
DEFAULT_PATCH_PLAN_SCHEMA = ROOT / "shared/schemas/map_component_manifest_patch_plan.v0.2.schema.json"
DEFAULT_MANIFEST_SCHEMA = ROOT / "shared/schemas/map_component_media_manifest.v0.2.schema.json"
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
EXTERNAL_URL_RE = re.compile(r"(?:https?://|://)", re.IGNORECASE)
REQUIRED_USAGE_POLICY = {
    "developer_explicit_manifest_apply_approval_only",
    "v0_2_single_image_manifest_replacement_preview",
    "replacement_manifest_artifact_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_style_pack_or_render_plan_mutation",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
    "no_secret_material",
}
FALSE_EFFECT_FIELDS = {
    "style_pack_modified",
    "render_plan_modified",
    "frontend_default_modified",
    "runtime_map_truth_modified",
}
SINGLE_IMAGE_KINDS = {"svg", "png", "webp"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_with_jsonschema(value: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
    if not schema:
        return []
    try:
        import jsonschema  # type: ignore
    except Exception:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator", None)
    if validator_cls is None:
        return []
    validator = validator_cls(schema)
    return [
        f"schema: {'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(value), key=str)
    ]


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed")
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
    elif isinstance(value, str) and EXTERNAL_URL_RE.search(value):
        errors.append(f"{path} must not contain an external URL")


def load_source_patch_plan(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    path_value = report.get("source_patch_plan_path")
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append("source_patch_plan_path must be a non-empty string")
        return {}
    path = resolve_repo_path(path_value)
    if not path.exists():
        errors.append(f"source_patch_plan_path does not exist: {path_value}")
        return {}
    patch_plan = load_json(path)
    if not isinstance(patch_plan, dict):
        errors.append("source patch plan root must be an object")
        return {}
    schema = load_json(DEFAULT_PATCH_PLAN_SCHEMA) if DEFAULT_PATCH_PLAN_SCHEMA.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    for error in patch_plan_validator.validate_report(patch_plan, schema_obj):
        errors.append(f"source patch plan invalid: {error}")
    if patch_plan.get("source_manifest_path") != report.get("source_manifest_path"):
        errors.append("source_manifest_path must match source patch plan")
    return patch_plan


def load_source_manifest(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    path_value = report.get("source_manifest_path")
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append("source_manifest_path must be a non-empty string")
        return {}
    path = resolve_repo_path(path_value)
    if not path.exists():
        errors.append(f"source_manifest_path does not exist: {path_value}")
        return {}
    manifest = load_json(path)
    if not isinstance(manifest, dict):
        errors.append("source manifest root must be an object")
        return {}
    schema = load_json(DEFAULT_MANIFEST_SCHEMA) if DEFAULT_MANIFEST_SCHEMA.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    for error in manifest_validator.validate_manifest(manifest, schema_obj):
        errors.append(f"source manifest invalid: {error}")
    return manifest


def load_and_validate_approval_plan(
    report: dict[str, Any],
    patch_plan: dict[str, Any],
    errors: list[str],
) -> tuple[set[str], set[str]]:
    path_value = report.get("source_approval_plan_path")
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append("source_approval_plan_path must be a non-empty string")
        return set(), set()
    path = resolve_repo_path(path_value)
    if not path.exists():
        errors.append(f"source_approval_plan_path does not exist: {path_value}")
        return set(), set()
    try:
        approval_plan = load_json(path)
    except json.JSONDecodeError as exc:
        errors.append(f"source_approval_plan_path is not valid JSON: {exc}")
        return set(), set()
    approval_id, approved_patch_ids, approved_candidate_ids, approval_errors = apply_builder.approved_entries(
        approval_plan
    )
    for error in approval_errors:
        errors.append(f"source approval plan invalid: {error}")
    if report.get("approval_id") != approval_id:
        errors.append("approval_id must match source approval plan")

    patches = [patch for patch in as_list(patch_plan.get("patches")) if isinstance(patch, dict)]
    known_patch_ids = {str(patch.get("patch_id") or "") for patch in patches}
    known_candidate_ids = {str(patch.get("candidate_id") or "") for patch in patches}
    unknown_patch_ids = sorted(approved_patch_ids - known_patch_ids)
    unknown_candidate_ids = sorted(approved_candidate_ids - known_candidate_ids)
    if unknown_patch_ids:
        errors.append("source approval plan references unknown patch_id: " + ", ".join(unknown_patch_ids))
    if unknown_candidate_ids:
        errors.append("source approval plan references unknown candidate_id: " + ", ".join(unknown_candidate_ids))
    return approved_patch_ids, approved_candidate_ids


def validate_output_manifest(report: dict[str, Any], errors: list[str]) -> dict[str, Any] | None:
    output_value = report.get("output_manifest_path")
    runtime_effect = as_obj(report.get("runtime_effect"))
    manifest_sha = as_obj(report.get("manifest_sha"))
    if output_value is None:
        if runtime_effect.get("manifest_replacement_written") is not False:
            errors.append("runtime_effect.manifest_replacement_written must be false when output_manifest_path is null")
        if manifest_sha.get("replacement_manifest_file_sha256_after") is not None:
            errors.append("replacement_manifest_file_sha256_after must be null when output_manifest_path is null")
        return None
    if not isinstance(output_value, str) or not output_value.strip():
        errors.append("output_manifest_path must be null or a non-empty string")
        return None
    path = resolve_repo_path(output_value)
    if not path.exists():
        errors.append(f"output_manifest_path does not exist: {output_value}")
        return None
    if runtime_effect.get("manifest_replacement_written") is not True:
        errors.append("runtime_effect.manifest_replacement_written must be true when output_manifest_path is set")
    actual_file_sha = sha256_file(path)
    if manifest_sha.get("replacement_manifest_file_sha256_after") != actual_file_sha:
        errors.append("manifest_sha.replacement_manifest_file_sha256_after must match output manifest file")
    manifest = load_json(path)
    if not isinstance(manifest, dict):
        errors.append("output manifest root must be an object")
        return None
    if manifest_sha.get("replacement_manifest_content_sha256_after") != sha256_json(manifest):
        errors.append("manifest_sha.replacement_manifest_content_sha256_after must match output manifest content")
    schema = load_json(DEFAULT_MANIFEST_SCHEMA) if DEFAULT_MANIFEST_SCHEMA.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    for error in manifest_validator.validate_manifest(manifest, schema_obj):
        errors.append(f"output manifest invalid: {error}")
    return manifest


def patches_by_id(patch_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(patch.get("patch_id") or ""): patch
        for patch in as_list(patch_plan.get("patches"))
        if isinstance(patch, dict)
    }


def candidate_file_errors(replacement: dict[str, Any]) -> list[str]:
    candidate_path_value = replacement.get("candidate_local_path")
    if not isinstance(candidate_path_value, str) or not candidate_path_value:
        return ["candidate_local_path is required"]
    candidate_path = resolve_repo_path(candidate_path_value)
    if not candidate_path.exists():
        return ["candidate file does not exist"]
    if sha256_file(candidate_path) != replacement.get("candidate_sha256"):
        return ["candidate file sha256 mismatch"]
    return apply_builder.validate_candidate_file(
        candidate_path=candidate_path,
        candidate_path_value=candidate_path_value,
        replacement=replacement,
    )


def validate_patch_results(
    report: dict[str, Any],
    patch_plan: dict[str, Any],
    source_manifest: dict[str, Any],
    output_manifest: dict[str, Any] | None,
    approved_patch_ids: set[str],
    approved_candidate_ids: set[str],
    errors: list[str],
) -> None:
    patches = patches_by_id(patch_plan)
    source_items = {
        str(item.get("stable_internal_id") or ""): item
        for item in as_list(source_manifest.get("items"))
        if isinstance(item, dict)
    }
    output_items = {
        str(item.get("stable_internal_id") or ""): item
        for item in as_list(output_manifest.get("items"))
        if isinstance(item, dict)
    } if output_manifest else {}

    results = [result for result in as_list(report.get("patch_results")) if isinstance(result, dict)]
    result_patch_ids = [str(result.get("patch_id") or "") for result in results]
    if set(result_patch_ids) != set(patches):
        errors.append("patch_results patch_id set must match source patch plan patches")
    duplicates = sorted({patch_id for patch_id in result_patch_ids if result_patch_ids.count(patch_id) > 1})
    for patch_id in duplicates:
        errors.append(f"duplicate patch_result patch_id: {patch_id}")

    for index, result in enumerate(results):
        patch_id = str(result.get("patch_id") or "")
        patch = patches.get(patch_id)
        if not patch:
            continue
        approved_by_plan = (
            patch_id in approved_patch_ids
            or str(result.get("candidate_id") or "") in approved_candidate_ids
        )
        expected_approval_status = "approved" if approved_by_plan else "not_approved"
        if result.get("approval_status") != expected_approval_status:
            errors.append(
                f"patch_results[{index}].approval_status must be {expected_approval_status} "
                "based on source approval plan"
            )
        replacement = as_obj(patch.get("replacement_source"))
        stable_id = str(patch.get("stable_internal_id") or "")
        source_item = source_items.get(stable_id)

        for key in ("candidate_id", "component_id", "stable_internal_id"):
            if result.get(key) != patch.get(key):
                errors.append(f"patch_results[{index}].{key} must match source patch")
        for key in ("media_kind", "file_type"):
            if result.get(key) != replacement.get(key):
                errors.append(f"patch_results[{index}].{key} must match source patch replacement")
        if result.get("candidate_local_path") != replacement.get("candidate_local_path"):
            errors.append(f"patch_results[{index}].candidate_local_path must match source patch")
        if result.get("candidate_sha256") != replacement.get("candidate_sha256"):
            errors.append(f"patch_results[{index}].candidate_sha256 must match source patch")
        if result.get("target_local_path") != patch.get("proposed_processed_local_path"):
            errors.append(f"patch_results[{index}].target_local_path must match proposed_processed_local_path")
        if result.get("target_public_url") != patch.get("proposed_public_url"):
            errors.append(f"patch_results[{index}].target_public_url must match proposed_public_url")
        if source_item and result.get("target_sha256_before") != source_item.get("sha256"):
            errors.append(f"patch_results[{index}].target_sha256_before must match source manifest")

        status = result.get("apply_status")
        if status == "applied_to_replacement_manifest":
            if result.get("approval_status") != "approved":
                errors.append(f"patch_results[{index}] applied result must be approved")
            if patch.get("patch_status") != "ready_for_developer_apply":
                errors.append(f"patch_results[{index}] applied result requires ready_for_developer_apply")
            if replacement.get("media_kind") not in SINGLE_IMAGE_KINDS:
                errors.append(f"patch_results[{index}] applied result requires svg/png/webp replacement_source")
            for candidate_error in candidate_file_errors(replacement):
                errors.append(f"patch_results[{index}] {candidate_error}")
            output_item = output_items.get(stable_id)
            proposed_item = as_obj(patch.get("proposed_manifest_item"))
            if output_manifest is None or output_item is None:
                errors.append(f"patch_results[{index}] applied result requires output manifest item")
            else:
                for key in ("media_kind", "file_type", "local_path", "url", "sha256", "width", "height", "source_kind"):
                    if output_item.get(key) != proposed_item.get(key):
                        errors.append(f"patch_results[{index}] output manifest item {key} must match proposed manifest item")
                if output_item.get("sha256") != result.get("target_sha256_after"):
                    errors.append(f"patch_results[{index}].target_sha256_after must match output manifest item")
        elif status == "skipped_not_approved":
            if result.get("approval_status") != "not_approved":
                errors.append(f"patch_results[{index}] skipped result must have approval_status=not_approved")
            if result.get("target_sha256_after") != result.get("target_sha256_before"):
                errors.append(f"patch_results[{index}] skipped result must not change target sha")
        elif status == "blocked":
            if result.get("approval_status") != "approved":
                errors.append(f"patch_results[{index}] blocked result must be an approved but rejected patch")
        if result.get("candidate_file_copied") and status == "skipped_not_approved":
            errors.append(f"patch_results[{index}] skipped results must not copy candidate files")


def validate_summary_and_status(report: dict[str, Any], patch_plan: dict[str, Any], source_manifest: dict[str, Any], errors: list[str]) -> None:
    results = [result for result in as_list(report.get("patch_results")) if isinstance(result, dict)]
    status_counts = Counter(str(result.get("apply_status")) for result in results)
    applied_count = status_counts.get("applied_to_replacement_manifest", 0)
    skipped_count = status_counts.get("skipped_not_approved", 0)
    blocked_count = status_counts.get("blocked", 0)
    approved_count = applied_count + blocked_count
    patches = [patch for patch in as_list(patch_plan.get("patches")) if isinstance(patch, dict)]
    media_kind_counts = Counter(
        str(result.get("media_kind") or "unknown")
        for result in results
        if result.get("apply_status") == "applied_to_replacement_manifest"
    )
    summary = as_obj(report.get("summary"))
    expected = {
        "source_patch_count": len(patches),
        "approved_patch_count": approved_count,
        "applied_patch_count": applied_count,
        "skipped_patch_count": skipped_count,
        "blocked_patch_count": blocked_count,
        "ready_patch_count": sum(1 for patch in patches if patch.get("patch_status") == "ready_for_developer_apply"),
        "manifest_item_count": len(as_list(source_manifest.get("items"))),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("media_kind_counts")) != dict(sorted(media_kind_counts.items())):
        errors.append("summary.media_kind_counts must match applied patch results")

    if blocked_count:
        expected_status = "blocked"
    elif applied_count:
        expected_status = "replacement_manifest_built"
    else:
        expected_status = "no_approved_patches"
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on patch results")


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(report, schema))
    scan_forbidden_key_fragments(report, "", errors)
    scan_external_urls(report, "", errors)

    if report.get("schema_version") != "map_component_manifest_apply_report.v0.2":
        errors.append("schema_version must be 'map_component_manifest_apply_report.v0.2'")
    usage_policy = set(map(str, as_list(report.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")
    runtime_effect = as_obj(report.get("runtime_effect"))
    for key in FALSE_EFFECT_FIELDS:
        if runtime_effect.get(key) is not False:
            errors.append(f"runtime_effect.{key} must be false")
    if runtime_effect.get("candidate_file_copied") is not any(
        bool(result.get("candidate_file_copied"))
        for result in as_list(report.get("patch_results"))
        if isinstance(result, dict)
    ):
        errors.append("runtime_effect.candidate_file_copied must reflect patch_results")

    source_manifest_path_value = report.get("source_manifest_path")
    if isinstance(source_manifest_path_value, str):
        source_manifest_path = resolve_repo_path(source_manifest_path_value)
        if source_manifest_path.exists():
            expected_sha = sha256_file(source_manifest_path)
            if as_obj(report.get("manifest_sha")).get("source_manifest_file_sha256_before") != expected_sha:
                errors.append("manifest_sha.source_manifest_file_sha256_before must match source manifest")

    patch_plan = load_source_patch_plan(report, errors)
    approved_patch_ids, approved_candidate_ids = load_and_validate_approval_plan(
        report, patch_plan, errors
    )
    source_manifest = load_source_manifest(report, errors)
    output_manifest = validate_output_manifest(report, errors)
    if output_manifest is None and source_manifest:
        expected_content_sha = sha256_json(source_manifest)
        if as_obj(report.get("manifest_sha")).get("replacement_manifest_content_sha256_after") != expected_content_sha:
            errors.append(
                "manifest_sha.replacement_manifest_content_sha256_after must match source manifest "
                "when no output manifest is written"
            )
    if report.get("output_manifest_path") is not None and not any(
        result.get("apply_status") == "applied_to_replacement_manifest"
        for result in as_list(report.get("patch_results"))
        if isinstance(result, dict)
    ):
        errors.append("output_manifest_path requires at least one applied patch result")
    validate_patch_results(
        report,
        patch_plan,
        source_manifest,
        output_manifest,
        approved_patch_ids,
        approved_candidate_ids,
        errors,
    )
    validate_summary_and_status(report, patch_plan, source_manifest, errors)
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentManifestApplyReport v0.2.")
    parser.add_argument("report", help="Report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID MapComponentManifestApplyReport v0.2")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentManifestApplyReport v0.2")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID MapComponentManifestApplyReport v0.2")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    errors = validate_report(report, schema_obj)
    if errors:
        print("INVALID MapComponentManifestApplyReport v0.2")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print(f"OK: {report_path}")
    print(f"- status: {report.get('status')}")
    print(f"- applied_patch_count: {summary.get('applied_patch_count')}")
    print(f"- skipped_patch_count: {summary.get('skipped_patch_count')}")
    print(f"- blocked_patch_count: {summary.get('blocked_patch_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
