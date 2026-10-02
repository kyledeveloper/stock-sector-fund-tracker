"""Regression: API startup must self-apply migrations.

Bug seen 2026-10-02: user started uvicorn directly on a fresh checkout;
no pipeline CLI had ever run, so no tables existed and EVERY panel failed
with "API 500" (sqlite3.OperationalError: no such table). The API must
ensure its own schema on startup -- migrations are idempotent and the
pipeline also applies them, so this is safe to do in both places.

Architecture: api/ may only depend on models/common/services, so the
schema-ensure lives in services.startup (thin wrapper over store.migrate).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import moneyflow.api.main as main_mod
import moneyflow.services.startup as startup_mod


def _tables(eng):
    with eng.connect() as conn:
        return {
            r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
        }


def test_startup_applies_migrations_to_fresh_db(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/fresh.db")
    monkeypatch.setattr(startup_mod, "get_engine", lambda: eng)
    assert "form4_transaction" not in _tables(eng)

    with TestClient(main_mod.app):
        pass

    tables = _tables(eng)
    assert "form4_transaction" in tables
    assert "cboe_putcall" in tables
    assert "_schema_version" in tables


def test_startup_is_idempotent_on_migrated_db(monkeypatch, tmp_path):
    from moneyflow.store.migrate import apply_migrations

    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    assert apply_migrations(eng) > 0  # first run applies
    monkeypatch.setattr(startup_mod, "get_engine", lambda: eng)

    with TestClient(main_mod.app):
        pass

    with eng.connect() as conn:
        versions = [
            r[0]
            for r in conn.exec_driver_sql("SELECT version FROM _schema_version ORDER BY version")
        ]
    assert versions == sorted(versions) and len(versions) == len(set(versions))
