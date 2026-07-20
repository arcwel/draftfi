"""DraftFi desktop launcher — the entry point for the packaged app.

Double-clicking the packaged application runs this. It:

1. Enforces a single running instance (a second launch just refocuses the
   first window instead of starting a duplicate server).
2. Points the database at the per-user app-data directory (persists between
   launches, always writable).
3. Starts the FastAPI server (which also serves the built frontend) on a free
   local port, bound to loopback only.
4. Opens a native desktop window pointed at that server, plus a tray/menu-bar
   icon with a quick-quit. If a native webview backend isn't available, it
   falls back to the default web browser.

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

# A fixed loopback port used ONLY as a single-instance lock + focus channel.
_LOCK_PORT = 49312
# Set once the native window exists so the focus listener can raise it.
_window = None


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------- #
# Single-instance guard (F2)
# --------------------------------------------------------------------------- #
def _acquire_single_instance() -> socket.socket | None:
    """Bind the lock port. Returns the socket if we're first, else ``None``.

    We deliberately do NOT set SO_REUSEADDR so a second process's bind fails
    while the first instance holds the listening socket.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", _LOCK_PORT))
        sock.listen(5)
        return sock
    except OSError:
        sock.close()
        return None


def _signal_existing_instance() -> None:
    """Ask the running instance to bring its window to the front."""
    try:
        with socket.create_connection(("127.0.0.1", _LOCK_PORT), timeout=2.0) as c:
            c.sendall(b"focus")
    except OSError:
        pass


def _focus_listener(lock: socket.socket) -> None:
    """Raise the window whenever another launch pings the lock port."""
    while True:
        try:
            conn, _ = lock.accept()
        except OSError:
            return
        with conn:
            try:
                conn.recv(16)
            except OSError:
                pass
        if _window is not None:
            try:
                _window.restore()
                _window.show()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Tray / menu-bar icon (F2)
# --------------------------------------------------------------------------- #
def _start_tray() -> None:
    """Show a tray icon with a quick-quit. No-op where unsupported.

    Skipped on macOS: a status-bar item needs the main run loop, which pywebview
    already owns — the app instead relies on the native app/dock menu (Cmd-Q).
    """
    if sys.platform == "darwin":
        return
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        return  # tray deps not bundled — fall through silently

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 56, 56), fill=(56, 189, 248, 255))

    def _quit(icon, _item) -> None:
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        "DraftFi",
        image,
        "DraftFi",
        menu=pystray.Menu(pystray.MenuItem("Quit DraftFi", _quit)),
    )
    threading.Thread(target=icon.run, daemon=True).start()


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
    global _window

    headless = bool(os.environ.get("DRAFTFI_HEADLESS"))

    # Single-instance guard (skipped in headless mode, where several server
    # instances may legitimately run). A second GUI launch refocuses the first.
    lock = None
    if not headless:
        lock = _acquire_single_instance()
        if lock is None:
            _signal_existing_instance()
            return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    server = threading.Thread(target=_serve, args=(port,), daemon=True)
    server.start()

    if not _wait_until_up(f"{url}/health"):
        print("DraftFi failed to start its local server.", file=sys.stderr)
        sys.exit(1)

    # Headless/server mode: keep the server running, open nothing. Useful for
    # tests and for anyone who'd rather use their own browser.
    if headless:
        print(f"DraftFi running (headless) at {url}", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    if lock is not None:
        threading.Thread(target=_focus_listener, args=(lock,), daemon=True).start()
    _start_tray()

    # Prefer a native window; fall back to the browser if unavailable.
    try:
        import webview  # type: ignore

        _window = webview.create_window(
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
