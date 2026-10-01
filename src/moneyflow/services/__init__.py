"""Thin orchestration per module. Phase 1+.

Services wire adapters -> repos -> compute. They contain no SQL, no HTTP,
no parsing -- only sequencing. One service module per product module
(flows/exposure/momentum/smart_money/sentiment).
"""
