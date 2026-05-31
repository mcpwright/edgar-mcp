"""EDGAR MCP server — SEC filings inside your agent.

Built on the official MCP Python SDK (``mcp.server.fastmcp``). All tools are
read-only and hit public SEC endpoints (no API key required).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .edgar_client import EdgarClient, EdgarError, pad_cik
from .formatting import (
    build_filing_url,
    filing_dir_url,
    filing_fields_from_efts,
    parse_filing_ref,
)
from .formc import parse_form_c
from .formd import parse_form_d
from .models import (
    CompanyFacts,
    Filing,
    FilingDocument,
    FilingHit,
    FormCDetails,
    FormDDetails,
    Issuer,
    Offering,
)
from .xbrl import extract_company_facts

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


async def _resolve_cik(cik_or_query: str) -> str:
    """Accept a raw CIK or a name/ticker; return a 10-digit CIK."""
    s = cik_or_query.strip().upper().removeprefix("CIK").strip()
    if s.isdigit():
        return pad_cik(s)
    matches = _issuers_from_map(
        await _edgar().company_tickers_exchange(), cik_or_query, limit=1
    )
    if matches:
        return matches[0].cik
    # Fall back to EDGAR's company search (covers private / non-exchange filers).
    ciks = await _edgar().search_company_ciks(cik_or_query, limit=1)
    if ciks:
        return ciks[0]
    raise ValueError(f"No issuer found matching {cik_or_query!r}")


@mcp.tool(annotations=_READ_ONLY)
async def lookup_issuer(query: str, limit: int = 10) -> list[Issuer]:
    """Resolve a company name or ticker to its SEC CIK and basic identity.

    `query`: a ticker (e.g. "AAPL") or part of a company name (e.g. "Apple" or
    "StartEngine"). Works for exchange-listed public companies AND private /
    non-exchange filers (Reg CF / Reg A issuers, funds). Returns matching issuers
    with their 10-digit CIK, legal name, tickers, and exchange. Resolve a CIK
    here first — the other tools key off it.
    """
    data = await _edgar().company_tickers_exchange()
    matches = _issuers_from_map(data, query, limit)
    if matches:
        return matches
    # Not in the (exchange-only) ticker map — fall back to EDGAR's company
    # search, which includes private / non-exchange filers.
    ciks = await _edgar().search_company_ciks(query, limit)
    return [
        Issuer(cik=cik, name=await _edgar().company_name(cik) or "") for cik in ciks
    ]


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
    data = await _edgar().full_text_search(
        query, forms=forms, date_from=date_from, date_to=date_to
    )
    hits = data.get("hits", {}).get("hits", [])
    return [FilingHit(**filing_fields_from_efts(h)) for h in hits[:limit]]


@mcp.tool(annotations=_READ_ONLY)
async def get_recent_offerings(
    form: str = "C",
    since: str | None = None,
    state: str | None = None,
    limit: int = 20,
) -> list[Offering]:
    """List recent securities offerings filed with the SEC, newest first.

    `form`: "C" for Regulation Crowdfunding (Form C family — C, C/A, C-U, C-AR),
    "D" for Regulation D (Form D family — D, D/A), or "A" for Regulation A
    (Form 1-A family — 1-A, 1-A/A, 1-A POS).
    `since`: optional ISO date (YYYY-MM-DD) lower bound on the filing date.
    `state`: optional 2-letter US state code (e.g. "CA") filtering on the
    issuer's principal place of business; comma-separate for several.
    Returns issuer, exact form, filed date, accession number, and a link.

    Note: there's no industry filter here — EDGAR doesn't populate an industry
    code on these listings. To screen by industry, open a result with
    `get_form_d_details` (its `industry_group`) or `get_form_c_details`.
    """
    forms_by_regime = {"C": "C", "D": "D", "A": "1-A"}
    f = form.strip().upper()
    if f not in forms_by_regime:
        raise ValueError('form must be "C" (Reg CF), "D" (Reg D), or "A" (Reg A)')
    data = await _edgar().full_text_search(
        forms=[forms_by_regime[f]],
        date_from=since,
        location=state.strip().upper() if state else None,
    )
    hits = data.get("hits", {}).get("hits", [])
    return [Offering(**filing_fields_from_efts(h)) for h in hits[:limit]]


@mcp.tool(annotations=_READ_ONLY)
async def get_filing(accession_or_url: str, cik: str | None = None) -> Filing:
    """Open one filing: its metadata and the documents it contains.

    `accession_or_url`: a filing `url` returned by another tool, OR an accession
    number (e.g. "0000320193-23-000106"). With a bare accession number, also pass
    `cik`. Returns the form, filing date, a link to the primary document, and
    every document in the filing with its URL.
    """
    resolved_cik, accession = parse_filing_ref(accession_or_url, cik)
    base = filing_dir_url(resolved_cik, accession)

    # Document list from the filing's archive directory.
    index = await _edgar().get_json(f"{base}/index.json")
    items = index.get("directory", {}).get("item", [])
    documents = [
        FilingDocument(
            name=it["name"],
            url=f"{base}/{it['name']}",
            size=int(it["size"]) if str(it.get("size") or "").isdigit() else None,
        )
        for it in items
    ]

    # Metadata + primary document from the issuer's submissions history. Only
    # the most recent filings are in `recent`; for older ones this is skipped
    # and we still return the document list.
    form = filed = primary_doc = primary_desc = None
    try:
        recent = (await _edgar().submissions(resolved_cik))["filings"]["recent"]
        idx = recent["accessionNumber"].index(accession)
        form = recent["form"][idx]
        filed = recent["filingDate"][idx]
        primary_desc = recent["primaryDocDescription"][idx] or None
        pdoc = recent["primaryDocument"][idx]
        primary_doc = f"{base}/{pdoc}" if pdoc else None
    except (EdgarError, ValueError, KeyError):
        pass

    return Filing(
        cik=resolved_cik,
        accession_no=accession,
        form=form,
        filed=filed,
        primary_document=primary_doc,
        primary_doc_description=primary_desc,
        index_url=f"{base}/{accession}-index.htm",
        documents=documents,
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_form_d_details(
    accession_or_url: str, cik: str | None = None
) -> FormDDetails:
    """Parse a Form D (Reg D) filing's structured offering data.

    Returns the offering amount, amount sold and remaining, minimum investment,
    number of investors, industry, revenue range, security types, claimed
    exemptions, and the officers / directors / promoters behind the raise — the
    fields you actually screen a private placement on.

    `accession_or_url`: a Form D filing `url` (from `get_recent_offerings` or
    `list_filings`), or an accession number (then also pass `cik`).
    """
    resolved_cik, accession = parse_filing_ref(accession_or_url, cik)
    base = filing_dir_url(resolved_cik, accession)
    try:
        xml_text = await _edgar().get_text(f"{base}/primary_doc.xml")
    except EdgarError as exc:
        raise ValueError(
            "Could not load the Form D document for this filing — "
            "is it a Form D / D-A offering?"
        ) from exc
    return parse_form_d(
        xml_text,
        cik=resolved_cik,
        accession_no=accession,
        url=f"{base}/{accession}-index.htm",
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_form_c_details(
    accession_or_url: str, cik: str | None = None
) -> FormCDetails:
    """Parse a Form C (Reg CF crowdfunding) filing's structured data.

    Returns the offering terms (target & maximum raise, price per security,
    security type, deadline, oversubscription), the funding-portal intermediary,
    employee count, and a two-year financial snapshot (revenue, net income,
    assets, cash, debt) — the fields you screen a crowdfunding raise on.

    `accession_or_url`: a Form C filing `url` (from `get_recent_offerings` or
    `list_filings`), or an accession number (then also pass `cik`).
    """
    resolved_cik, accession = parse_filing_ref(accession_or_url, cik)
    base = filing_dir_url(resolved_cik, accession)
    try:
        xml_text = await _edgar().get_text(f"{base}/primary_doc.xml")
    except EdgarError as exc:
        raise ValueError(
            "Could not load the Form C document for this filing — "
            "is it a Form C / Reg CF offering?"
        ) from exc
    return parse_form_c(
        xml_text,
        cik=resolved_cik,
        accession_no=accession,
        url=f"{base}/{accession}-index.htm",
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_company_facts(cik_or_query: str) -> CompanyFacts:
    """Headline financials for a public reporting company, from its XBRL facts.

    Returns the latest annual values for revenue, gross profit, operating
    income, net income, total assets, liabilities, stockholders' equity, and
    cash. `cik_or_query`: a CIK or a name/ticker to resolve.

    Only companies that file XBRL (public reporting companies) have this — most
    private Reg CF / Reg D issuers do not; use `get_form_c_details` /
    `get_form_d_details` for those instead.
    """
    cik = await _resolve_cik(cik_or_query)
    try:
        data = await _edgar().company_facts(cik)
    except EdgarError as exc:
        raise ValueError(
            "No XBRL financial data for this issuer — only public reporting "
            "companies have it. For a private raise, try get_form_c_details / "
            "get_form_d_details."
        ) from exc
    return extract_company_facts(data, cik=cik)


def main() -> None:
    """Console entry point — runs over stdio for Claude Desktop / Claude Code."""
    mcp.run()
