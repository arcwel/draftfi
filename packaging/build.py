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
    # keyring discovers OS backends via entry points — bundle its submodules AND
    # metadata so the keychain works in the frozen app (else it falls back to
    # plaintext). G1.
    if _module_available("keyring"):
        args += [
            "--collect-submodules",
            "keyring",
            "--copy-metadata",
            "keyring",
        ]
    icon = _icon_path()
    if icon:
        args += ["--icon", str(icon)]

    try:
        run(args, cwd=BACKEND)
    finally:
        shutil.rmtree(staged, ignore_errors=True)

    if sys.platform == "darwin":
        _codesign(dist_dir / f"{APP_NAME}.app")

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


# macOS grants keychain access per *code signature*. PyInstaller ad-hoc signs,
# and an ad-hoc hash changes with the binary, so every rebuild looked like a
# brand-new application and re-prompted for the stored API key. Signing with a
# stable identity fixes that permanently. DRAFTFI_SIGN_IDENTITY names the
# identity (see packaging/make_signing_identity.sh); unset, we fall back to
# ad-hoc and warn.
SIGN_IDENTITY_ENV = "DRAFTFI_SIGN_IDENTITY"
DEFAULT_SIGN_IDENTITY = "DraftFi Local Signing"


def _codesign(app_path: Path) -> None:
    if sys.platform != "darwin" or not app_path.exists():
        return
    identity = os.environ.get(SIGN_IDENTITY_ENV, DEFAULT_SIGN_IDENTITY)
    listing = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        capture_output=True, text=True, check=False,
    ).stdout
    line = next((ln for ln in listing.splitlines() if identity in ln), None)
    if line is None:
        print(
            f"[warn] signing identity {identity!r} not found — leaving the "
            "ad-hoc signature in place.\n"
            "       macOS will re-prompt for keychain access after every "
            "rebuild until you create one:\n"
            "         bash packaging/make_signing_identity.sh"
        )
        return
    if "CSSMERR" in line:
        # find-identity counts an untrusted certificate as "valid" but tags it.
        # codesign then blocks on a GUI prompt instead of failing, which hangs
        # the build — so screen for the tag rather than the name alone.
        print(
            f"[warn] signing identity {identity!r} is not trusted "
            f"({line.strip().split('(')[-1].rstrip(')')}), so codesign cannot "
            "use it. Keeping the ad-hoc signature.\n"
            "       Finish the one-time trust step (no password needed):\n"
            "         bash packaging/make_signing_identity.sh"
        )
        return
    # The build tree lives in a Google Drive folder, and both Drive and `ditto`
    # attach extended attributes (com.apple.FinderInfo, quarantine flags) to the
    # files inside the bundle. codesign will happily sign over them, but the
    # signature then fails strict verification with "resource fork, Finder
    # information, or similar detritus not allowed" — which macOS treats as an
    # invalid signature, undoing the whole point of signing. Clear them first.
    subprocess.run(
        ["xattr", "-cr", str(app_path)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    try:
        result = subprocess.run(
            [
                "codesign", "--force", "--deep", "--timestamp=none",
                "--sign", identity, str(app_path),
            ],
            capture_output=True, text=True, check=False,
            # Signing is fast; anything slower means a keychain dialog is waiting
            # for a human. A build must never block on that.
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print(
            "[warn] codesign timed out — it is almost certainly waiting on a "
            "keychain prompt for the signing key. Keeping the ad-hoc signature."
        )
        return
    if result.returncode != 0:
        print(f"[warn] codesign failed, keeping ad-hoc signature:\n{result.stderr}")
        return
    # Signing "succeeding" is not the same as the signature being valid, and a
    # silently invalid one looks identical to ad-hoc from the keychain's point of
    # view. Say which of the two actually happened.
    check = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app_path)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if check.returncode != 0:
        print(
            "[warn] signed, but the signature does not verify:\n"
            f"{check.stderr.strip()}\n"
            "       macOS will treat this build as unsigned and keep asking for "
            "keychain access."
        )
        return
    print(f"[OK] Signed with {identity!r} — keychain access will persist.")


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
