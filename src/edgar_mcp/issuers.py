"""Issuer resolution — turn a name/ticker into a CIK (and identity).

Shared by the tools: the ticker map handles exchange-listed companies; EDGAR's
company search backs it up for private / non-exchange filers.
"""

from __future__ import annotations

from typing import Any

from .edgar_client import EdgarClient, pad_cik
from .models import Issuer


def issuers_from_map(data: dict[str, Any], query: str, limit: int) -> list[Issuer]:
    """Match a name/ticker query against the company_tickers_exchange map."""
    fields = data["fields"]
    ci, ni, ti, ei = (fields.index(f) for f in ("cik", "name", "ticker", "exchange"))

    # One CIK can have several ticker rows — aggregate them.
    by_cik: dict[str, dict[str, Any]] = {}
    for row in data["data"]:
        cik = pad_cik(row[ci])
        entry = by_cik.setdefault(
            cik, {"name": row[ni], "tickers": [], "exchange": row[ei]}
        )
        ticker = (row[ti] or "").strip()
        if ticker and ticker not in entry["tickers"]:
            entry["tickers"].append(ticker)
        if not entry["exchange"] and row[ei]:
            entry["exchange"] = row[ei]

    q = query.strip().upper()
    exact: list[Issuer] = []
    partial: list[Issuer] = []
    for cik, e in by_cik.items():
        issuer = Issuer(
            cik=cik, name=e["name"], tickers=e["tickers"], exchange=e["exchange"]
        )
        if q in (t.upper() for t in e["tickers"]):
            exact.append(issuer)
        elif q in e["name"].upper():
            partial.append(issuer)

    return (exact + partial)[:limit]


async def lookup_issuers(edgar: EdgarClient, query: str, limit: int) -> list[Issuer]:
    """Resolve a name/ticker to issuers: ticker map first, then EDGAR company
    search (which also covers private / non-exchange filers)."""
    data = await edgar.company_tickers_exchange()
    matches = issuers_from_map(data, query, limit)
    if matches:
        return matches
    ciks = await edgar.search_company_ciks(query, limit)
    return [Issuer(cik=cik, name=await edgar.company_name(cik) or "") for cik in ciks]


async def resolve_cik(edgar: EdgarClient, cik_or_query: str) -> str:
    """Accept a raw CIK or a name/ticker; return a 10-digit CIK."""
    s = cik_or_query.strip().upper().removeprefix("CIK").strip()
    if s.isdigit():
        return pad_cik(s)
    matches = issuers_from_map(
        await edgar.company_tickers_exchange(), cik_or_query, limit=1
    )
    if matches:
        return matches[0].cik
    # Fall back to EDGAR's company search (covers private / non-exchange filers).
    ciks = await edgar.search_company_ciks(cik_or_query, limit=1)
    if ciks:
        return ciks[0]
    raise ValueError(f"No issuer found matching {cik_or_query!r}")
