#!/usr/bin/env python3
"""Build the CoreArtifactAlignmentReport v0.1 evidence artifact.

The report is intentionally offline and deterministic. It audits whether
reviewed packages carry native ContextPackage / FactEntry / CGOP /
WorldStateDeltaTransaction evidence, but never promotes review-only artifacts
or mutates runtime/world state.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
WORLD_STATE_DIR = ROOT / "tools" / "world_state"
for path in (ASSET_GRAPH_DIR, WORLD_STATE_DIR, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validation_common import load_json  # noqa: E402
from validate_ai_compile_core_artifacts import (  # noqa: E402
    validate_ai_compile_core_artifact,
)
from validate_world_delta_transaction import validate_transaction  # noqa: E402


OUTPUT_PATH = ROOT / "examples/review_packs/core_artifact_alignment_report.v0.1.json"
FRONTEND_MOCK_PACK = ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json"
CONTEXT_PACKAGE = ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
FACT_ENTRY = ROOT / "examples/review_packs/mvp_gray_lantern.fact_entry.json"
CGOP = ROOT / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json"
WORLD_DELTA_TRANSACTION_DIR = ROOT / "examples/world_delta_transactions"
PROVIDER_STAGING = (
    ROOT / "examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json"
)
PROVIDER_PROMOTION = (
    ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json"
)

CORE_KEYS = (
    "context_package",
    "fact_entry",
    "compiled_game_object_package",
    "world_delta",
    "world_delta_transaction",
)
EMBEDDED_CORE_KEYS = (
    "context_package",
    "fact_entry",
    "compiled_game_object_package",
)
MIGRATION_CANDIDATE_SCHEMA_KEYWORDS = (
    "story_asset",
    "stage_candidate",
    "multistage",
    "compiler_review_dossier",
    "stage05_plan",
    "compilable_object_plan",
)


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def repo_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _validation_result(
    artifact_kind: str,
    errors: list[str],
    ref: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_kind": artifact_kind,
        "status": "passed" if not errors else "failed",
        "error_count": len(errors),
    }
    if ref:
        result["ref"] = ref
    if errors:
        result["errors"] = errors[:8]
    return result


def _core_artifact_errors(artifact_kind: str, artifact: dict[str, Any]) -> list[str]:
    if artifact_kind == "world_delta_transaction":
        return validate_transaction(artifact)
    if artifact_kind in EMBEDDED_CORE_KEYS:
        return validate_ai_compile_core_artifact(artifact)
    return []


def _target(
    *,
    target_id: str,
    target_kind: str,
    source_path: Path,
    alignment_state: str,
    expected_artifacts: list[str],
    present_artifacts: list[str],
    refs: dict[str, str] | None = None,
    validation_results: list[dict[str, Any]] | None = None,
    next_action: str,
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "target_kind": target_kind,
        "source_path": rel(source_path),
        "alignment_state": alignment_state,
        "review_only": True,
        "runtime_activation_allowed": False,
        "world_mutation_allowed": False,
        "expected_artifacts": expected_artifacts,
        "present_artifacts": present_artifacts,
        "refs": refs or {},
        "validation_results": validation_results or [],
        "next_action": next_action,
    }


def _validate_embedded_core(
    payload: dict[str, Any],
    refs: dict[str, str],
    artifact_keys: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key in artifact_keys:
        artifact = as_obj(payload.get(key))
        errors = _core_artifact_errors(key, artifact)
        results.append(_validation_result(key, errors, refs.get(key)))
    return results


def _frontend_mock_pack_target() -> dict[str, Any]:
    pack = load_json(FRONTEND_MOCK_PACK)
    core_artifacts = as_obj(pack.get("core_artifacts"))
    refs = {
        key: str(value)
        for key, value in as_obj(core_artifacts.get("refs")).items()
        if key in CORE_KEYS and isinstance(value, str)
    }
    present = [key for key in CORE_KEYS if key in core_artifacts or key in refs]
    validation_results = _validate_embedded_core(
        core_artifacts, refs, list(EMBEDDED_CORE_KEYS)
    )
    transaction = as_obj(core_artifacts.get("world_delta_transaction"))
    validation_results.append(
        _validation_result(
            "world_delta_transaction",
            validate_transaction(transaction),
            refs.get("world_delta_transaction"),
        )
    )
    state = (
        "native_snapshot_ready"
        if all(item["status"] == "passed" for item in validation_results)
        else "validation_failed"
    )
    return _target(
        target_id="frontend_mock_pack.core_artifacts",
        target_kind="frontend_mock_pack",
        source_path=FRONTEND_MOCK_PACK,
        alignment_state=state,
        expected_artifacts=[
            "context_package",
            "fact_entry",
            "compiled_game_object_package",
            "world_delta_transaction",
        ],
        present_artifacts=present,
        refs=refs,
        validation_results=validation_results,
        next_action=(
            "保持为 evidence / Studio 辅助字段；玩家 runtime 仍只消费 reviewed assets、runtime package 与 map package。"
        ),
    )


def _standalone_core_targets() -> list[dict[str, Any]]:
    specs = [
        ("context_package.example", "context_package", CONTEXT_PACKAGE),
        ("fact_entry.example", "fact_entry", FACT_ENTRY),
        ("cgop.example", "compiled_game_object_package", CGOP),
    ]
    targets: list[dict[str, Any]] = []
    for target_id, kind, path in specs:
        artifact = load_json(path)
        errors = validate_ai_compile_core_artifact(artifact)
        targets.append(
            _target(
                target_id=target_id,
                target_kind="core_artifact_example",
                source_path=path,
                alignment_state="native_snapshot_ready" if not errors else "validation_failed",
                expected_artifacts=[kind],
                present_artifacts=[kind],
                refs={kind: rel(path)},
                validation_results=[_validation_result(kind, errors, rel(path))],
                next_action="作为字段级示例和迁移锚点保留；不要直接写入玩家 runtime。",
            )
        )
    return targets


def _world_transaction_targets() -> list[dict[str, Any]]:
    paths = sorted(WORLD_DELTA_TRANSACTION_DIR.glob("*.world_delta_transaction.json"))
    targets: list[dict[str, Any]] = []
    chain_results: list[dict[str, Any]] = []
    chain_refs: dict[str, str] = {}
    for path in paths:
        transaction = load_json(path)
        errors = validate_transaction(transaction)
        ref = rel(path)
        chain_results.append(_validation_result("world_delta_transaction", errors, ref))
        chain_refs[path.stem] = ref
        if path.name == "first_battle_result.world_delta_transaction.json":
            targets.append(
                _target(
                    target_id="first_battle_result.world_delta_transaction",
                    target_kind="world_delta_transaction",
                    source_path=path,
                    alignment_state=(
                        "native_snapshot_ready" if not errors else "validation_failed"
                    ),
                    expected_artifacts=["world_delta_transaction"],
                    present_artifacts=["world_delta_transaction"],
                    refs={"world_delta_transaction": ref},
                    validation_results=[
                        _validation_result("world_delta_transaction", errors, ref)
                    ],
                    next_action="继续作为首战事务语义样例；不得把事务字段塞回 WorldStateDelta 顶层。",
                )
            )
    chain_failed = any(result["status"] == "failed" for result in chain_results)
    targets.append(
        _target(
            target_id="stage01_stage07.world_delta_transaction_chain",
            target_kind="world_delta_transaction_chain",
            source_path=WORLD_DELTA_TRANSACTION_DIR,
            alignment_state="validation_failed" if chain_failed else "native_snapshot_ready",
            expected_artifacts=["world_delta_transaction"],
            present_artifacts=["world_delta_transaction"],
            refs=chain_refs,
            validation_results=chain_results,
            next_action="后续剧情 / 世界演化包应继续引用事务链，而不是写通用 effects[]。",
        )
    )
    return targets


def _review_pack_alignment_state(path: Path, payload: dict[str, Any]) -> tuple[str, str]:
    explicit = as_obj(payload.get("core_artifact_alignment"))
    if explicit.get("alignment_state") == "review_only_not_applicable":
        return (
            "review_only_not_applicable",
            str(
                explicit.get("next_action")
                or "该 review pack 已声明为专项 evidence，不应强行迁移成核心对象。"
            ),
        )
    schema_version = str(payload.get("schema_version") or path.stem)
    lowered = f"{schema_version} {path.name}".lower()
    if any(keyword in lowered for keyword in MIGRATION_CANDIDATE_SCHEMA_KEYWORDS):
        return (
            "missing_core_alignment",
            "补充 core_artifact_refs 或原生 core_artifacts 快照，并通过统一 validator。",
        )
    return (
        "review_only_not_applicable",
        "保持为专项 review-only 证据；若未来要进入 runtime/world，先经对应 builder 生成核心对象或事务。",
    )


def _review_pack_targets() -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    standalone_core_paths = {CONTEXT_PACKAGE, FACT_ENTRY, CGOP, OUTPUT_PATH}
    for path in sorted((ROOT / "examples/review_packs").glob("*.json")):
        if path in standalone_core_paths:
            continue
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        refs = {
            key: str(value)
            for key, value in as_obj(payload.get("core_artifact_refs")).items()
            if key in CORE_KEYS and isinstance(value, str)
        }
        core_artifacts = as_obj(payload.get("core_artifacts"))
        embedded_present = [key for key in CORE_KEYS if key in core_artifacts]
        present = sorted(set(refs) | set(embedded_present))
        validation_results = _validate_embedded_core(
            core_artifacts,
            refs,
            [key for key in EMBEDDED_CORE_KEYS if key in embedded_present],
        )
        if "world_delta_transaction" in embedded_present:
            validation_results.append(
                _validation_result(
                    "world_delta_transaction",
                    validate_transaction(as_obj(core_artifacts.get("world_delta_transaction"))),
                    refs.get("world_delta_transaction"),
                )
            )
        if embedded_present:
            state = (
                "native_snapshot_ready"
                if all(item["status"] == "passed" for item in validation_results)
                else "validation_failed"
            )
            next_action = "保留原生核心对象快照；后续迁移可逐步减少兼容 refs-only 字段。"
        elif refs:
            state = "refs_only"
            next_action = "优先补原生核心对象摘要或统一 validation report，避免只靠路径引用解释语义。"
        else:
            state, next_action = _review_pack_alignment_state(path, payload)
        expected = present if present else []
        targets.append(
            _target(
                target_id=f"review_pack.{path.stem}",
                target_kind="review_pack",
                source_path=path,
                alignment_state=state,
                expected_artifacts=expected,
                present_artifacts=present,
                refs=refs,
                validation_results=validation_results,
                next_action=next_action,
            )
        )
    return targets


def _provider_targets() -> list[dict[str, Any]]:
    return [
        _target(
            target_id="provider_artifact_staging_manifest",
            target_kind="provider_artifact_stage",
            source_path=PROVIDER_STAGING,
            alignment_state="review_only_not_applicable",
            expected_artifacts=[],
            present_artifacts=[],
            refs={},
            validation_results=[],
            next_action=(
                "保持为 review-only staging；通过 promotion report 后仍需独立 runtime package / WorldStateDeltaTransaction builder。"
            ),
        ),
        _target(
            target_id="provider_artifact_promotion_report",
            target_kind="provider_artifact_promotion",
            source_path=PROVIDER_PROMOTION,
            alignment_state="review_only_not_applicable",
            expected_artifacts=[],
            present_artifacts=[],
            refs={},
            validation_results=[],
            next_action=(
                "当前报告只表达阻断/晋升许可，不直接携带可运行核心对象；批准后也只能作为后续 builder 输入。"
            ),
        ),
    ]


def _migration_tasks(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for target in targets:
        state = target.get("alignment_state")
        if state not in {"missing_core_alignment", "refs_only", "validation_failed"}:
            continue
        target_id = str(target.get("target_id"))
        if state == "validation_failed":
            objective = "修复现有原生核心对象或事务的 validator 失败，再允许它作为迁移锚点。"
            blocked_until = "相关 validator 返回 passed。"
        elif state == "refs_only":
            objective = "把 refs-only 迁移为原生核心对象摘要或统一 validation report。"
            blocked_until = "确认该产物确实需要被 runtime / world 编译链路消费。"
        else:
            objective = "为该 review pack 补 core_artifact_refs、原生 core_artifacts 快照或明确 not-applicable 边界。"
            blocked_until = "决定该产物是否会进入后续 runtime package / WorldStateDeltaTransaction 构建。"
        tasks.append(
            {
                "task_id": f"core_alignment::{target_id}",
                "priority": "P1" if state != "validation_failed" else "P1",
                "source_target_id": target_id,
                "objective": objective,
                "blocked_until": blocked_until,
            }
        )
    return tasks


def build_report() -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    targets.append(_frontend_mock_pack_target())
    targets.extend(_standalone_core_targets())
    targets.extend(_world_transaction_targets())
    targets.extend(_provider_targets())
    targets.extend(_review_pack_targets())
    status_counts = Counter(str(target.get("alignment_state")) for target in targets)
    validation_failed_count = status_counts.get("validation_failed", 0)
    missing_count = status_counts.get("missing_core_alignment", 0)
    refs_only_count = status_counts.get("refs_only", 0)
    overall_status = (
        "failed"
        if validation_failed_count
        else "needs_migration"
        if missing_count or refs_only_count
        else "passed"
    )
    return {
        "schema_version": "core_artifact_alignment_report.v0.1",
        "report_id": "core_artifact_alignment_report_mvp_2026_07_02",
        "created_at": "2026-07-02T00:00:00Z",
        "authority": {
            "visibility": "internal_evidence",
            "report_only": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "summary": {
            "overall_status": overall_status,
            "target_count": len(targets),
            "status_counts": dict(sorted(status_counts.items())),
            "native_snapshot_ready_count": status_counts.get("native_snapshot_ready", 0),
            "refs_only_count": refs_only_count,
            "missing_core_alignment_count": missing_count,
            "validation_failed_count": validation_failed_count,
            "review_only_not_applicable_count": status_counts.get(
                "review_only_not_applicable", 0
            ),
        },
        "target_reports": targets,
        "migration_tasks": _migration_tasks(targets),
        "safety_summary": {
            "reads_env": False,
            "calls_external_service": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "runtime_mutation_count": 0,
            "world_mutation_count": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build CoreArtifactAlignmentReport v0.1."
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help="Output path for the report JSON.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the generated report after writing it.",
    )
    args = parser.parse_args()

    output = Path(args.output)
    report = build_report()
    write_json(output, report)
    print(f"Wrote CoreArtifactAlignmentReport: {output}")
    if args.validate:
        from validate_core_artifact_alignment_report import validate_report

        errors = validate_report(report, source_path=output)
        if errors:
            print("INVALID CoreArtifactAlignmentReport")
            for error in errors:
                print(f"- {error}")
            return 1
        print(f"CoreArtifactAlignmentReport validation passed: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
