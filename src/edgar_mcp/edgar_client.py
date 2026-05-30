"""Async HTTP client for SEC EDGAR public data.

Handles what the SEC asks of API consumers:
- a descriptive ``User-Agent`` header (set ``EDGAR_MCP_USER_AGENT`` to your own contact),
- staying under the ~10 requests/second fair-access limit,
- retrying transient errors (429 / 5xx) with exponential backoff.

All endpoints are public and require no API key.
See https://www.sec.gov/os/webmaster-faq#developers
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

# --- Public SEC endpoints ---------------------------------------------------
TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FULLTEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

DEFAULT_USER_AGENT = os.environ.get(
    "EDGAR_MCP_USER_AGENT",
    "edgar-mcp/0.1 (https://github.com/mcpwright/edgar-mcp)",
)

# The SEC asks consumers to stay at or under 10 req/s; ~8 req/s leaves headroom.
_MIN_INTERVAL = 1.0 / 8


class EdgarError(RuntimeError):
    """Raised when the SEC API returns an error we can't recover from."""


def pad_cik(cik: str | int) -> str:
    """Zero-pad a CIK to the 10-digit form EDGAR's submissions API expects."""
    digits = str(cik).strip().upper().removeprefix("CIK").strip()
    if not digits.isdigit():
        raise ValueError(f"CIK must be numeric, got {cik!r}")
    return digits.zfill(10)


class _RateLimiter:
    """Serialize requests so consecutive calls are spaced >= min_interval apart."""

    def __init__(self, min_interval: float = _MIN_INTERVAL) -> None:
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delay = self._min_interval - (time.monotonic() - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


class EdgarClient:
    """Thin async wrapper over the SEC's public JSON endpoints."""

    def __init__(
        self, user_agent: str = DEFAULT_USER_AGENT, *, max_retries: int = 3
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        self._limiter = _RateLimiter()
        self._max_retries = max_retries

    async def __aenter__(self) -> EdgarClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET a URL as JSON, with throttling and retry on transient failures."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            await self._limiter.wait()
            try:
                resp = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:  # network/timeout — retry
                last_exc = exc
                await asyncio.sleep(2**attempt)
                continue

            if resp.status_code == 404:
                raise EdgarError(f"Not found: {resp.url}")
            if resp.status_code == 429 or resp.status_code >= 500:  # transient — retry
                last_exc = EdgarError(f"SEC returned {resp.status_code} for {resp.url}")
                await asyncio.sleep(2**attempt)
                continue
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

        raise EdgarError(
            f"SEC request failed after {self._max_retries} attempts: {url}"
        ) from last_exc

    # --- typed endpoint helpers --------------------------------------------
    async def company_tickers_exchange(self) -> dict[str, Any]:
        """The full ticker -> CIK -> exchange map (one row per ticker)."""
        return await self.get_json(TICKERS_EXCHANGE_URL)

    async def submissions(self, cik: str | int) -> dict[str, Any]:
        """An issuer's metadata + recent filing history."""
        return await self.get_json(SUBMISSIONS_URL.format(cik=pad_cik(cik)))

    async def full_text_search(
        self,
        query: str,
        *,
        forms: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """EDGAR full-text search over filing documents (efts.sec.gov)."""
        params: dict[str, str] = {"q": query}
        if forms:
            params["forms"] = ",".join(forms)
        if date_from:
            params["startdt"] = date_from
        if date_to:
            params["enddt"] = date_to
        if date_from or date_to:
            params["dateRange"] = "custom"
        return await self.get_json(FULLTEXT_SEARCH_URL, params=params)
