"""Async HTTP client for SEC EDGAR public data.

Handles what the SEC asks of API consumers:
- a descriptive ``User-Agent`` header (set ``EDGAR_MCP_USER_AGENT`` to your own contact),
- staying under the ~10 requests/second fair-access limit,
- retrying transient errors (429 / 5xx) with exponential backoff.

The HTTP plumbing (retry/backoff, throttle, lifecycle) lives in
``mcpwright_core.AsyncHttpClient``; this module adds the SEC endpoints and an
in-memory response cache. All endpoints are public and require no API key.
See https://www.sec.gov/os/webmaster-faq#developers
"""

from __future__ import annotations

import os
import re
from typing import Any, cast

from mcpwright_core import AsyncHttpClient, RateLimiter, TTLCache
from mcpwright_core.errors import HttpError

# --- Public SEC endpoints ---------------------------------------------------
TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FULLTEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
BROWSE_EDGAR_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# browse-edgar's company-search Atom feed (used for private/non-exchange filers).
_CIK_RE = re.compile(r"<cik>(\d+)</cik>")
_CONFORMED_NAME_RE = re.compile(r"<conformed-name>([^<]+)</conformed-name>")

DEFAULT_USER_AGENT = os.environ.get(
    "EDGAR_MCP_USER_AGENT",
    "edgar-mcp/0.1 (https://github.com/mcpwright/edgar-mcp)",
)

# The SEC asks consumers to stay at or under 10 req/s; ~8 req/s leaves headroom.
_RATE_PER_SEC = 8

# Cache TTLs (seconds), chosen by how volatile each endpoint is.
_TTL_IMMUTABLE = 7 * 24 * 3600  # filing-archive content never changes per accession
_TTL_TICKERS = 24 * 3600  # the ticker map changes rarely
_TTL_DEFAULT = 600  # submissions / facts / search — fresh-ish, but worth deduping


def _cache_key(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    query = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{url}?{query}"


def _ttl_for(url: str) -> float:
    """How long a response for this URL may be cached."""
    if "/Archives/edgar/data/" in url:
        return _TTL_IMMUTABLE
    if url == TICKERS_EXCHANGE_URL:
        return _TTL_TICKERS
    return _TTL_DEFAULT


class EdgarError(HttpError):
    """Raised when the SEC API returns an error we can't recover from."""


def pad_cik(cik: str | int) -> str:
    """Zero-pad a CIK to the 10-digit form EDGAR's submissions API expects."""
    digits = str(cik).strip().upper().removeprefix("CIK").strip()
    if not digits.isdigit():
        raise ValueError(f"CIK must be numeric, got {cik!r}")
    return digits.zfill(10)


class EdgarClient(AsyncHttpClient):
    """SEC EDGAR client: the shared HTTP base + an in-memory response cache.

    Throttled to the SEC's fair-access limit, retrying transient errors, and
    caching responses per a TTL policy keyed on how volatile each endpoint is.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        *,
        max_retries: int = 3,
        cache: bool = True,
    ) -> None:
        super().__init__(
            user_agent=user_agent,
            max_retries=max_retries,
            rate_limiter=RateLimiter.per_second(_RATE_PER_SEC),
            error_cls=EdgarError,
            follow_redirects=True,
        )
        # On by default; set EDGAR_MCP_CACHE=0 to disable.
        enabled = cache and os.environ.get("EDGAR_MCP_CACHE", "1") not in ("0", "false")
        self._cache: TTLCache | None = TTLCache() if enabled else None

    async def get_json(
        self, url: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET a URL and parse the JSON body (cached per TTL policy).

        Every EDGAR JSON endpoint returns an object, so this narrows the base
        client's ``Any`` return to ``dict[str, Any]``.
        """
        key = f"json:{_cache_key(url, params)}"
        if self._cache is not None:
            hit, value = await self._cache.get(key)
            if hit:
                return cast("dict[str, Any]", value)
        resp = await self.request("GET", url, params=params)
        data: dict[str, Any] = resp.json()
        if self._cache is not None:
            await self._cache.set(key, data, _ttl_for(url), size=len(resp.content))
        return data

    async def get_text(self, url: str, *, params: dict[str, Any] | None = None) -> str:
        """GET a URL and return the raw text body (cached per TTL policy)."""
        key = f"text:{_cache_key(url, params)}"
        if self._cache is not None:
            hit, value = await self._cache.get(key)
            if hit:
                return cast("str", value)
        resp = await self.request("GET", url, params=params)
        text = resp.text
        if self._cache is not None:
            await self._cache.set(key, text, _ttl_for(url), size=len(text))
        return text

    # --- typed endpoint helpers --------------------------------------------
    async def company_tickers_exchange(self) -> dict[str, Any]:
        """The full ticker -> CIK -> exchange map (one row per ticker)."""
        return await self.get_json(TICKERS_EXCHANGE_URL)

    async def submissions(self, cik: str | int) -> dict[str, Any]:
        """An issuer's metadata + recent filing history."""
        return await self.get_json(SUBMISSIONS_URL.format(cik=pad_cik(cik)))

    async def company_facts(self, cik: str | int) -> dict[str, Any]:
        """XBRL company facts (financial concepts over time). 404s for filers
        without XBRL data (i.e. most non-reporting private companies)."""
        return await self.get_json(COMPANYFACTS_URL.format(cik=pad_cik(cik)))

    async def full_text_search(
        self,
        query: str = "",
        *,
        forms: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """EDGAR full-text search over filing documents (efts.sec.gov).

        With no ``query``, results are browsed by ``forms`` / date and returned
        newest-first — useful for "recent filings of form type X". ``location``
        is a state/country code (or comma-separated list) filtering on the
        filer's principal place of business.
        """
        params: dict[str, str] = {}
        if query:
            params["q"] = query
        if forms:
            params["forms"] = ",".join(forms)
        if location:
            params["locationCodes"] = location
        if date_from:
            params["startdt"] = date_from
        if date_to:
            params["enddt"] = date_to
        if date_from or date_to:
            params["dateRange"] = "custom"
        return await self.get_json(FULLTEXT_SEARCH_URL, params=params)

    async def search_company_ciks(self, query: str, limit: int = 10) -> list[str]:
        """Resolve a company name to candidate CIKs via EDGAR's company search.

        Unlike the ticker map, this includes private / non-exchange filers
        (Reg CF and Reg A issuers, funds, etc.). Returns 10-digit CIKs, in the
        order EDGAR ranks them.
        """
        text = await self.get_text(
            BROWSE_EDGAR_URL,
            params={
                "action": "getcompany",
                "company": query,
                "type": "",
                "output": "atom",
                "count": str(max(limit, 10)),
            },
        )
        seen: list[str] = []
        for cik in _CIK_RE.findall(text):
            padded = cik.zfill(10)
            if padded not in seen:
                seen.append(padded)
        return seen[:limit]

    async def company_name(self, cik: str | int) -> str | None:
        """The canonical (conformed) name for a CIK, or None if not found."""
        text = await self.get_text(
            BROWSE_EDGAR_URL,
            params={
                "action": "getcompany",
                "CIK": pad_cik(cik),
                "type": "",
                "output": "atom",
                "count": "1",
            },
        )
        m = _CONFORMED_NAME_RE.search(text)
        return m.group(1) if m else None
