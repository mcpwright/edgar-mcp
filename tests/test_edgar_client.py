import httpx
import pytest
import respx

from edgar_mcp.edgar_client import (
    SUBMISSIONS_URL,
    EdgarClient,
    EdgarError,
    pad_cik,
)
from edgar_mcp.formatting import build_filing_url, parse_filing_ref


def test_pad_cik_variants() -> None:
    assert pad_cik(320193) == "0000320193"
    assert pad_cik("320193") == "0000320193"
    assert pad_cik("CIK0000320193") == "0000320193"
    assert pad_cik("0000320193") == "0000320193"


def test_pad_cik_rejects_non_numeric() -> None:
    with pytest.raises(ValueError):
        pad_cik("apple")


def test_build_filing_url_primary_document() -> None:
    url = build_filing_url("0000320193", "0000320193-23-000106", "aapl-20230930.htm")
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    )


def test_build_filing_url_falls_back_to_index() -> None:
    url = build_filing_url("320193", "0000320193-23-000106", None)
    assert url.endswith("000032019323000106/0000320193-23-000106-index.htm")


def test_parse_filing_ref_from_url() -> None:
    cik, acc = parse_filing_ref(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        None,
    )
    assert cik == "0000320193"
    assert acc == "0000320193-23-000106"


def test_parse_filing_ref_accession_with_cik() -> None:
    cik, acc = parse_filing_ref("0000320193-23-000106", "320193")
    assert cik == "0000320193"
    assert acc == "0000320193-23-000106"


def test_parse_filing_ref_accession_without_cik_raises() -> None:
    with pytest.raises(ValueError):
        parse_filing_ref("0000320193-23-000106", None)


def test_parse_filing_ref_garbage_raises() -> None:
    with pytest.raises(ValueError):
        parse_filing_ref("not-a-filing", None)


@respx.mock
@pytest.mark.asyncio
async def test_submissions_returns_json() -> None:
    cik = "0000320193"
    respx.get(SUBMISSIONS_URL.format(cik=cik)).mock(
        return_value=httpx.Response(200, json={"name": "Apple Inc."})
    )
    async with EdgarClient() as client:
        data = await client.submissions("320193")
    assert data["name"] == "Apple Inc."


@respx.mock
@pytest.mark.asyncio
async def test_404_raises_edgar_error() -> None:
    cik = "9999999999"
    respx.get(SUBMISSIONS_URL.format(cik=cik)).mock(return_value=httpx.Response(404))
    async with EdgarClient() as client:
        with pytest.raises(EdgarError):
            await client.submissions(cik)
