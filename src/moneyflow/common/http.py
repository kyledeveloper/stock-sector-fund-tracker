"""Shared HTTP client: compliant User-Agent, retries, politeness delays.

SEC EDGAR fair-access rules REQUIRE a descriptive User-Agent with contact
info and cap anonymous traffic at 10 req/s. Every adapter in ingest/
must go through here, never raw httpx.
"""

from __future__ import annotations

import time

import httpx

DEFAULT_UA = "us-moneyflow/0.1 (+https://github.com/kyledeveloper; personal research tool)"

# Conservative default: well under SEC's 10 req/s and typical site limits.
DEFAULT_MIN_INTERVAL_S = 0.5


class PoliteClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        trust_env: bool = True,  # False in tests (sandbox proxy env breaks MockTransport)
        transport: httpx.BaseTransport | None = None,  # inject MockTransport in tests
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
        self._last_call = 0.0

    def _polite_wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval_s:
            time.sleep(self._min_interval_s - elapsed)

    def get(self, url: str, **kwargs) -> httpx.Response:
        last_exc: httpx.HTTPError | None = None
        last_resp: httpx.Response | None = None
        for attempt in range(self._max_retries):
            self._polite_wait()
            try:
                resp = self._client.get(url, **kwargs)
            except httpx.HTTPError as exc:  # network-level: retry
                last_exc = exc
                time.sleep(2**attempt)
                continue
            self._last_call = time.monotonic()
            if resp.status_code == 429 or resp.status_code >= 500:
                last_resp = resp  # retryable status: back off and retry
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()  # 4xx (non-429): fail fast, no retry
            return resp
        if last_exc is not None:
            raise last_exc
        assert last_resp is not None  # loop always runs >= 1 attempt
        last_resp.raise_for_status()  # persistent 429/5xx -> HTTPStatusError
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._client.close()
