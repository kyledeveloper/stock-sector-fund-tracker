-- 002: sector_momentum was missing from 001 (found by red-team review).
-- Same idempotent-upsert convention: PRIMARY KEY (as_of, ticker).

CREATE TABLE IF NOT EXISTS sector_momentum (
    as_of        TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    rs_20d       REAL NOT NULL,
    rs_60d       REAL NOT NULL,
    rrg_quadrant TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (as_of, ticker)
);
