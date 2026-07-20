"""DraftFi FastAPI application entry point."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

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
from app.services import security, updates


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
