#!/usr/bin/env python3
"""Validate MapComponentManifestPatchPlan v0.1."""

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

import validate_map_component_candidate_review_report as candidate_validator  # noqa: E402
import validate_map_component_media_pack as manifest_validator  # noqa: E402
import validate_map_component_promotion_gate_report as promotion_validator  # noqa: E402
import validate_map_component_visual_quality_report as visual_validator  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_manifest_patch_plan.v0.1.schema.json"
DEFAULT_CANDIDATE_SCHEMA = ROOT / "shared/schemas/map_component_candidate_review_report.v0.1.schema.json"
DEFAULT_VISUAL_SCHEMA = ROOT / "shared/schemas/map_component_visual_quality_report.v0.1.schema.json"
DEFAULT_PROMOTION_SCHEMA = ROOT / "shared/schemas/map_component_promotion_gate_report.v0.1.schema.json"
DEFAULT_MANIFEST_SCHEMA = ROOT / "shared/schemas/map_component_media_manifest.v0.1.schema.json"

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
    "review_only_manifest_patch_proposal",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_manifest_write",
    "no_candidate_file_copy",
    "no_style_pack_or_render_plan_mutation",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
    "no_secret_material",
}
FALSE_EFFECT_FIELDS = {
    "manifest_replacement_written",
    "style_pack_modified",
    "render_plan_modified",
    "frontend_default_modified",
    "runtime_map_truth_modified",
    "candidate_file_copied",
}


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


def rel_or_abs(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def load_source_report(
    report: dict[str, Any],
    field: str,
    expected_version: str,
    errors: list[str],
) -> dict[str, Any]:
    source_value = report.get(field)
    if not isinstance(source_value, str) or not source_value.strip():
        errors.append(f"{field} must be a non-empty string")
        return {}
    source_path = resolve_repo_path(source_value)
    if not source_path.exists():
        errors.append(f"{field} does not exist: {source_value}")
        return {}
    try:
        source = load_json(source_path)
    except json.JSONDecodeError as exc:
        errors.append(f"{field} is not valid JSON: {exc}")
        return {}
    if not isinstance(source, dict):
        errors.append(f"{field} root must be an object")
        return {}
    if source.get("schema_version") != expected_version:
        errors.append(f"{field} must be {expected_version}")
    return source


def validate_manifest(manifest: dict[str, Any], errors: list[str]) -> None:
    schema = load_json(DEFAULT_MANIFEST_SCHEMA) if DEFAULT_MANIFEST_SCHEMA.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    for error in manifest_validator.validate_manifest(manifest, schema_obj):
        errors.append(f"source manifest invalid: {error}")


def file_type_from_path(path_value: str) -> str:
    suffix = Path(path_value).suffix.lower().lstrip(".")
    return suffix if suffix in {"svg", "png", "webp"} else "unknown"


def allowed_decisions_by_candidate_id(promotion_gate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(decision.get("candidate_id") or ""): decision
        for decision in as_list(promotion_gate.get("decisions"))
        if isinstance(decision, dict)
        and decision.get("candidate_kind") == "generated_candidate"
        and decision.get("decision") == "allowed"
        and decision.get("promotion_allowed") is True
    }


def generated_candidates_by_id(candidate_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict) and candidate.get("candidate_kind") == "generated_candidate"
    }


def visual_items_by_candidate_id(visual_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("candidate_id") or ""): item
        for item in as_list(visual_report.get("items"))
        if isinstance(item, dict)
    }


def manifest_items_by_stable_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("stable_internal_id") or ""): item
        for item in as_list(manifest.get("items"))
        if isinstance(item, dict)
    }


