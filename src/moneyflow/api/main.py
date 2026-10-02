"""FastAPI app. Versioned API (/api/v1) + serves the React build.

Product-matrix ready: the frontend is a fully decoupled static app;
any future product can consume /api/v1 independently.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from moneyflow.api.routers import exposure, filings, freshness, health, momentum, sentiment
from moneyflow.services.startup import ensure_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Self-heal schema on a fresh checkout/DB; idempotent, pipeline does it too.
    ensure_schema()
    yield


app = FastAPI(title="US Money Flow Tracker", version="0.1.0", lifespan=lifespan)
app.include_router(health.router, prefix="/api/v1")
app.include_router(freshness.router, prefix="/api/v1")
app.include_router(exposure.router, prefix="/api/v1")
app.include_router(momentum.router, prefix="/api/v1")
app.include_router(filings.router, prefix="/api/v1")
app.include_router(sentiment.router, prefix="/api/v1")

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
if WEB_DIST.exists():  # React build output; absent until `npm run build`
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
