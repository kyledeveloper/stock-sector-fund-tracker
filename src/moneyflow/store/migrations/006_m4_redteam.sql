-- 006: M4 red-team fixes (Phase 3 red team, 2026-10-02).
--
-- B1: form4_transaction PK was (accession, date, code, shares) -- two lots
--     with the same share count in one filing silently collided (DO NOTHING
--     dropped the second). New PK is (accession_number, ordinal): the 0-based
--     row index within the filing, assigned deterministically at parse time.
--     SQLite cannot ALTER a PK, so the table is rebuilt; existing rows are
--     renumbered (rows already lost to the old collision are unrecoverable --
--     documented in REDTEAM.md).
-- M2: form4_filing.form_type ("4" | "4/A") -- amendments are flagged in the
--     panel, not auto-superseded (v1 cannot reliably link a 4/A to its
--     original accession).
-- M3: form4_filing.is_joint_filing -- joint filings store all owner names
--     and OR their officer/director flags (no silent exclusion).

ALTER TABLE form4_filing ADD COLUMN form_type TEXT NOT NULL DEFAULT '4';
ALTER TABLE form4_filing ADD COLUMN is_joint_filing INTEGER NOT NULL DEFAULT 0;

CREATE TABLE form4_transaction_new (
    accession_number   TEXT NOT NULL,
    ordinal            INTEGER NOT NULL,
    transaction_date   TEXT NOT NULL,
    transaction_code   TEXT NOT NULL,
    shares             INTEGER NOT NULL,
    price              REAL,
    value_usd          REAL,
    side               TEXT NOT NULL DEFAULT '',
    is_open_market_buy INTEGER NOT NULL DEFAULT 0,
    is_10b5_1          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (accession_number, ordinal),
    FOREIGN KEY (accession_number) REFERENCES form4_filing(accession_number)
);

INSERT INTO form4_transaction_new
    (accession_number, ordinal, transaction_date, transaction_code,
     shares, price, value_usd, side, is_open_market_buy, is_10b5_1)
    SELECT accession_number,
           ROW_NUMBER() OVER (
               PARTITION BY accession_number
               ORDER BY transaction_date, transaction_code, shares, price
           ) - 1,
           transaction_date, transaction_code, shares, price,
           value_usd, side, is_open_market_buy, is_10b5_1
    FROM form4_transaction;

DROP TABLE form4_transaction;
ALTER TABLE form4_transaction_new RENAME TO form4_transaction;