def validate_source_reports(
    report: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    promotion_gate = load_source_report(
        report,
        "source_promotion_gate_report_path",
        "map_component_promotion_gate_report.v0.1",
        errors,
    )
    candidate_review = load_source_report(
        report,
        "source_candidate_review_report_path",
        "map_component_candidate_review_report.v0.1",
        errors,
    )
    visual_report = load_source_report(
        report,
        "source_visual_quality_report_path",
        "map_component_visual_quality_report.v0.1",
        errors,
    )
    manifest = load_source_report(
        report,
        "source_manifest_path",
        "map_component_media_manifest.v0.1",
        errors,
    )

    if promotion_gate:
        schema = load_json(DEFAULT_PROMOTION_SCHEMA) if DEFAULT_PROMOTION_SCHEMA.exists() else None
        schema_obj = schema if isinstance(schema, dict) else None
        for source_error in promotion_validator.validate_report(promotion_gate, schema_obj):
            errors.append(f"source promotion gate invalid: {source_error}")
        expected_sources = {
            "source_candidate_review_report_path": report.get("source_candidate_review_report_path"),
            "source_visual_quality_report_path": report.get("source_visual_quality_report_path"),
            "source_manifest_path": report.get("source_manifest_path"),
        }
        for key, expected in expected_sources.items():
            if promotion_gate.get(key) != expected:
                errors.append(f"{key} must match source promotion gate")

    if candidate_review:
        schema = load_json(DEFAULT_CANDIDATE_SCHEMA) if DEFAULT_CANDIDATE_SCHEMA.exists() else None
        schema_obj = schema if isinstance(schema, dict) else None
        for source_error in candidate_validator.validate_report(candidate_review, schema_obj):
            errors.append(f"source candidate review invalid: {source_error}")

    if visual_report:
        schema = load_json(DEFAULT_VISUAL_SCHEMA) if DEFAULT_VISUAL_SCHEMA.exists() else None
        schema_obj = schema if isinstance(schema, dict) else None
        for source_error in visual_validator.validate_report(visual_report, schema_obj):
            errors.append(f"source visual quality invalid: {source_error}")

    if manifest:
        validate_manifest(manifest, errors)

    return promotion_gate, candidate_review, visual_report, manifest


def validate_ready_patch(
    patch: dict[str, Any],
    *,
    index: int,
    decision: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    visual_item: dict[str, Any] | None,
    manifest_item: dict[str, Any] | None,
    errors: list[str],
) -> None:
    candidate_id = str(patch.get("candidate_id") or "")
    if decision is None:
        errors.append(f"patches[{index}] has no matching allowed promotion gate decision: {candidate_id}")
        return
    if candidate is None:
        errors.append(f"patches[{index}] has no matching generated candidate review item: {candidate_id}")
        return
    if visual_item is None:
        errors.append(f"patches[{index}] has no matching visual quality item: {candidate_id}")
        return
    if manifest_item is None:
        errors.append(f"patches[{index}] has no matching manifest item")
        return

    if candidate.get("review_status") != "passed":
        errors.append(f"patches[{index}] ready patch requires candidate review_status=passed")
    if candidate.get("promotion_recommendation") != "eligible_for_promotion":
        errors.append(f"patches[{index}] ready patch requires candidate promotion_recommendation=eligible_for_promotion")
    if candidate.get("promotion_allowed_now") is not True:
        errors.append(f"patches[{index}] ready patch requires candidate promotion_allowed_now=true")
    if visual_item.get("review_status") != "passed":
        errors.append(f"patches[{index}] ready patch requires passed visual quality item")

    component_id = patch.get("component_id")
    stable_internal_id = patch.get("stable_internal_id")
    target_summary = as_obj(patch.get("target_manifest_item"))
    if component_id != decision.get("component_id"):
        errors.append(f"patches[{index}].component_id must match promotion decision")
    if stable_internal_id != manifest_item.get("stable_internal_id"):
        errors.append(f"patches[{index}].stable_internal_id must match manifest stable_internal_id")
    if candidate.get("component_id") not in {component_id, stable_internal_id}:
        errors.append(f"patches[{index}] candidate component_id must match patch component/stable id")
    expected_target_summary = {
        "local_path": manifest_item.get("local_path"),
        "url": manifest_item.get("url"),
        "sha256": manifest_item.get("sha256"),
        "width": manifest_item.get("width"),
        "height": manifest_item.get("height"),
        "source_kind": manifest_item.get("source_kind"),
        "style_pack_id": manifest_item.get("style_pack_id"),
        "node_id": manifest_item.get("node_id"),
        "component_role": manifest_item.get("component_role"),
        "source_binding": manifest_item.get("source_binding"),
        "media_role": manifest_item.get("media_role"),
    }
    if target_summary != expected_target_summary:
        errors.append(f"patches[{index}].target_manifest_item must match source manifest item summary")

    path_value = candidate.get("candidate_local_path")
    declared_sha = candidate.get("candidate_sha256")
    replacement = as_obj(patch.get("replacement_source"))
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"patches[{index}] ready patch requires candidate_local_path")
    elif replacement.get("candidate_local_path") != path_value:
        errors.append(f"patches[{index}].replacement_source.candidate_local_path must match candidate review")
    if not isinstance(declared_sha, str) or not declared_sha.strip():
        errors.append(f"patches[{index}] ready patch requires candidate_sha256")
    elif replacement.get("candidate_sha256") != declared_sha:
        errors.append(f"patches[{index}].replacement_source.candidate_sha256 must match candidate review")
    if isinstance(path_value, str) and isinstance(declared_sha, str):
        candidate_path = resolve_repo_path(path_value)
        if not candidate_path.exists():
            errors.append(f"patches[{index}] candidate file does not exist: {path_value}")
        elif sha256_file(candidate_path) != declared_sha:
            errors.append(f"patches[{index}] candidate sha does not match local file")

    file_type = replacement.get("file_type") or file_type_from_path(str(path_value or ""))
    if file_type != "svg":
        errors.append(f"patches[{index}] ready patch must be SVG-compatible with MapComponentMediaManifest v0.1")
    if patch.get("manifest_schema_compatible_now") is not True:
        errors.append(f"patches[{index}] ready patch must set manifest_schema_compatible_now=true")
    if patch.get("proposed_processed_local_path") != manifest_item.get("local_path"):
        errors.append(f"patches[{index}].proposed_processed_local_path must reuse current processed SVG target")
    if patch.get("proposed_public_url") != manifest_item.get("url"):
        errors.append(f"patches[{index}].proposed_public_url must reuse current processed SVG URL")


