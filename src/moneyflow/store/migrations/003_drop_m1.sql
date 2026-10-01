-- 003: M1 cut from v1 (user decision 2026-10-01, option D).
-- $0 sources cannot provide daily per-sector fund flows (see docs/POC.md),
-- so the sector_flow table has no producer. Drop it; keep history honest.
-- implied_exposure stays: Phase 1 (M2 holdings snapshot) will define its shape.

DROP TABLE IF EXISTS sector_flow;
