"""Implied per-stock exposure (M2). Phase 2.

Pure functions only: inputs are canonical models, outputs are canonical
models. No I/O, no DB, no HTTP -- trivially unit-testable.

Methodology caveats (red team F3, load-bearing):
- In-kind creations/redemptions involve NO market buying of constituents.
- Mechanical flows (401k, rebalancing, tax-loss harvesting) are mixed in.
- Therefore the output is "config-style capital exposure (estimate)",
  never "inflow"/主力/聪明钱. The panel copy is enforced by contract test.
- Holdings file is T-1 vs flow date: align as-of dates before multiplying.
- Single-partition invariant: one ticker in at most one source ETF
  (the 11 SPDR sector ETFs partition the S&P 500) -- no double counting.
"""

from moneyflow.models import Holding, ImpliedExposure, SectorFlow


def implied_exposure(flows: list[SectorFlow], holdings: list[Holding]) -> list[ImpliedExposure]:
    raise NotImplementedError("Phase 2")
