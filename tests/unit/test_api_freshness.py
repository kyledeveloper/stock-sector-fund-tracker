"""Contract test for GET /api/v1/freshness (red-team B3).

Pins the backend shape the React Panel shell consumes:
module / as_of / checked_at (ISO-8601 string) / stale.
If this test goes red, the frontend contract broke -- fix the API,
not the test.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from moneyflow.api.main import app

client = TestClient(app)


def test_freshness_shape_matches_frontend_contract():
    resp = client.get("/api/v1/freshness")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) == 4
    modules = set()
    for rec in body:
        assert set(rec) == {"module", "as_of", "checked_at", "stale"}, rec
        modules.add(rec["module"])
        assert rec["as_of"] is None  # Phase 0 stub: no data yet
        assert rec["stale"] is True
        # checked_at must be an ISO-8601 string -- web/src/api/types.ts
        # mirrors Freshness.checked_at as string.
        datetime.fromisoformat(rec["checked_at"])
    assert modules == {"m2", "m3", "m4", "m5"}  # M1 cut from v1 (user D, 2026-10-01)
