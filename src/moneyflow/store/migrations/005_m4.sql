-- M4 (Phase 3): 13F-HR quarterly holdings + Form 4 insider transactions.
-- 13F rows keyed by (report_date, cik, cusip, put_call): the same CUSIP can
-- appear twice (common stock + option leg) and those are independent rows.

CREATE TABLE IF NOT EXISTS thirteenf_holding (
    report_date   TEXT NOT NULL,
    cik           TEXT NOT NULL,
    cusip         TEXT NOT NULL,
    put_call      TEXT NOT NULL DEFAULT '',
    filed_at      TEXT NOT NULL,
    filer_name    TEXT NOT NULL DEFAULT '',
    issuer        TEXT NOT NULL DEFAULT '',
    title_of_class TEXT NOT NULL DEFAULT '',
    value_usd     REAL NOT NULL,
    shares        INTEGER NOT NULL,
    PRIMARY KEY (report_date, cik, cusip, put_call)
);

CREATE TABLE IF NOT EXISTS form4_filing (
    accession_number TEXT PRIMARY KEY,
    ticker           TEXT NOT NULL,
    issuer           TEXT NOT NULL DEFAULT '',
    insider          TEXT NOT NULL DEFAULT '',
    officer_title    TEXT NOT NULL DEFAULT '',
    is_officer       INTEGER NOT NULL DEFAULT 0,
    is_director      INTEGER NOT NULL DEFAULT 0,
    filed_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS form4_transaction (
    accession_number  TEXT NOT NULL,
    transaction_date  TEXT NOT NULL,
    transaction_code  TEXT NOT NULL,
    shares            INTEGER NOT NULL,
    price             REAL,
    value_usd         REAL,
    side              TEXT NOT NULL DEFAULT '',
    is_open_market_buy INTEGER NOT NULL DEFAULT 0,
    is_10b5_1         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (accession_number, transaction_date, transaction_code, shares),
    FOREIGN KEY (accession_number) REFERENCES form4_filing(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_form4_filing_ticker_filed
    ON form4_filing(ticker, filed_at);
