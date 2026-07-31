#!/usr/bin/env python3
"""Install the built app into ~/Applications, signed and verified.

Why this is a separate step from ``build.py``
---------------------------------------------
``dist_desktop`` lives inside a Google Drive folder, and Drive stamps extended
attributes (``com.apple.FinderInfo``, quarantine flags) onto files as it syncs
them. codesign happily signs over that, but the resulting signature fails
strict verification with:

    resource fork, Finder information, or similar detritus not allowed

macOS treats an unverifiable signature as no signature — which silently undoes
the entire point of having a stable signing identity, and brings back the
"approve keychain access again" prompt on every rebuild. Stripping the
attributes before signing does not help for long, because Drive puts them back
whenever it touches the bundle.

So the bundle that actually gets signed is the *installed* copy in
``~/Applications``, which Drive never touches. That is also the copy the
keychain grant is attached to, so it is the one that has to be right.

Usage:  backend/.venv/bin/python packaging/install.py [--launch]
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "DraftFi"
SIGN_IDENTITY_ENV = "DRAFTFI_SIGN_IDENTITY"
DEFAULT_SIGN_IDENTITY = "DraftFi Local Signing"

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "dist_desktop" / f"{APP_NAME}.app"
DEST = Path.home() / "Applications" / f"{APP_NAME}.app"
BACKUP = DEST.with_suffix(".app.old")


def run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, check=False, timeout=timeout
    )


def quit_running_app() -> None:
    """Ask the app to quit, by name.

    Deliberately *not* ``pkill -f``: that pattern matches any process whose
    command line mentions the bundle, which includes the copy the user is
    sitting in front of. Killing that out from under them looks exactly like
    the app losing all its data.
    """
    result = run(["osascript", "-e", f'quit app "{APP_NAME}"'], timeout=30)
    if result.returncode == 0:
        print(f"[..] Asked {APP_NAME} to quit")


def copy_clean() -> None:
    """Copy the bundle without carrying Drive's extended attributes across."""
    if BACKUP.exists():
        shutil.rmtree(BACKUP)
    if DEST.exists():
        DEST.rename(BACKUP)
        print(f"[..] Previous build kept at {BACKUP}")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    # --noextattr/--norsrc/--noqtn are the whole reason for using ditto here
    # rather than shutil.copytree: they drop the metadata that breaks signing.
    result = run(
        ["ditto", "--noextattr", "--norsrc", "--noqtn", str(SOURCE), str(DEST)]
    )
    if result.returncode != 0:
        raise SystemExit(f"[fail] copy failed:\n{result.stderr}")
    print(f"[OK] Installed to {DEST}")


def sign_and_verify() -> bool:
    identity = os.environ.get(SIGN_IDENTITY_ENV, DEFAULT_SIGN_IDENTITY)
    listing = run(["security", "find-identity", "-v", "-p", "codesigning"]).stdout
    line = next((ln for ln in listing.splitlines() if identity in ln), None)
    if line is None or "CSSMERR" in line:
        print(
            f"[warn] signing identity {identity!r} is missing or untrusted, so "
            "the app stays ad-hoc signed and macOS will keep asking for "
            "keychain access after every rebuild.\n"
            "       Fix with (no password needed):\n"
            "         bash packaging/make_signing_identity.sh"
        )
        return False

    # Belt and braces: ditto should already have dropped the attributes, but a
    # single leftover xattr anywhere in the bundle invalidates the signature.
    run(["xattr", "-cr", str(DEST)])
    result = run(
        [
            "codesign", "--force", "--deep", "--timestamp=none",
            "--sign", identity, str(DEST),
        ]
    )
    if result.returncode != 0:
        print(f"[warn] codesign failed:\n{result.stderr}")
        return False

    check = run(["codesign", "--verify", "--deep", "--strict", str(DEST)])
    if check.returncode != 0:
        print(
            "[warn] signed, but the signature does not verify:\n"
            f"{check.stderr.strip()}"
        )
        return False

    # The designated requirement is what a keychain grant is recorded against.
    # Printing it makes the guarantee checkable rather than a claim: it names
    # the certificate, not this build's hash, so it is identical next rebuild.
    # codesign splits this output: "Executable=..." goes to stderr while the
    # requirement itself goes to stdout. Read both rather than guessing.
    proc = run(["codesign", "-d", "-r-", str(DEST)])
    req = f"{proc.stdout}\n{proc.stderr}"
    designated = next(
        (ln.strip() for ln in req.splitlines() if ln.startswith("designated")), ""
    )
    print(f"[OK] Signed with {identity!r} and verified")
    if designated:
        print(f"     {designated}")
        print("     Unchanged across rebuilds, so the keychain grant sticks.")
    return True


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(
            f"[fail] {SOURCE} not found — run packaging/build.py first."
        )
    quit_running_app()
    copy_clean()
    ok = sign_and_verify()
    if "--launch" in sys.argv:
        run(["open", "-a", str(DEST)], timeout=30)
        print(f"[..] Launched {APP_NAME}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
