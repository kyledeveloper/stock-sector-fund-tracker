"""PoliteClient unit tests (no network: httpx MockTransport)."""

import httpx

from moneyflow.common.http import PoliteClient


def _client_for(handler):
    return PoliteClient(
        min_interval_s=0,
        trust_env=False,
        transport=httpx.MockTransport(handler),
    )


def test_compliant_user_agent_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, text="ok")

    c = _client_for(handler)
    assert c.get("https://example.com").status_code == 200
    assert "us-moneyflow" in seen["ua"]


def test_retries_then_raises_on_persistent_500():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, text="boom")

    c = _client_for(handler)
    try:
        c.get("https://example.com")
    except httpx.HTTPStatusError:
        pass
    assert len(calls) == 3  # max_retries
