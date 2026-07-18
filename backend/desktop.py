"""DraftFi desktop launcher — the entry point for the packaged app.

Double-clicking the packaged application runs this. It:

1. Points the database at the per-user app-data directory (persists between
   launches, always writable).
2. Starts the FastAPI server (which also serves the built frontend) on a free
   local port, bound to loopback only.
3. Opens a native desktop window pointed at that server. If a native webview
   backend isn't available, it falls back to the default web browser.

No Python, Node, or terminal knowledge required — everything is bundled.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from contextlib import closing

# Point the DB at the per-user data dir BEFORE the app/config is imported.
from app.paths import default_db_path  # noqa: E402

os.environ.setdefault("DRAFTFI_DB_PATH", str(default_db_path()))

import uvicorn  # noqa: E402


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url: str, timeout: float = 20.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    return False


def _serve(port: int) -> None:
    # Import here so the DB env var is already set.
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    server = threading.Thread(target=_serve, args=(port,), daemon=True)
    server.start()

    if not _wait_until_up(f"{url}/health"):
        print("DraftFi failed to start its local server.", file=sys.stderr)
        sys.exit(1)

    # Headless/server mode: keep the server running, open nothing. Useful for
    # tests and for anyone who'd rather use their own browser.
    if os.environ.get("DRAFTFI_HEADLESS"):
        print(f"DraftFi running (headless) at {url}", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    # Prefer a native window; fall back to the browser if unavailable.
    try:
        import webview  # type: ignore

        webview.create_window(
            "DraftFi", url, width=1360, height=880, min_size=(900, 600)
        )
        webview.start()
    except Exception:
        import webbrowser

        webbrowser.open(url)
        print(f"DraftFi is running at {url} — close this window to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
