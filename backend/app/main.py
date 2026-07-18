"""DraftFi FastAPI application entry point."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import budget, imports, llm_status, simulation, transactions
from app.config import get_settings
from app.db.connection import init_db


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

    app.include_router(imports.router)
    app.include_router(transactions.router)
    app.include_router(llm_status.router)
    app.include_router(simulation.router)
    app.include_router(budget.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

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
