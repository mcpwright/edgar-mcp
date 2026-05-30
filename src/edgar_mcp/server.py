"""EDGAR MCP server — SEC filings inside your agent.

Built on the official MCP Python SDK (``mcp.server.fastmcp``). All tools are
read-only and hit public SEC endpoints (no API key required).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .edgar_client import EdgarClient, pad_cik
from .formatting import build_filing_url
from .models import FilingHit, Issuer

mcp = FastMCP("edgar")

# Tools only read public data and reach out to the open web.
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

# Shared client, created lazily on first use.
_client: EdgarClient | None = None


def _edgar() -> EdgarClient:
    global _client
    if _client is None:
        _client = EdgarClient()
    return _client


def _issuers_from_map(data: dict[str, Any], query: str, limit: int) -> list[Issuer]:
    """Match a name/ticker query against the company_tickers_exchange map."""
    fields = data["fields"]
    ci, ni, ti, ei = (fields.index(f) for f in ("cik", "name", "ticker", "exchange"))

    # One CIK can have several ticker rows — aggregate them.
    by_cik: dict[str, dict[str, Any]] = {}
    for row in data["data"]:
        cik = pad_cik(row[ci])
        entry = by_cik.setdefault(cik, {"name": row[ni], "tickers": [], "exchange": row[ei]})
        ticker = (row[ti] or "").strip()
        if ticker and ticker not in entry["tickers"]:
            entry["tickers"].append(ticker)
        if not entry["exchange"] and row[ei]:
            entry["exchange"] = row[ei]

    q = query.strip().upper()
    exact: list[Issuer] = []
    partial: list[Issuer] = []
    for cik, e in by_cik.items():
        issuer = Issuer(cik=cik, name=e["name"], tickers=e["tickers"], exchange=e["exchange"])
        if q in (t.upper() for t in e["tickers"]):
            exact.append(issuer)
        elif q in e["name"].upper():
            partial.append(issuer)

    return (exact + partial)[:limit]


async def _resolve_cik(cik_or_query: str) -> str:
    """Accept a raw CIK or a name/ticker; return a 10-digit CIK."""
    s = cik_or_query.strip().upper().removeprefix("CIK").strip()
    if s.isdigit():
        return pad_cik(s)
    matches = _issuers_from_map(await _edgar().company_tickers_exchange(), cik_or_query, limit=1)
    if not matches:
        raise ValueError(f"No issuer found matching {cik_or_query!r}")
    return matches[0].cik


@mcp.tool(annotations=_READ_ONLY)
async def lookup_issuer(query: str, limit: int = 10) -> list[Issuer]:
    """Resolve a company name or ticker to its SEC CIK and basic identity.

    `query`: a ticker (e.g. "AAPL") or part of a company name (e.g. "Apple").
    Returns matching issuers with their 10-digit CIK, legal name, tickers, and
    exchange. Resolve a CIK here first — the other tools key off it.
    """
    data = await _edgar().company_tickers_exchange()
    return _issuers_from_map(data, query, limit)


@mcp.tool(annotations=_READ_ONLY)
async def list_filings(
    cik_or_query: str, form_type: str | None = None, limit: int = 20
) -> list[FilingHit]:
    """List the most recent filings for one issuer, newest first.

    `cik_or_query`: a CIK (digits) or a ticker/name to resolve.
    `form_type`: optional prefix filter, e.g. "10-K", "8-K", "C", "D".
    """
    cik = await _resolve_cik(cik_or_query)
    sub = await _edgar().submissions(cik)
    recent = sub["filings"]["recent"]
    name = sub.get("name", "")

    out: list[FilingHit] = []
    for form, filed, acc, doc in zip(
        recent["form"],
        recent["filingDate"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        strict=False,
    ):
        if form_type and not form.upper().startswith(form_type.upper()):
            continue
        out.append(
            FilingHit(
                issuer=name,
                cik=cik,
                form=form,
                filed=filed,
                accession_no=acc,
                url=build_filing_url(cik, acc, doc),
            )
        )
        if len(out) >= limit:
            break
    return out


@mcp.tool(annotations=_READ_ONLY)
async def search_filings(
    query: str,
    forms: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> list[FilingHit]:
    """Full-text search across SEC filing documents.

    `query`: free text (use quotes inside the string for exact phrases).
    `forms`: optional list of form types to restrict to, e.g. ["10-K", "8-K"].
    `date_from` / `date_to`: ISO dates (YYYY-MM-DD).
    """
    data = await _edgar().full_text_search(query, forms=forms, date_from=date_from, date_to=date_to)
    hits = data.get("hits", {}).get("hits", [])

    out: list[FilingHit] = []
    for h in hits[:limit]:
        src = h.get("_source", {})
        accession, _, filename = h.get("_id", "").partition(":")
        ciks = src.get("ciks") or []
        cik = pad_cik(ciks[0]) if ciks else None
        names = src.get("display_names") or []
        out.append(
            FilingHit(
                issuer=names[0] if names else "",
                cik=cik,
                form=src.get("root_form") or src.get("file_type") or "",
                filed=src.get("file_date", ""),
                accession_no=accession,
                url=build_filing_url(cik, accession, filename) if cik else None,
            )
        )
    return out


def main() -> None:
    """Console entry point — runs over stdio for Claude Desktop / Claude Code."""
    mcp.run()
