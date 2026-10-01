"""Source adapter protocol: one adapter per data source.

Each adapter owns exactly one upstream: fetching its raw payload and
parsing it into canonical models. Adapters never touch the database,
the API layer, or each other (enforced by tests/test_architecture.py).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# NOTE: adapters may only import from moneyflow.models and moneyflow.common
# (enforced by tests/test_architecture.py). No store/services/api imports.


@runtime_checkable
class SourceAdapter(Protocol):
    """Minimal contract every ingest adapter implements."""

    name: str  # e.g. "ssga", "etf_com"

    def fetch_raw(self) -> bytes:
        """Download the raw upstream payload (bytes). No parsing here."""
        ...

    def parse(self, raw: bytes):  # -> list[BaseModel]
        """Pure function: raw bytes -> canonical models. No I/O here."""
        ...

    def fetch(self):  # -> list[BaseModel]
        """Convenience: fetch_raw + parse."""
        return self.parse(self.fetch_raw())
