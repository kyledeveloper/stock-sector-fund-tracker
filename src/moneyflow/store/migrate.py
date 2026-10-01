"""Versioned SQL migrations. Explicit files, tiny runner, fully auditable.

Convention: store/migrations/NNN_name.sql applied in order, tracked in
_schema_version. No ORM autogenerate -- every schema change is a reviewed file.
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def apply_migrations(engine) -> int:
    """Apply pending migrations. Returns number applied."""
    applied = 0
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY)"
        )
        cur = conn.exec_driver_sql("SELECT MAX(version) FROM _schema_version").scalar()
        current = cur or 0
        files = sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
        for f in files:
            version = int(f.stem.split("_")[0])
            if version > current:
                conn.exec_driver_sql(f.read_text())
                conn.exec_driver_sql("INSERT INTO _schema_version (version) VALUES (?)", (version,))
                applied += 1
    return applied
