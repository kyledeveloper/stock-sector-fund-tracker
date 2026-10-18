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


# --- Auditor P1 #5/#6: configurable SEC contact UA, Retry-After, jitter, caps ---

from datetime import UTC, datetime, timedelta  # noqa: E402
from email.utils import format_datetime  # noqa: E402

import pytest  # noqa: E402

from moneyflow.common import http as http_mod  # noqa: E402


def _sleepy_client(handler, **kw):
    slept: list[float] = []
    c = PoliteClient(
        min_interval_s=0,
        trust_env=False,
        transport=httpx.MockTransport(handler),
        sleep=slept.append,
        jitter=lambda: 0.0,
        **kw,
    )
    return c, slept


def _seq(*responses):
    it = iter(responses)
    return lambda request: next(it)


def test_retry_after_seconds_is_honored():
    c, slept = _sleepy_client(
        _seq(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, text="ok"))
    )
    assert c.get("https://example.com").status_code == 200
    assert slept == [7.0]


def test_retry_after_http_date_is_honored():
    when = datetime.now(UTC) + timedelta(seconds=30)
    hdr = format_datetime(when, usegmt=True)
    c, slept = _sleepy_client(
        _seq(httpx.Response(503, headers={"Retry-After": hdr}), httpx.Response(200, text="ok"))
    )
    c.get("https://example.com")
    assert len(slept) == 1 and 25 <= slept[0] <= 31


def test_retry_after_is_capped_per_wait():
    c, slept = _sleepy_client(
        _seq(httpx.Response(429, headers={"Retry-After": "3600"}), httpx.Response(200, text="ok")),
        max_backoff_s=60,
    )
    c.get("https://example.com")
    assert slept == [60.0]


def test_garbage_retry_after_falls_back_to_exponential():
    c, slept = _sleepy_client(
        _seq(
            httpx.Response(429, headers={"Retry-After": "soon"}),
            httpx.Response(429),
            httpx.Response(200, text="ok"),
        )
    )
    c.get("https://example.com")
    assert slept == [1.0, 2.0]


def test_jitter_is_added_to_backoff():
    slept: list[float] = []
    c = PoliteClient(
        min_interval_s=0,
        trust_env=False,
        transport=httpx.MockTransport(_seq(httpx.Response(500), httpx.Response(200))),
        sleep=slept.append,
        jitter=lambda: 0.25,
    )
    c.get("https://example.com")
    assert slept == [1.25]


def test_total_retry_budget_stops_early():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "50"})

    c, slept = _sleepy_client(handler, max_retries=5, max_total_wait_s=80)
    with pytest.raises(httpx.HTTPStatusError):
        c.get("https://example.com")
    assert sum(slept) <= 80
    assert len(calls) == 2  # second wait of 50s would exceed the 80s budget


def test_no_sleep_after_final_attempt():
    c, slept = _sleepy_client(lambda r: httpx.Response(500), max_retries=3)
    with pytest.raises(httpx.HTTPStatusError):
        c.get("https://example.com")
    assert slept == [1.0, 2.0]  # 3 attempts, 2 waits between them


def test_sec_user_agent_includes_contact_email(monkeypatch):
    monkeypatch.setenv("MONEYFLOW_CONTACT_EMAIL", "ops@example.org")
    ua = http_mod.sec_user_agent()
    assert "us-moneyflow" in ua and "ops@example.org" in ua


def test_sec_user_agent_without_email_fails_loud(monkeypatch):
    monkeypatch.delenv("MONEYFLOW_CONTACT_EMAIL", raising=False)
    with pytest.raises(http_mod.SecContactMissing, match="MONEYFLOW_CONTACT_EMAIL"):
        http_mod.sec_user_agent()


def test_sec_user_agent_rejects_non_email(monkeypatch):
    monkeypatch.setenv("MONEYFLOW_CONTACT_EMAIL", "not-an-email")
    with pytest.raises(http_mod.SecContactMissing):
        http_mod.sec_user_agent()
