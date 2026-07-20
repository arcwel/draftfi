#!/usr/bin/env python3
"""Cross-platform build script for the DraftFi desktop app.

Produces a self-contained application (macOS ``.app`` / Windows ``.exe`` /
Linux onedir bundle) that packs the Python runtime, all backend dependencies,
and the built React frontend. End users install nothing — they download and
double-click (Linux: extract the tarball and run ``DraftFi/DraftFi``).

Usage:
    python packaging/build.py [--skip-frontend] [--dist DIR]

Run it from a machine matching the target OS (PyInstaller does not
cross-compile). CI does exactly this on macOS, Windows, and Linux runners.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
DIST_SRC = FRONTEND / "dist"
APP_NAME = "DraftFi"


def run(cmd: list[str], cwd: Path) -> None:
    print(f"\n$ {' '.join(cmd)}  (in {cwd})", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def build_frontend() -> None:
    npm = shutil.which("npm") or "npm"
    run([npm, "install"], cwd=FRONTEND)
    run([npm, "run", "build"], cwd=FRONTEND)
    if not (DIST_SRC / "index.html").exists():
        sys.exit("Frontend build did not produce dist/index.html")


def build_app(dist_dir: Path) -> None:
    # Stage the built frontend next to the backend so PyInstaller bundles it.
    staged = BACKEND / "frontend_dist"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(DIST_SRC, staged)

    sep = ";" if sys.platform == "win32" else ":"
    work_dir = dist_dir / "_work"
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "desktop.py",
        "--name",
        APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",  # no console window
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--add-data",
        f"{staged}{sep}frontend_dist",
        # FastAPI/uvicorn/pydantic need their dynamic bits collected explicitly.
        "--collect-submodules",
        "uvicorn",
        "--hidden-import",
        "app.main",
    ]
    # Bundle the native-window backend only if it's installed (else the app
    # falls back to the default browser).
    if _module_available("webview"):
        args += ["--collect-submodules", "webview"]
    # Tray backend (Windows/Linux); PyInstaller needs its platform submodules.
    if _module_available("pystray"):
        args += ["--collect-submodules", "pystray"]
    icon = _icon_path()
    if icon:
        args += ["--icon", str(icon)]

    try:
        run(args, cwd=BACKEND)
    finally:
        shutil.rmtree(staged, ignore_errors=True)

    print(f"\n[OK] Built {APP_NAME} into {dist_dir}", flush=True)
    if sys.platform == "darwin":
        print(f"  -> {dist_dir / (APP_NAME + '.app')}")
    elif sys.platform == "win32":
        print(f"  -> {dist_dir / APP_NAME / (APP_NAME + '.exe')}")
    else:  # Linux (and other *nix): PyInstaller onedir bundle.
        print(f"  -> {dist_dir / APP_NAME / APP_NAME}")


def _icon_path() -> Path | None:
    icons = Path(__file__).resolve().parent / "icons"
    name = "DraftFi.icns" if sys.platform == "darwin" else "DraftFi.ico"
    p = icons / name
    return p if p.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the DraftFi desktop app")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--dist", default=str(ROOT / "dist_desktop"))
    args = parser.parse_args()

    if not args.skip_frontend:
        build_frontend()
    elif not (DIST_SRC / "index.html").exists():
        sys.exit("--skip-frontend given but frontend/dist is missing; build it first")

    dist_dir = Path(args.dist)
    dist_dir.mkdir(parents=True, exist_ok=True)
    build_app(dist_dir)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    # Windows consoles default to cp1252; force UTF-8 so any non-ASCII output
    # (paths, etc.) can't crash the build with a UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    main()
