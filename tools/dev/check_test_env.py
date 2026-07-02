#!/usr/bin/env python3
"""Check whether the local environment can run the full test suite."""

from __future__ import annotations

import importlib.util
import shutil
import sys


REQUIRED_PYTHON_MODULES = {
    "fastapi": "FastAPI backend and TestClient app creation",
    "pydantic": "request / response models",
    "pytest": "backend test runner",
    "httpx": "FastAPI TestClient transport dependency",
    "uvicorn": "local development server",
}


def main() -> int:
    print("Python:", sys.version.split()[0])
    missing: list[str] = []
    for module, reason in REQUIRED_PYTHON_MODULES.items():
        found = importlib.util.find_spec(module) is not None
        mark = "OK" if found else "MISSING"
        print(f"{mark:7} {module:<10} {reason}")
        if not found:
            missing.append(module)

    node = shutil.which("node")
    print(f"{'OK' if node else 'MISSING':7} node       frontend syntax check")
    if not node:
        missing.append("node")

    if missing:
        print()
        print("Missing dependency group:", ", ".join(missing))
        print("Install Python dependencies with:")
        print("  python3 -m pip install -r requirements.txt")
        print("Then rerun:")
        print("  python3 -m pytest backend/tests")
        return 1

    print()
    print("Environment can run the full local verification suite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
