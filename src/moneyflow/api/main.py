"""FastAPI app. Versioned API (/api/v1) + serves the React build.

Product-matrix ready: the frontend is a fully decoupled static app;
any future product can consume /api/v1 independently.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from moneyflow.api.routers import health

app = FastAPI(title="US Money Flow Tracker", version="0.1.0")
app.include_router(health.router, prefix="/api/v1")

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
if WEB_DIST.exists():  # React build output; absent until `npm run build`
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
