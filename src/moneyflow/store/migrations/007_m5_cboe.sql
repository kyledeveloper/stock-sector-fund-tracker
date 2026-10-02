CREATE TABLE IF NOT EXISTS cboe_putcall (
    trade_date TEXT PRIMARY KEY,
    total_put_call REAL NOT NULL,
    equity_put_call REAL NOT NULL,
    index_put_call REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT ''
);
