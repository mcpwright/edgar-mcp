"""EDGAR MCP server — SEC filings inside your agent.

Built on the official MCP Python SDK (``mcp.server.fastmcp``). All tools are
read-only and hit public SEC endpoints (no API key required).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from .edgar_client import EdgarClient, EdgarError
from .formatting import (
    build_filing_url,
    filing_dir_url,
    filing_fields_from_efts,
    parse_filing_ref,
)
from .formc import parse_form_c
from .formd import parse_form_d
from .forms345 import NotOwnershipDocError, parse_ownership_doc, strip_xsl_prefix
from .htmltext import html_to_text
from .issuers import lookup_issuers, resolve_cik
from .models import (
    CompanyFacts,
    Filing,
    FilingDocument,
    FilingHit,
    FilingText,
    FormCDetails,
    FormDDetails,
    Insider,
    InsiderFiling,
    Issuer,
    Offering,
)
from .xbrl import extract_company_facts

# How many recent ownership filings to scan when building an insider roster.
_INSIDER_SCAN_LIMIT = 40

_INSTRUCTIONS = """\
Read-only access to U.S. SEC EDGAR filings and company data (no API key).

Typical flow:
- Resolve a company first with `lookup_issuer` (name or ticker; works for both
  public and private/non-exchange filers). Use the returned 10-digit CIK with
  the other tools. If several issuers match, ask the user which one they mean.
- Discover raises with `get_recent_offerings` (form "C"=Reg CF, "D"=Reg D,
  "A"=Reg A; optional `state` filter), then screen one with `get_form_d_details`
  or `get_form_c_details` for the actual economics.
- `list_filings` for an issuer's filing history; `search_filings` for full-text.
- `get_filing` lists a filing's documents; pass a document URL to
  `get_filing_text` to read/summarize it (paginated — filings can be huge).
- `get_company_facts` returns XBRL headline financials for public reporting
  companies (most private issuers have none — use the Form C/D tools there).

Monetary amounts are USD. Dates are ISO (YYYY-MM-DD) except Form C fields,
which the SEC formats MM-DD-YYYY.
"""


@dataclass
class AppContext:
    """Resources shared across requests for the lifetime of the server."""

    edgar: EdgarClient


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Own the EDGAR HTTP client: create on startup, close on shutdown."""
    edgar = EdgarClient()
    try:
        yield AppContext(edgar=edgar)
    finally:
        await edgar.aclose()


mcp = FastMCP("edgar", instructions=_INSTRUCTIONS, lifespan=_lifespan)

# Tools only read public data and reach out to the open web.
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def _edgar(ctx: Context) -> EdgarClient:
    """The shared EDGAR client from the lifespan context."""
    app = cast(AppContext, ctx.request_context.lifespan_context)
    return app.edgar


@mcp.tool(annotations=_READ_ONLY)
async def lookup_issuer(query: str, ctx: Context, limit: int = 10) -> list[Issuer]:
    """Resolve a company name or ticker to its SEC CIK and basic identity.

    `query`: a ticker (e.g. "AAPL") or part of a company name (e.g. "Apple" or
    "StartEngine"). Works for exchange-listed public companies AND private /
    non-exchange filers (Reg CF / Reg A issuers, funds). Returns matching issuers
    with their 10-digit CIK, legal name, tickers, and exchange. Resolve a CIK
    here first — the other tools key off it.
    """
    return await lookup_issuers(_edgar(ctx), query, limit)


@mcp.tool(annotations=_READ_ONLY)
async def list_filings(
    cik_or_query: str, ctx: Context, form_type: str | None = None, limit: int = 20
) -> list[FilingHit]:
    """List the most recent filings for one issuer, newest first.

    `cik_or_query`: a CIK (digits) or a ticker/name to resolve.
    `form_type`: optional prefix filter, e.g. "10-K", "8-K", "C", "D".
    """
    edgar = _edgar(ctx)
    cik = await resolve_cik(edgar, cik_or_query)
    sub = await edgar.submissions(cik)
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
    ctx: Context,
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
    data = await _edgar(ctx).full_text_search(
        query, forms=forms, date_from=date_from, date_to=date_to
    )
    hits = data.get("hits", {}).get("hits", [])
    return [FilingHit(**filing_fields_from_efts(h)) for h in hits[:limit]]


