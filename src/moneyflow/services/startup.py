"""Startup helpers. Thin orchestration only -- no business logic.

ensure_schema(): the API server must be startable on a fresh checkout
without a prior pipeline run. Migrations are idempotent, and the daily
pipeline also applies them, so running them at API startup is safe.
Without this, a fresh DB means "no such table" 500s on every panel.
"""

from __future__ import annotations

from moneyflow.store.db import get_engine
from moneyflow.store.migrate import apply_migrations


def ensure_schema() -> int:
    """Apply pending migrations. Returns number applied (0 if up to date)."""
    return apply_migrations(get_engine())
