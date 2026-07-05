#!/usr/bin/env python3
"""Build a v0.2-aware MapComponent manifest patch proposal plan."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_component_manifest_patch_plan.v0.2"
DEFAULT_PROMOTION_GATE = ROOT / "examples/review_packs/map_component_promotion_gate_report.v0.1.json"
DEFAULT_SOURCE_MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.2.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_component_manifest_patch_plan.v0.2.json"

USAGE_POLICY = [
    "review_only_manifest_patch_proposal",
    "v0_2_single_image_manifest_replacement_preview",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_manifest_write",
    "no_candidate_file_copy",
    "no_style_pack_or_render_plan_mutation",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
    "no_secret_material",
]
RUNTIME_EFFECT = {
    "manifest_replacement_written": False,
    "style_pack_modified": False,
    "render_plan_modified": False,
    "frontend_default_modified": False,
    "runtime_map_truth_modified": False,
    "candidate_file_copied": False,
}
READY_NEXT_ACTIONS = [
    "developer reviews v0.2 patch proposal",
    "developer confirms candidate file may replace the reviewed baseline media item",
    "run explicit v0.2 manifest replacement apply if approved",
    "rerun MapComponentMediaManifest v0.2 validation after explicit apply",
    "rerun StylePack binding, frontend contract, and demo evidence after explicit apply",
]
SINGLE_IMAGE_KINDS = {"svg", "png", "webp"}
MEDIA_KIND_TO_SUFFIX = {
    "svg": ".svg",
    "png": ".png",
    "webp": ".webp",
}


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


def allowed_decisions(promotion_gate: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        decision
        for decision in as_list(promotion_gate.get("decisions"))
        if isinstance(decision, dict)
        and decision.get("candidate_kind") == "generated_candidate"
        and decision.get("decision") == "allowed"
        and decision.get("promotion_allowed") is True
    ]


def generated_candidates_by_id(candidate_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict) and candidate.get("candidate_kind") == "generated_candidate"
    }


def visual_items_by_candidate_id(visual_quality_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("candidate_id") or ""): item
        for item in as_list(visual_quality_report.get("items"))
        if isinstance(item, dict)
    }


def manifest_items_by_stable_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("stable_internal_id") or ""): item
        for item in as_list(manifest.get("items"))
        if isinstance(item, dict)
    }


def file_type_from_path(path_value: str) -> str:
    suffix = Path(path_value).suffix.lower().lstrip(".")
    return suffix if suffix in SINGLE_IMAGE_KINDS else "unknown"


def media_kind_from_candidate(candidate: dict[str, Any], file_type: str) -> str:
    declared = str(candidate.get("media_kind") or candidate.get("target_media_kind") or "")
    if declared in {*SINGLE_IMAGE_KINDS, "atlas_animation"}:
        return declared
    return file_type if file_type in SINGLE_IMAGE_KINDS else "unknown"


def target_manifest_summary(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "stable_internal_id": item.get("stable_internal_id"),
        "asset_id": item.get("asset_id"),
        "asset_type": item.get("asset_type"),
        "media_role": item.get("media_role"),
        "media_layer": item.get("media_layer"),
        "media_kind": item.get("media_kind"),
        "component_role": item.get("component_role"),
        "style_pack_id": item.get("style_pack_id"),
        "node_id": item.get("node_id"),
        "source_owner_id": item.get("source_owner_id"),
        "source_binding": item.get("source_binding"),
        "local_path": item.get("local_path"),
        "url": item.get("url"),
        "sha256": item.get("sha256"),
        "width": item.get("width"),
        "height": item.get("height"),
        "file_type": item.get("file_type"),
        "source_kind": item.get("source_kind"),
        "usage_policy": as_list(item.get("usage_policy")),
    }


def replacement_source(candidate: dict[str, Any], visual_item: dict[str, Any] | None) -> dict[str, Any]:
    path_value = str(candidate.get("candidate_local_path") or "")
    file_checks = as_obj(visual_item.get("file_checks")) if visual_item else {}
    target_size = as_obj(candidate.get("target_size"))
    file_type = str(file_checks.get("extension") or file_type_from_path(path_value))
    media_kind = media_kind_from_candidate(candidate, file_type)
    return {
        "candidate_local_path": path_value,
        "candidate_sha256": candidate.get("candidate_sha256"),
        "media_kind": media_kind,
        "file_type": file_type,
        "width": file_checks.get("width") or target_size.get("width"),
        "height": file_checks.get("height") or target_size.get("height"),
    }


def proposed_processed_paths(stable_internal_id: str, file_type: str) -> tuple[str | None, str | None]:
    suffix = MEDIA_KIND_TO_SUFFIX.get(file_type)
    if suffix is None:
        return None, None
    local_path = f"game_data/media/map_components/processed/{stable_internal_id}{suffix}"
    url = f"/assets/map_components/processed/{stable_internal_id}{suffix}"
    return local_path, url


def proposed_manifest_item(
    *,
    manifest_item: dict[str, Any] | None,
    replacement: dict[str, Any],
    proposed_local_path: str | None,
    proposed_url: str | None,
) -> dict[str, Any] | None:
    file_type = str(replacement.get("file_type") or "")
    media_kind = str(replacement.get("media_kind") or "")
    if manifest_item is None or media_kind not in SINGLE_IMAGE_KINDS:
        return None
    if proposed_local_path is None or proposed_url is None:
        return None
    width = replacement.get("width")
    height = replacement.get("height")
    sha256 = replacement.get("candidate_sha256")
    if not isinstance(width, int) or not isinstance(height, int) or not isinstance(sha256, str):
        return None
    return {
        "media_kind": media_kind,
        "file_type": file_type,
        "local_path": proposed_local_path,
        "url": proposed_url,
        "sha256": sha256,
        "width": width,
        "height": height,
        "source_kind": "generated_candidate_reviewed_media",
    }


def patch_status_and_actions(
    *,
    decision: dict[str, Any],
    candidate: dict[str, Any] | None,
    visual_item: dict[str, Any] | None,
    manifest_item: dict[str, Any] | None,
    media_kind: str,
) -> tuple[str, bool, list[str]]:
    compatible = media_kind in SINGLE_IMAGE_KINDS
    if decision.get("promotion_allowed") is not True or decision.get("decision") != "allowed":
        return (
            "blocked_candidate_not_allowed",
            compatible,
            ["rerun promotion gate after candidate review and visual quality both pass"],
        )
    if candidate is None or candidate.get("review_status") != "passed" or candidate.get("promotion_allowed_now") is not True:
        return (
            "blocked_candidate_not_allowed",
            compatible,
            ["approve candidate review before proposing a manifest replacement"],
        )
    if visual_item is None or visual_item.get("review_status") != "passed":
        return (
            "blocked_visual_not_passed",
            compatible,
            ["approve visual quality and cutout review before proposing a manifest replacement"],
        )
    if manifest_item is None:
        return (
            "blocked_missing_manifest_item",
            compatible,
            ["add or restore the target reviewed manifest item before planning replacement"],
        )
    if media_kind == "atlas_animation":
        return (
            "blocked_atlas_not_supported_by_apply_v0_2",
            False,
            ["v0.2 apply currently accepts only svg/png/webp single-image replacements"],
        )
    if not compatible:
        return (
            "blocked_manifest_schema_incompatible",
            False,
            ["import candidate as svg, png, or webp single-image media before v0.2 manifest apply"],
        )
    return "ready_for_developer_apply", True, READY_NEXT_ACTIONS


def build_patch(
    decision: dict[str, Any],
    *,
    candidate: dict[str, Any] | None,
    visual_item: dict[str, Any] | None,
    manifest_item: dict[str, Any] | None,
) -> dict[str, Any]:
    component_id = str(decision.get("component_id") or "")
    candidate_id = str(decision.get("candidate_id") or "")
    stable_internal_id = str((manifest_item or {}).get("stable_internal_id") or component_id)
    replacement = replacement_source(candidate or {}, visual_item)
    file_type = str(replacement.get("file_type") or "unknown")
    media_kind = str(replacement.get("media_kind") or "unknown")
    proposed_local_path, proposed_url = proposed_processed_paths(stable_internal_id, file_type)
    patch_status, compatible, required_next_actions = patch_status_and_actions(
        decision=decision,
        candidate=candidate,
        visual_item=visual_item,
        manifest_item=manifest_item,
        media_kind=media_kind,
    )
    proposed_item = proposed_manifest_item(
        manifest_item=manifest_item,
        replacement=replacement,
        proposed_local_path=proposed_local_path,
        proposed_url=proposed_url,
    )
    return {
        "patch_id": f"{stable_internal_id}.manifest_patch_proposal_v0_2",
        "candidate_id": candidate_id,
        "component_id": component_id,
        "stable_internal_id": stable_internal_id,
        "target_manifest_item_found": manifest_item is not None,
        "target_manifest_item": target_manifest_summary(manifest_item),
        "replacement_source": replacement,
        "visual_quality_item_status": visual_item.get("review_status") if visual_item else None,
        "candidate_review_status": str(candidate.get("review_status") if candidate else "missing"),
        "patch_status": patch_status,
        "manifest_schema_compatible_now": compatible,
        "proposed_processed_local_path": proposed_local_path if compatible else None,
        "proposed_public_url": proposed_url if compatible else None,
        "proposed_manifest_item": proposed_item if compatible else None,
        "required_next_actions": required_next_actions,
    }


def build_plan(
    promotion_gate_path: Path,
    *,
    source_manifest_path: Path,
    output_path: Path,
    created_at: str | None,
) -> dict[str, Any]:
    promotion_gate = as_obj(load_json(promotion_gate_path))
    candidate_review_path = resolve_path(str(promotion_gate.get("source_candidate_review_report_path") or ""))
    visual_quality_path = resolve_path(str(promotion_gate.get("source_visual_quality_report_path") or ""))
    candidate_review = as_obj(load_json(candidate_review_path))
    visual_quality_report = as_obj(load_json(visual_quality_path))
    manifest = as_obj(load_json(source_manifest_path))

    candidates = generated_candidates_by_id(candidate_review)
    visual_items = visual_items_by_candidate_id(visual_quality_report)
    manifest_items = manifest_items_by_stable_id(manifest)
    decisions = allowed_decisions(promotion_gate)
    patches = [
        build_patch(
            decision,
            candidate=candidates.get(str(decision.get("candidate_id") or "")),
            visual_item=visual_items.get(str(decision.get("candidate_id") or "")),
            manifest_item=manifest_items.get(str(decision.get("component_id") or "")),
        )
        for decision in decisions
    ]
    status_counts = Counter(str(patch.get("patch_status")) for patch in patches)
    media_kind_counts = Counter(
        str(as_obj(patch.get("replacement_source")).get("media_kind") or "unknown")
        for patch in patches
    )
    ready_count = status_counts.get("ready_for_developer_apply", 0)
    blocked_count = len(patches) - ready_count
    if not decisions:
        status = "no_allowed_candidates"
    elif blocked_count:
        status = "blocked"
    else:
        status = "ready_for_developer_apply"

    summary = {
        "allowed_decision_count": len(decisions),
        "patch_count": len(patches),
        "blocked_patch_count": blocked_count,
        "ready_patch_count": ready_count,
        "manifest_item_count": len(as_list(manifest.get("items"))),
        "single_image_ready_patch_count": sum(
            1
            for patch in patches
            if patch.get("patch_status") == "ready_for_developer_apply"
            and as_obj(patch.get("replacement_source")).get("media_kind") in SINGLE_IMAGE_KINDS
        ),
        "atlas_blocked_patch_count": status_counts.get("blocked_atlas_not_supported_by_apply_v0_2", 0),
        "media_kind_counts": dict(sorted(media_kind_counts.items())),
        "runtime_effect": RUNTIME_EFFECT,
    }
    return {
        "schema_version": REPORT_VERSION,
        "plan_id": "map_component_manifest_patch_plan_v0_2",
        "created_at": created_at or str(promotion_gate.get("created_at") or manifest.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_promotion_gate_report_path": rel_or_abs(promotion_gate_path),
        "source_candidate_review_report_path": rel_or_abs(candidate_review_path),
        "source_visual_quality_report_path": rel_or_abs(visual_quality_path),
        "source_manifest_path": rel_or_abs(source_manifest_path),
        "source_manifest_schema_version": "map_component_media_manifest.v0.2",
        "status": status,
        "usage_policy": USAGE_POLICY,
        "summary": summary,
        "patches": patches,
        "runtime_effect": RUNTIME_EFFECT,
        "validation": {
            "validator": "tools/media/validate_map_component_manifest_patch_plan_v02.py",
            "commands": [
                f"python3 tools/media/validate_map_component_manifest_patch_plan_v02.py {rel_or_abs(output_path)}"
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapComponentManifestPatchPlan v0.2.")
    parser.add_argument("--promotion-gate-report", default=str(DEFAULT_PROMOTION_GATE))
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    promotion_gate_path = resolve_path(args.promotion_gate_report)
    source_manifest_path = resolve_path(args.source_manifest)
    output_path = resolve_path(args.output)
    plan = build_plan(
        promotion_gate_path,
        source_manifest_path=source_manifest_path,
        output_path=output_path,
        created_at=args.created_at,
    )
    write_json(output_path, plan)
    summary = as_obj(plan.get("summary"))
    print(f"OK: wrote {output_path}")
    print(f"- status: {plan['status']}")
    print(f"- patch_count: {summary.get('patch_count')}")
    print(f"- ready_patch_count: {summary.get('ready_patch_count')}")
    print(f"- media_kind_counts: {summary.get('media_kind_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
