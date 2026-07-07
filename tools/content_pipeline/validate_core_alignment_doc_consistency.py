#!/usr/bin/env python3
"""Validate core artifact alignment report status and stale documentation phrases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.content_pipeline.validate_core_artifact_alignment_report import (  # noqa: E402
    as_list,
    as_obj,
    validate_report,
)


DEFAULT_REPORT = ROOT / "examples/review_packs/core_artifact_alignment_report.v0.1.json"
DEFAULT_DOCS = [
    ROOT / "control/TASK_QUEUE.md",
    ROOT / "docs/CURRENT_ARCHITECTURE_INDEX.md",
    ROOT / "docs/AI_COMPILATION_SYSTEM_V0_1.md",
]
FORBIDDEN_PHRASES = [
    "当前报告状态为 `needs_migration`",
    "CoreArtifactAlignmentReport 已列出当前待迁移 review pack",
    "下一步继续把 review pack 与真实 provider 产物对齐到这些核心字段",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def repo_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def validate_consistency(report_path: Path, doc_paths: list[Path]) -> dict[str, Any]:
    report = load_json(report_path)
    errors = validate_report(report, source_path=report_path)
    if errors:
        raise ValueError("core artifact alignment report invalid: " + "; ".join(errors))
    summary = as_obj(report.get("summary"))
    if summary.get("overall_status") != "passed":
        raise ValueError("summary.overall_status must be passed")
    if summary.get("missing_core_alignment_count") != 0:
        raise ValueError("summary.missing_core_alignment_count must be 0")
    if as_list(report.get("migration_tasks")):
        raise ValueError("migration_tasks must be empty")

    stale_hits: list[str] = []
    for doc_path in doc_paths:
        path = repo_path(doc_path)
        text = path.read_text(encoding="utf-8")
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                stale_hits.append(f"{path.relative_to(ROOT)} contains stale phrase: {phrase}")
    if stale_hits:
        raise ValueError("; ".join(stale_hits))
    return {
        "report": str(report_path),
        "overall_status": summary.get("overall_status"),
        "checked_doc_count": len(doc_paths),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--doc", type=Path, action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    docs = args.doc or DEFAULT_DOCS
    try:
        summary = validate_consistency(repo_path(args.report), docs)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"core alignment doc consistency validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "core alignment doc consistency validation passed: "
        + json.dumps(summary, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
