"""Shared HTTP client: compliant User-Agent, retries, politeness delays.

SEC EDGAR fair-access rules REQUIRE a descriptive User-Agent with contact
info and cap anonymous traffic at 10 req/s. Every adapter in ingest/
must go through here, never raw httpx. SEC callers use sec_client(),
which refuses to run without MONEYFLOW_CONTACT_EMAIL (Auditor P1 #5).

Retries (Auditor P1 #6): 429/5xx honor Retry-After (seconds or HTTP-date),
otherwise exponential backoff; jitter is added and exponential waits are
capped at max_backoff_s. A server Retry-After above max_backoff_s means give
up immediately: retrying early can extend an SEC block. The whole call also
gives up once the next wait would push total waiting past max_total_wait_s.
"""

from __future__ import annotations

import os
import random
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

DEFAULT_UA = "us-moneyflow/0.1 (+https://github.com/kyledeveloper; personal research tool)"
CONTACT_ENV = "MONEYFLOW_CONTACT_EMAIL"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# RFC 2606 reserved names (README placeholder is you@example.com).
_PLACEHOLDER_DOMAIN = re.compile(
    r"(^|\.)example\.(com|org|net)$|(^|\.)(example|invalid|test|localhost)$"
)

# Conservative default: well under SEC's 10 req/s and typical site limits.
DEFAULT_MIN_INTERVAL_S = 0.5
DEFAULT_MAX_BACKOFF_S = 60.0
DEFAULT_MAX_TOTAL_WAIT_S = 180.0


class SecContactMissing(RuntimeError):
    """SEC requires a contact email in the User-Agent; refuse to send without it."""


def sec_user_agent() -> str:
    email = os.environ.get(CONTACT_ENV, "").strip()
    domain = email.rsplit("@", 1)[-1].lower().rstrip(".")
    if not _EMAIL.match(email) or _PLACEHOLDER_DOMAIN.search(domain):
        raise SecContactMissing(
            f"set {CONTACT_ENV} to a real contact email before pulling SEC EDGAR "
            "(SEC fair-access policy requires it in the User-Agent)"
        )
    return f"us-moneyflow/0.1 ({email}; +https://github.com/kyledeveloper)"


def _retry_after_s(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isascii() and raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class PoliteClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        trust_env: bool = True,  # False in tests (sandbox proxy env breaks MockTransport)
        transport: httpx.BaseTransport | None = None,  # inject MockTransport in tests
        max_backoff_s: float = DEFAULT_MAX_BACKOFF_S,
        max_total_wait_s: float = DEFAULT_MAX_TOTAL_WAIT_S,
        sleep: Callable[[float], None] = time.sleep,  # injectable: tests never really sleep
        jitter: Callable[[], float] = lambda: random.uniform(0.0, 0.5),
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            timeout=timeout_s,
            follow_redirects=True,
            trust_env=trust_env,
            transport=transport,
        )
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._max_backoff_s = max_backoff_s
        self._max_total_wait_s = max_total_wait_s
        self._sleep = sleep
        self._jitter = jitter
        self._last_call = 0.0

    def _polite_wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval_s:
            self._sleep(self._min_interval_s - elapsed)

    def _backoff(self, attempt: int, resp: httpx.Response | None) -> float | None:
        """Seconds to wait before the next attempt, or None to give up now."""
        hinted = _retry_after_s(resp) if resp is not None else None
        if hinted is not None:
            if hinted > self._max_backoff_s:
                return None  # server asked for longer than we will wait
            return hinted + self._jitter()
        return min(float(2**attempt) + self._jitter(), self._max_backoff_s)

    def get(self, url: str, **kwargs) -> httpx.Response:
        last_exc: httpx.HTTPError | None = None
        last_resp: httpx.Response | None = None
        waited = 0.0
        for attempt in range(self._max_retries):
            self._polite_wait()
            try:
                resp = self._client.get(url, **kwargs)
            except httpx.HTTPError as exc:  # network-level: retry
                last_exc, last_resp = exc, None
            else:
                self._last_call = time.monotonic()
                if resp.status_code != 429 and resp.status_code < 500:
                    resp.raise_for_status()  # 4xx (non-429): fail fast, no retry
                    return resp
                last_exc, last_resp = None, resp  # retryable status
            if attempt == self._max_retries - 1:
                break
            delay = self._backoff(attempt, last_resp)
            if delay is None or waited + delay > self._max_total_wait_s:
                break
            self._sleep(delay)
            waited += delay
        if last_exc is not None:
            raise last_exc
        assert last_resp is not None  # loop always runs >= 1 attempt
        last_resp.raise_for_status()  # persistent 429/5xx -> HTTPStatusError
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._client.close()


def sec_client(**kwargs) -> PoliteClient:
    """PoliteClient for SEC EDGAR: fails loud without a contact email."""
    return PoliteClient(user_agent=sec_user_agent(), **kwargs)
