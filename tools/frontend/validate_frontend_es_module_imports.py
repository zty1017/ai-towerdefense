#!/usr/bin/env python3
"""Validate named ES module imports used by the frontend runtime.

`node --check` catches syntax errors but does not verify that a named import is
actually exported by the target module. This validator keeps the lightweight
offline quality gate honest while the frontend is being split into runtime
modules.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = ROOT / "frontend"
ENTRY_FILES = [FRONTEND_ROOT / "app.js", *sorted((FRONTEND_ROOT / "runtime").glob("*.js"))]


IMPORT_RE = re.compile(
    r"import\s*\{(?P<names>.*?)\}\s*from\s*[\"'](?P<module>[^\"']+)[\"']",
    re.S,
)
EXPORT_FUNCTION_RE = re.compile(
    r"(?m)^\s*export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)
EXPORT_LIST_RE = re.compile(r"export\s*\{(?P<names>.*?)\}", re.S)


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_import_names(block: str) -> list[str]:
    names: list[str] = []
    for raw in block.split(","):
        item = raw.strip()
        if not item:
            continue
        exported = item.split(" as ", 1)[0].strip()
        if exported:
            names.append(exported)
    return names


def parse_export_names(source: str) -> set[str]:
    names = {match.group("name") for match in EXPORT_FUNCTION_RE.finditer(source)}
    for match in EXPORT_LIST_RE.finditer(source):
        for raw in match.group("names").split(","):
            item = raw.strip()
            if not item:
                continue
            exported = item.split(" as ", 1)[-1].strip()
            if exported:
                names.add(exported)
    return names


def resolve_module(importer: Path, module_path: str) -> Path | None:
    if not module_path.startswith("."):
        return None
    path = (importer.parent / module_path).resolve()
    if path.suffix:
        return path
    return path.with_suffix(".js")


def validate() -> list[str]:
    failures: list[str] = []
    export_cache: dict[Path, set[str]] = {}
    for importer in ENTRY_FILES:
        if not importer.exists():
            continue
        source = importer.read_text(encoding="utf-8")
        for match in IMPORT_RE.finditer(source):
            target = resolve_module(importer, match.group("module"))
            if target is None:
                continue
            if not target.exists():
                failures.append(f"{rel(importer)} imports missing module {match.group('module')}")
                continue
            if target not in export_cache:
                export_cache[target] = parse_export_names(target.read_text(encoding="utf-8"))
            exported = export_cache[target]
            for name in parse_import_names(match.group("names")):
                if name not in exported:
                    failures.append(
                        f"{rel(importer)} imports {name!r} from {rel(target)}, but it is not exported"
                    )
    return failures


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description=__doc__).parse_args()


def main() -> int:
    parse_args()
    failures = validate()
    if failures:
        print("INVALID frontend ES module imports")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("OK frontend ES module imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
