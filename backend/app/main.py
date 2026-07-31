"""DraftFi FastAPI application entry point."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import (
    budget,
    data,
    export,
    goals,
    imports,
    insights,
    llm_status,
    logs,
    merchants,
    scenario,
    simulation,
    transactions,
)
from app.api import (
    settings as settings_api,
)
from app.config import get_settings
from app.db.connection import init_db, session
from app.models.schemas import UpdateInfo
from app.services import logging_setup, security, updates


def _frontend_dir() -> Path | None:
    """Locate the built React frontend (``dist``), if it was bundled.

    Handles three cases: a PyInstaller-frozen app (``sys._MEIPASS``), a local
    copy placed next to the backend, and the repo layout (``../frontend/dist``).
    Returns None in plain dev, where Vite serves the frontend instead.
    """
    candidates = []
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        candidates.append(Path(getattr(sys, "_MEIPASS", ".")) / "frontend_dist")
    here = Path(__file__).resolve().parent
    candidates.append(here / "frontend_dist")  # copied in during packaging
    candidates.append(here.parent.parent / "frontend" / "dist")  # repo layout
    for c in candidates:
        if c.is_dir() and (c / "index.html").exists():
            return c
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the log file before anything else so boot failures are captured.
    logging_setup.setup_logging()
    # Create/upgrade the local SQLite database and seed defaults on boot.
    init_db()
    # Start locked when a passcode is configured (G2).
    with session() as conn:
        security.refresh_lock_state(conn)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DraftFi API",
        description="Local-first financial simulation engine (BYO-LLM).",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Loopback binding is not, by itself, a security boundary. Any web page the
    # user has open can issue requests to 127.0.0.1, and Starlette's
    # CORSMiddleware does not block them — it only omits a response header, so
    # a "simple" request (a form POST, a multipart upload) still reaches the
    # handler and still runs. Verified before this existed: a cross-origin
    # POST /reset deleted every transaction and returned 200, and a request
    # carrying a spoofed Host header served the entire transaction history from
    # /export/data.json after a DNS rebind.
    #
    # Two cheap checks close both. Neither costs anything at runtime, and
    # neither can be satisfied by an attacker who only controls a web page.
    _LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
    _SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

    def _hostname(value: str) -> str:
        host = (value or "").strip().lower()
        if host.startswith("["):  # bracketed IPv6
            return host.split("]")[0] + "]"
        return host.split(":")[0]

    @app.middleware("http")
    async def _origin_gate(request, call_next):
        # Host: defeats DNS rebinding. After a rebind the browser considers the
        # attacker's domain same-origin, so CORS stops helping — but the Host
        # header still carries that domain, and ours is always loopback.
        if _hostname(request.headers.get("host", "")) not in _LOOPBACK_HOSTS:
            return JSONResponse(
                {"detail": "Invalid Host header."}, status_code=421
            )
        # Origin: defeats CSRF. Only checked for state-changing methods, and
        # only when present — the app's own fetches from a file/app origin may
        # legitimately send none.
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and _hostname(urlparse(origin).netloc) not in _LOOPBACK_HOSTS:
                return JSONResponse(
                    {"detail": "Cross-origin requests are not allowed."},
                    status_code=403,
                )
        return await call_next(request)

    @app.middleware("http")
    async def _passcode_gate(request, call_next):
        """G2: while locked, refuse data routes with 423 (the SPA + lock-screen
        endpoints stay reachable so the user can enter their passcode)."""
        if security.is_locked() and not security.path_allowed_when_locked(
            request.url.path
        ):
            return JSONResponse(
                {"detail": "DraftFi is locked."}, status_code=423
            )
        return await call_next(request)

    app.include_router(imports.router)
    app.include_router(transactions.router)
    app.include_router(llm_status.router)
    app.include_router(simulation.router)
    app.include_router(budget.router)
    app.include_router(goals.router)
    app.include_router(insights.router)
    app.include_router(settings_api.router)
    app.include_router(data.router)
    app.include_router(scenario.router)
    app.include_router(export.router)
    app.include_router(logs.router)
    app.include_router(merchants.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/update-check", response_model=UpdateInfo, tags=["meta"])
    async def update_check() -> UpdateInfo:
        """F1: is a newer desktop release available on GitHub?"""
        return UpdateInfo(**await updates.check_for_update())

    # In the packaged desktop app, this same process serves the built React
    # frontend so everything runs from one local origin (no Vite, no proxy).
    dist = _frontend_dir()
    if dist is not None:
        app.mount(
            "/assets", StaticFiles(directory=dist / "assets"), name="assets"
        )

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon() -> FileResponse:
            icon = dist / "favicon.ico"
            target = icon if icon.exists() else dist / "index.html"
            return FileResponse(target)

    return app


app = create_app()
