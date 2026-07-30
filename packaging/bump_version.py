#!/usr/bin/env python3
"""Bump the app version. Patch by default.

The version is single-sourced in ``backend/app/__init__.py`` and surfaced in the
Settings header (read from /health), so the number on screen always identifies
the build that is actually running. Run this once per change set:

    python packaging/bump_version.py            # 2.0.1 -> 2.0.2
    python packaging/bump_version.py --minor    # 2.0.7 -> 2.1.0
    python packaging/bump_version.py --set 3.0.0
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INIT = Path(__file__).resolve().parent.parent / "backend" / "app" / "__init__.py"
PATTERN = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump the DraftFi version")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--minor", action="store_true", help="bump minor, reset patch")
    group.add_argument("--major", action="store_true", help="bump major, reset rest")
    group.add_argument("--set", dest="exact", help="set an exact X.Y.Z version")
    parser.add_argument(
        "--print", action="store_true", help="print the current version and exit"
    )
    args = parser.parse_args()

    source = INIT.read_text()
    match = PATTERN.search(source)
    if not match:
        sys.exit(f"Could not find __version__ in {INIT}")
    major, minor, patch = (int(g) for g in match.groups())
    current = f"{major}.{minor}.{patch}"

    if args.print:
        print(current)
        return

    if args.exact:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.exact):
            sys.exit("--set expects X.Y.Z")
        new = args.exact
    elif args.major:
        new = f"{major + 1}.0.0"
    elif args.minor:
        new = f"{major}.{minor + 1}.0"
    else:
        new = f"{major}.{minor}.{patch + 1}"

    INIT.write_text(PATTERN.sub(f'__version__ = "{new}"', source, count=1))
    print(f"{current} -> {new}")


if __name__ == "__main__":
    main()
