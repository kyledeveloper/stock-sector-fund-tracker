-- 001: core tables. All writes are idempotent upserts keyed on
-- (module, as_of, natural key) so a daily re-run never duplicates rows.
-- Money amounts stored as REAL USD; ratios derived in compute/, not here.

CREATE TABLE IF NOT EXISTS sector_flow (
    as_of      TEXT NOT NULL,
    ticker     TEXT NOT NULL,
    net_flow_usd REAL NOT NULL,
    aum_usd    REAL,
    source     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (as_of, ticker, source)
);

CREATE TABLE IF NOT EXISTS holding (
    as_of      TEXT NOT NULL,
    etf_ticker TEXT NOT NULL,
    ticker     TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    weight     REAL NOT NULL,
    PRIMARY KEY (as_of, etf_ticker, ticker)
);

CREATE TABLE IF NOT EXISTS implied_exposure (
    as_of           TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    implied_usd     REAL NOT NULL,
    contributing    TEXT NOT NULL DEFAULT '[]',
    consecutive_days INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (as_of, ticker)
);

CREATE TABLE IF NOT EXISTS price_bar (
    as_of  TEXT NOT NULL,
    ticker TEXT NOT NULL,
    close  REAL NOT NULL,
    volume INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (as_of, ticker)
);

CREATE TABLE IF NOT EXISTS put_call_ratio (
    as_of TEXT NOT NULL,
    scope TEXT NOT NULL,
    ratio REAL NOT NULL,
    PRIMARY KEY (as_of, scope)
);

CREATE TABLE IF NOT EXISTS filing_event (
    as_of      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    cik        TEXT NOT NULL,
    filer_name TEXT NOT NULL DEFAULT '',
    ticker     TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    lag_note   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (as_of, kind, cik, ticker, detail)
);

CREATE TABLE IF NOT EXISTS freshness (
    module     TEXT PRIMARY KEY,
    as_of      TEXT,
    checked_at TEXT NOT NULL DEFAULT '',
    stale      INTEGER NOT NULL DEFAULT 0
);
