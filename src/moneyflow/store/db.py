"""SQLite engine/session. WAL mode for concurrent read during writes."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def get_engine(db_path: Path | None = None):
    db_path = db_path or (DATA_DIR / "moneyflow.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    return engine


SessionLocal = sessionmaker(future=True)
