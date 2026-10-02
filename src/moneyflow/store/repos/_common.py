"""Shared helpers for the repository package."""

from __future__ import annotations

from datetime import date


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