@mcp.tool(annotations=_READ_ONLY)
async def get_recent_offerings(
    ctx: Context,
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
    data = await _edgar(ctx).full_text_search(
        forms=[forms_by_regime[f]],
        date_from=since,
        location=state.strip().upper() if state else None,
    )
    hits = data.get("hits", {}).get("hits", [])
    return [Offering(**filing_fields_from_efts(h)) for h in hits[:limit]]


@mcp.tool(annotations=_READ_ONLY)
async def get_filing(
    accession_or_url: str, ctx: Context, cik: str | None = None
) -> Filing:
    """Open one filing: its metadata and the documents it contains.

    `accession_or_url`: a filing `url` returned by another tool, OR an accession
    number (e.g. "0000320193-23-000106"). With a bare accession number, also pass
    `cik`. Returns the form, filing date, a link to the primary document, and
    every document in the filing with its URL.
    """
    edgar = _edgar(ctx)
    resolved_cik, accession = parse_filing_ref(accession_or_url, cik)
    base = filing_dir_url(resolved_cik, accession)

    # Document list from the filing's archive directory.
    index = await edgar.get_json(f"{base}/index.json")
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
        recent = (await edgar.submissions(resolved_cik))["filings"]["recent"]
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
    accession_or_url: str, ctx: Context, cik: str | None = None
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
        xml_text = await _edgar(ctx).get_text(f"{base}/primary_doc.xml")
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
    accession_or_url: str, ctx: Context, cik: str | None = None
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
        xml_text = await _edgar(ctx).get_text(f"{base}/primary_doc.xml")
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
async def get_company_facts(cik_or_query: str, ctx: Context) -> CompanyFacts:
    """Headline financials for a public reporting company, from its XBRL facts.

    Returns the latest annual values for revenue, gross profit, operating
    income, net income, total assets, liabilities, stockholders' equity, and
    cash. `cik_or_query`: a CIK or a name/ticker to resolve.

    Only companies that file XBRL (public reporting companies) have this — most
    private Reg CF / Reg D issuers do not; use `get_form_c_details` /
    `get_form_d_details` for those instead.
    """
    edgar = _edgar(ctx)
    cik = await resolve_cik(edgar, cik_or_query)
    try:
        data = await edgar.company_facts(cik)
    except EdgarError as exc:
        raise ValueError(
            "No XBRL financial data for this issuer — only public reporting "
            "companies have it. For a private raise, try get_form_c_details / "
            "get_form_d_details."
        ) from exc
    return extract_company_facts(data, cik=cik)


@mcp.tool(annotations=_READ_ONLY)
async def get_filing_text(
    url: str, ctx: Context, offset: int = 0, max_chars: int = 20000
) -> FilingText:
    """Fetch a filing document's text — for reading or summarizing it.

    `url`: a document URL from `get_filing` (its `documents` / `primary_document`).
    HTML documents are stripped to plain text. Filings are large (a 10-K can be
    over a million characters), so the result is paginated: pass `offset` and
    `max_chars` to page through. `truncated` indicates more text remains.
    """
    host = urlparse(url).hostname or ""
    if not (host == "sec.gov" or host.endswith(".sec.gov")):
        raise ValueError("url must be an SEC (sec.gov) document URL")

    raw = await _edgar(ctx).get_text(url)
    text = html_to_text(raw) if url.lower().endswith((".htm", ".html")) else raw

    total = len(text)
    offset = max(0, offset)
    page = text[offset : offset + max_chars] if max_chars > 0 else text[offset:]
    return FilingText(
        url=url,
        text=page,
        total_chars=total,
        offset=offset,
        truncated=offset + len(page) < total,
    )


async def _recent_ownership_filings(
    edgar: EdgarClient, cik_or_query: str, *, forms: set[str], max_filings: int
) -> list[InsiderFiling]:
    """Fetch + parse an issuer's recent Section 16 filings of the given forms."""
    cik = await resolve_cik(edgar, cik_or_query)
    recent = (await edgar.submissions(cik))["filings"]["recent"]
    out: list[InsiderFiling] = []
    for form, filed, acc, doc in zip(
        recent["form"],
        recent["filingDate"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        strict=False,
    ):
        if form not in forms:
            continue
        base = filing_dir_url(cik, acc)
        try:
            xml = await edgar.get_text(f"{base}/{strip_xsl_prefix(doc)}")
            out.append(
                parse_ownership_doc(
                    xml, accession_no=acc, filed=filed, url=f"{base}/{acc}-index.htm"
                )
            )
        except (EdgarError, NotOwnershipDocError):
            continue  # skip filings we can't fetch/parse, keep going
        if len(out) >= max_filings:
            break
    return out


@mcp.tool(annotations=_READ_ONLY)
async def get_insider_trades(
    cik_or_query: str, ctx: Context, limit: int = 20
) -> list[InsiderFiling]:
    """Recent insider (Section 16) transactions for a company, newest first.

    Each result is one Form 4 filing: the reporting owner, their role(s), and the
    trades reported (buy/sell/grant/exercise, shares, price, shares owned after).
    `cik_or_query`: a CIK or a name/ticker to resolve.

    Insider data exists for public reporting companies (officers, directors, and
    >10% owners file Forms 3/4/5); most private Reg CF / Reg D issuers have none.
    """
    return await _recent_ownership_filings(
        _edgar(ctx), cik_or_query, forms={"4"}, max_filings=limit
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_insiders(
    cik_or_query: str, ctx: Context, limit: int = 25
) -> list[Insider]:
    """The insiders of a company — officers, directors, and >10% owners.

    Built from recent Section 16 filings (Forms 3/4/5), de-duplicated per person
    with their role(s) and most recent filing date. `cik_or_query`: a CIK or a
    name/ticker. Reflects recent filings, so very large boards may be partial.
    """
    filings = await _recent_ownership_filings(
        _edgar(ctx),
        cik_or_query,
        forms={"3", "4", "5"},
        max_filings=_INSIDER_SCAN_LIMIT,
    )
    roster: dict[str, Insider] = {}
    for f in filings:  # submissions are newest-first, so first sighting is most recent
        key = f.owner_cik or f.owner_name
        existing = roster.get(key)
        if existing is None:
            roster[key] = Insider(
                name=f.owner_name,
                cik=f.owner_cik,
                roles=list(f.roles),
                officer_title=f.officer_title,
                last_filing=f.filed,
            )
        else:
            for role in f.roles:
                if role not in existing.roles:
                    existing.roles.append(role)
    return list(roster.values())[:limit]


def main() -> None:
    """Console entry point — runs over stdio for Claude Desktop / Claude Code."""
    mcp.run()
