#!/usr/bin/env python3
"""Fail when source files exceed the Wave 3 large-file budget."""

from __future__ import annotations

import argparse
from pathlib import Path


MAX_LINES = 799
REPO_ROOT = Path(__file__).resolve().parents[1]

BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"

BACKEND_SUFFIXES = {".py"}
FRONTEND_SUFFIXES = {".ts", ".tsx"}

EXCLUDED_PARTS = {
    ".next",
    ".venv",
    "__pycache__",
    "coverage",
    "node_modules",
    "playwright-report",
    "test-results",
    "tests",
    "__tests__",
}


def is_source_file(path: Path, *, root: Path, suffixes: set[str]) -> bool:
    if path.suffix not in suffixes:
        return False
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return not any(part in EXCLUDED_PARTS for part in relative.parts)


def count_lines(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def scan(root: Path, suffixes: set[str]) -> list[tuple[int, Path]]:
    violations: list[tuple[int, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file() or not is_source_file(path, root=root, suffixes=suffixes):
            continue
        line_count = count_lines(path)
        if line_count > MAX_LINES:
            violations.append((line_count, path))
    return sorted(violations, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", action="store_true", help="Check backend Python files.")
    parser.add_argument("--frontend", action="store_true", help="Check frontend TS/TSX files.")
    args = parser.parse_args()

    check_backend = args.backend or not args.frontend
    check_frontend = args.frontend or not args.backend

    violations: list[tuple[int, Path]] = []
    if check_backend:
        violations.extend(scan(BACKEND_ROOT, BACKEND_SUFFIXES))
    if check_frontend:
        violations.extend(scan(FRONTEND_ROOT, FRONTEND_SUFFIXES))

    if violations:
        print(f"Files over {MAX_LINES} lines:")
        for line_count, path in sorted(violations, reverse=True):
            print(f"{line_count:5d} {path.relative_to(REPO_ROOT)}")
        return 1

    print(f"Large-file check passed: no source file over {MAX_LINES} lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
