"""Versioned SQL migrations. Explicit files, tiny runner, fully auditable.

Convention: store/migrations/NNN_name.sql applied in order, tracked in
_schema_version. No ORM autogenerate -- every schema change is a reviewed file.
"""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements.

    Quote- and comment-aware: semicolons inside '...', "...", -- comments
    or /* ... */ blocks do not split. Migration files are ours, but a
    naive text.split(";") would corrupt a future statement containing a
    literal semicolon -- this costs 30 lines once and prevents a class
    of silent schema bugs.
    """
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_single = in_double = False
    in_line_comment = in_block_comment = False
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 1
                in_block_comment = False
        elif in_single:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":  # '' is an escaped quote, not the end
                    buf.append(nxt)
                    i += 1
                else:
                    in_single = False
        elif in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
        elif ch == "-" and nxt == "-":
            buf.append(ch + nxt)
            i += 1
            in_line_comment = True
        elif ch == "/" and nxt == "*":
            buf.append(ch + nxt)
            i += 1
            in_block_comment = True
        elif ch == "'":
            buf.append(ch)
            in_single = True
        elif ch == '"':
            buf.append(ch)
            in_double = True
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


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
                for stmt in _split_statements(f.read_text()):
                    conn.exec_driver_sql(stmt)
                conn.exec_driver_sql("INSERT INTO _schema_version (version) VALUES (?)", (version,))
                applied += 1
    return applied
