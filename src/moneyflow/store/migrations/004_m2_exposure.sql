-- 004: M2 redefined as holdings snapshot (user decision D, 2026-10-01).
-- implied_exposure (flow x weight) has no producer without M1 flows.
-- Replace with stock_exposure: per-stock cross-sector weight aggregation.

DROP TABLE IF EXISTS implied_exposure;

CREATE TABLE IF NOT EXISTS stock_exposure (
    as_of            TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    total_weight     REAL NOT NULL,
    etf_count        INTEGER NOT NULL DEFAULT 1,
    contributing     TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (as_of, ticker)
);
