# DraftFi Desktop App

DraftFi ships as a **self-contained desktop app** for macOS and Windows. Users
download one file and double-click it — no Python, no Node, no terminal, no
setup. Everything (the Python runtime, all dependencies, and the web UI) is
bundled inside the app.

## For end users

1. Download the app for your OS from the project's
   [Releases](https://github.com/) page:
   - **macOS:** `DraftFi-macos.zip` → unzip → drag `DraftFi.app` to Applications → open it.
   - **Windows:** `DraftFi-windows.zip` → unzip → run `DraftFi.exe`.
2. DraftFi opens in its own window like any other application.
3. Your data lives locally and privately in:
   - **macOS:** `~/Library/Application Support/DraftFi/sandbox.db`
   - **Windows:** `%APPDATA%\DraftFi\sandbox.db`

Every launch just reopens the app with your saved data. Nothing is uploaded
anywhere.

> **First-launch security prompts.** Because the app isn't code-signed with a
> paid developer certificate, macOS Gatekeeper may say it's from an
> unidentified developer (right-click → Open the first time), and Windows
> SmartScreen may show "More info → Run anyway". Code-signing certificates
> ($99/yr Apple, ~$200–400/yr Windows) remove these prompts and are the last
> step before a fully commercial release.

## How it works

The packaged app runs the same FastAPI backend used in development, but:

- FastAPI **also serves the built React UI**, so the whole app is one local
  process on one loopback port (never exposed to the network).
- A **native window** (via `pywebview` — WebKit on macOS, WebView2 on Windows)
  points at that local server. If no webview backend is available it falls back
  to the default browser.
- The SQLite database is stored in the per-user app-data directory.

## Building it yourself

Requires the target OS (PyInstaller can't cross-compile — build macOS on a Mac,
Windows on Windows).

```bash
# 1. Backend deps + packaging deps
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r ../packaging/requirements-desktop.txt

# 2. Build (compiles the frontend, then freezes everything)
cd ..
python packaging/build.py
```

Output lands in `dist_desktop/`:
- macOS → `dist_desktop/DraftFi.app`
- Windows → `dist_desktop/DraftFi/DraftFi.exe`

Flags: `--skip-frontend` (reuse an existing `frontend/dist`), `--dist DIR`
(change the output location).

## Automated builds

`.github/workflows/release.yml` builds both apps on GitHub's macOS and Windows
runners. Push a version tag to produce downloadable release assets:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

The workflow can also be run manually from the **Actions** tab (artifacts are
attached to the run even without a tag).

## Running without packaging (headless)

The launcher supports a headless mode that starts the local server without
opening a window — handy for testing a frozen build or running it like a
service:

```bash
DRAFTFI_HEADLESS=1 ./DraftFi.app/Contents/MacOS/DraftFi   # macOS
```
