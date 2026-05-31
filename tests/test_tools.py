import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.edgar_client import (
    BROWSE_EDGAR_URL,
    FULLTEXT_SEARCH_URL,
    SUBMISSIONS_URL,
    TICKERS_EXCHANGE_URL,
)

# An empty ticker map — forces the private-company search fallback.
_EMPTY_TICKERS = {"fields": ["cik", "name", "ticker", "exchange"], "data": []}
# browse-edgar company-search results (multi-match Atom: CIKs, no usable name).
_SEARCH_ATOM = (
    "<feed><entry><content><company-info>"
    "<cik>0001661779</cik></company-info></content></entry></feed>"
)
# browse-edgar single-CIK Atom (carries the conformed name).
_NAME_ATOM = (
    "<feed><content><company-info>"
    "<conformed-name>STARTENGINE CROWDFUNDING, INC.</conformed-name>"
    "<cik>0001661779</cik></company-info></content></feed>"
)

# One efts (full-text search) hit, shaped like a real Form C result.
_EFTS_FORM_C = {
    "hits": {
        "hits": [
            {
                "_id": "0002133509-26-000001:primary_doc.xml",
                "_source": {
                    "ciks": ["0002133509"],
                    "display_names": ["1000 Hawthorn Crossings LLC  (CIK 0002133509)"],
                    "form": "C",
                    "root_forms": ["C"],
                    "file_date": "2026-05-29",
                    "adsh": "0002133509-26-000001",
                },
            }
        ]
    }
}


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_offerings_form_c(ctx) -> None:
    respx.get(FULLTEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_EFTS_FORM_C)
    )
    offerings = await server.get_recent_offerings(ctx, "C", limit=5)

    assert len(offerings) == 1
    o = offerings[0]
    assert o.form == "C"
    assert o.cik == "0002133509"
    assert o.accession_no == "0002133509-26-000001"
    assert o.url is not None
    # archive paths use the dash-stripped accession number
    assert o.url.endswith("000213350926000001/primary_doc.xml")


@pytest.mark.asyncio
async def test_get_recent_offerings_rejects_bad_form(ctx) -> None:
    with pytest.raises(ValueError):
        await server.get_recent_offerings(ctx, "X")


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_offerings_reg_a_maps_to_1a(ctx) -> None:
    route = respx.get(FULLTEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_EFTS_FORM_C)
    )
    await server.get_recent_offerings(ctx, "A")
    assert route.calls.last.request.url.params["forms"] == "1-A"


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_offerings_state_filter(ctx) -> None:
    route = respx.get(FULLTEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_EFTS_FORM_C)
    )
    await server.get_recent_offerings(ctx, "D", state="ca")
    params = route.calls.last.request.url.params
    assert params["forms"] == "D"
    assert params["locationCodes"] == "CA"  # normalized to upper-case


_FILING_BASE = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106"
_INDEX_JSON = {
    "directory": {
        "item": [
            {"name": "aapl-20230930.htm", "size": "1000", "type": "text.gif"},
            {"name": "ex-21.htm", "size": "", "type": "text.gif"},
        ]
    }
}
_SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": ["0000320193-23-000106"],
            "form": ["10-K"],
            "filingDate": ["2023-11-03"],
            "primaryDocument": ["aapl-20230930.htm"],
            "primaryDocDescription": ["10-K"],
        }
    }
}


@respx.mock
@pytest.mark.asyncio
async def test_get_filing_by_url(ctx) -> None:
    respx.get(f"{_FILING_BASE}/index.json").mock(
        return_value=httpx.Response(200, json=_INDEX_JSON)
    )
    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS)
    )

    filing = await server.get_filing(f"{_FILING_BASE}/aapl-20230930.htm", ctx)

    assert filing.cik == "0000320193"
    assert filing.accession_no == "0000320193-23-000106"
    assert filing.form == "10-K"
    assert filing.filed == "2023-11-03"
    assert filing.primary_document is not None
    assert filing.primary_document.endswith("/aapl-20230930.htm")
    assert filing.index_url.endswith("0000320193-23-000106-index.htm")
    assert len(filing.documents) == 2
    assert filing.documents[0].size == 1000
    assert filing.documents[1].size is None  # empty size -> None


@pytest.mark.asyncio
async def test_get_filing_bare_accession_needs_cik(ctx) -> None:
    with pytest.raises(ValueError):
        await server.get_filing("0000320193-23-000106", ctx)


@respx.mock
@pytest.mark.asyncio
async def test_lookup_issuer_private_company_fallback(ctx) -> None:
    # Not in the ticker map -> falls back to EDGAR company search + name lookup.
    respx.get(TICKERS_EXCHANGE_URL).mock(
        return_value=httpx.Response(200, json=_EMPTY_TICKERS)
    )
    respx.get(BROWSE_EDGAR_URL).mock(
        side_effect=[
            httpx.Response(200, text=_SEARCH_ATOM),  # company search -> CIK
            httpx.Response(200, text=_NAME_ATOM),  # single-CIK -> name
        ]
    )

    issuers = await server.lookup_issuer("StartEngine", ctx)

    assert len(issuers) == 1
    assert issuers[0].cik == "0001661779"
    assert "STARTENGINE" in issuers[0].name.upper()


@respx.mock
@pytest.mark.asyncio
async def test_list_filings_resolves_private_company_name(ctx) -> None:
    respx.get(TICKERS_EXCHANGE_URL).mock(
        return_value=httpx.Response(200, json=_EMPTY_TICKERS)
    )
    respx.get(BROWSE_EDGAR_URL).mock(
        return_value=httpx.Response(200, text=_SEARCH_ATOM)
    )
    respx.get(SUBMISSIONS_URL.format(cik="0001661779")).mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "STARTENGINE CROWDFUNDING, INC.",
                "filings": {
                    "recent": {
                        "form": ["10-Q"],
                        "filingDate": ["2026-05-20"],
                        "accessionNumber": ["0001104659-26-064442"],
                        "primaryDocument": ["primary_doc.htm"],
                    }
                },
            },
        )
    )

    filings = await server.list_filings("StartEngine", ctx, limit=5)

    assert filings
    assert filings[0].issuer.startswith("STARTENGINE")
    assert filings[0].form == "10-Q"


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_offerings_lowercase_form_ok(ctx) -> None:
    route = respx.get(FULLTEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_EFTS_FORM_C)
    )
    await server.get_recent_offerings(ctx, "c")
    # "c" should be normalized to "C" and sent as the forms filter
    assert route.called
    assert route.calls.last.request.url.params["forms"] == "C"
