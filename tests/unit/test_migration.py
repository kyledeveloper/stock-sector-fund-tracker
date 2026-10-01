"""Migration runner regression tests (red-team B1).

The runner once passed a whole multi-statement .sql file to a
single-statement executor and blew up with ProgrammingError. These tests
pin the fix: real migration files apply cleanly, and reruns are no-ops.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect

from moneyflow.store.migrate import _split_statements, apply_migrations


def _memory_engine():
    return create_engine("sqlite://")


def test_splitter_respects_quotes_and_comments():
    sql = """
    CREATE TABLE t (a TEXT DEFAULT 'x;y', b TEXT); -- trailing; comment
    /* block; comment */
    INSERT INTO t VALUES ('it''s', "q;q");
    """
    stmts = _split_statements(sql)
    assert len(stmts) == 2
    assert stmts[0].lstrip().startswith("CREATE TABLE")
    assert "INSERT INTO" in stmts[1]
    assert "'x;y'" in stmts[0]  # quoted semicolons survived intact


def test_apply_real_migrations_twice_is_idempotent():
    engine = _memory_engine()
    first = apply_migrations(engine)
    assert first == 3  # 001_init.sql + 002_sector_momentum.sql + 003_drop_m1.sql

    tables = set(inspect(engine).get_table_names())
    assert "sector_flow" not in tables, "M1 cut: sector_flow must be gone"
    for expected in (
        "holding",
        "implied_exposure",
        "price_bar",
        "sector_momentum",
        "put_call_ratio",
        "filing_event",
        "freshness",
    ):
        assert expected in tables, f"missing table: {expected}"

    second = apply_migrations(engine)
    assert second == 0  # rerun must be a no-op