def validate_patches_against_sources(
    report: dict[str, Any],
    promotion_gate: dict[str, Any],
    candidate_review: dict[str, Any],
    visual_report: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    allowed_decisions = allowed_decisions_by_candidate_id(promotion_gate)
    candidates = generated_candidates_by_id(candidate_review)
    visual_items = visual_items_by_candidate_id(visual_report)
    manifest_items = manifest_items_by_stable_id(manifest)
    patches = [patch for patch in as_list(report.get("patches")) if isinstance(patch, dict)]
    patch_ids = [str(patch.get("candidate_id") or "") for patch in patches]
    if set(patch_ids) != set(allowed_decisions):
        errors.append("patches candidate_id set must match promotion gate allowed generated decisions")
    duplicates = sorted({candidate_id for candidate_id in patch_ids if patch_ids.count(candidate_id) > 1})
    for candidate_id in duplicates:
        errors.append(f"duplicate patch candidate_id: {candidate_id}")

    if not allowed_decisions and patches:
        errors.append("patches must be empty when promotion gate has no allowed generated candidates")

    for index, patch in enumerate(patches):
        candidate_id = str(patch.get("candidate_id") or "")
        component_id = str(patch.get("component_id") or "")
        decision = allowed_decisions.get(candidate_id)
        candidate = candidates.get(candidate_id)
        visual_item = visual_items.get(candidate_id)
        manifest_item = manifest_items.get(component_id)
        replacement = as_obj(patch.get("replacement_source"))
        file_type = str(replacement.get("file_type") or file_type_from_path(str(replacement.get("candidate_local_path") or "")))
        schema_compatible = file_type == "svg"

        if decision and patch.get("component_id") != decision.get("component_id"):
            errors.append(f"patches[{index}].component_id must match allowed promotion decision")
        if patch.get("stable_internal_id") != component_id:
            errors.append(f"patches[{index}].stable_internal_id must equal component_id for v0.1 manifest lookup")
        if patch.get("target_manifest_item_found") is not (manifest_item is not None):
            errors.append(f"patches[{index}].target_manifest_item_found must reflect source manifest lookup")
        if patch.get("visual_quality_item_status") != (visual_item.get("review_status") if visual_item else None):
            errors.append(f"patches[{index}].visual_quality_item_status must match visual quality item")
        if patch.get("candidate_review_status") != str(candidate.get("review_status") if candidate else "missing"):
            errors.append(f"patches[{index}].candidate_review_status must match candidate review")
        if patch.get("manifest_schema_compatible_now") is not schema_compatible:
            errors.append(f"patches[{index}].manifest_schema_compatible_now must reflect current SVG-only manifest schema")

        status = patch.get("patch_status")
        if file_type in {"png", "webp"} and status == "ready_for_developer_apply":
            errors.append(f"patches[{index}] cannot mark PNG/WebP candidate ready under v0.1 manifest schema")
        if status == "ready_for_developer_apply":
            validate_ready_patch(
                patch,
                index=index,
                decision=decision,
                candidate=candidate,
                visual_item=visual_item,
                manifest_item=manifest_item,
                errors=errors,
            )
        elif status == "blocked_manifest_schema_incompatible" and file_type == "svg":
            errors.append(f"patches[{index}] SVG candidate should not be schema-incompatible")
        elif status == "blocked_missing_manifest_item" and manifest_item is not None:
            errors.append(f"patches[{index}] cannot be blocked_missing_manifest_item when target exists")
        elif status == "blocked_visual_not_passed" and visual_item and visual_item.get("review_status") == "passed":
            errors.append(f"patches[{index}] cannot be blocked_visual_not_passed when visual item passed")
        elif status == "blocked_candidate_not_allowed" and decision is not None:
            errors.append(f"patches[{index}] cannot be blocked_candidate_not_allowed for an allowed decision")

        if not as_list(patch.get("required_next_actions")):
            errors.append(f"patches[{index}].required_next_actions must not be empty")


def validate_summary_and_status(
    report: dict[str, Any],
    promotion_gate: dict[str, Any],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    patches = [patch for patch in as_list(report.get("patches")) if isinstance(patch, dict)]
    allowed_count = len(allowed_decisions_by_candidate_id(promotion_gate))
    status_counts = Counter(str(patch.get("patch_status")) for patch in patches)
    ready_count = status_counts.get("ready_for_developer_apply", 0)
    blocked_count = len(patches) - ready_count
    summary = as_obj(report.get("summary"))
    expected = {
        "allowed_decision_count": allowed_count,
        "patch_count": len(patches),
        "blocked_patch_count": blocked_count,
        "ready_patch_count": ready_count,
        "manifest_item_count": len(as_list(manifest.get("items"))),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("runtime_effect")) != as_obj(report.get("runtime_effect")):
        errors.append("summary.runtime_effect must match top-level runtime_effect")

    if allowed_count == 0:
        expected_status = "no_allowed_candidates"
        if patches:
            errors.append("no_allowed_candidates plans must not contain patches")
    elif blocked_count:
        expected_status = "blocked"
    else:
        expected_status = "ready_for_developer_apply"
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on allowed decisions and patches")


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(report, schema))
    scan_forbidden_key_fragments(report, "", errors)
    scan_external_urls(report, "", errors)

    if report.get("schema_version") != "map_component_manifest_patch_plan.v0.1":
        errors.append("schema_version must be 'map_component_manifest_patch_plan.v0.1'")

    usage_policy = set(map(str, as_list(report.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    runtime_effect = as_obj(report.get("runtime_effect"))
    for key in FALSE_EFFECT_FIELDS:
        if runtime_effect.get(key) is not False:
            errors.append(f"runtime_effect.{key} must be false; this plan is review-only")

    promotion_gate, candidate_review, visual_report, manifest = validate_source_reports(report, errors)
    validate_patches_against_sources(
        report,
        promotion_gate,
        candidate_review,
        visual_report,
        manifest,
        errors,
    )
    validate_summary_and_status(report, promotion_gate, manifest, errors)
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentManifestPatchPlan v0.1.")
    parser.add_argument("plan", help="Plan JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    plan_path = Path(args.plan)
    schema_path = Path(args.schema)
    try:
        report = load_json(plan_path)
    except FileNotFoundError:
        print("INVALID MapComponentManifestPatchPlan")
        print(f"- plan file not found: {plan_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentManifestPatchPlan")
        print(f"- plan is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID MapComponentManifestPatchPlan")
        print("- plan root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    errors = validate_report(report, schema_obj)
    if errors:
        print("INVALID MapComponentManifestPatchPlan")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print(f"OK: {plan_path}")
    print(f"- status: {report.get('status')}")
    print(f"- patch_count: {summary.get('patch_count')}")
    print(f"- ready_patch_count: {summary.get('ready_patch_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
