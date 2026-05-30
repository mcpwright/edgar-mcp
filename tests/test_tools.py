import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.edgar_client import FULLTEXT_SEARCH_URL

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
async def test_get_recent_offerings_form_c() -> None:
    respx.get(FULLTEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_EFTS_FORM_C)
    )
    offerings = await server.get_recent_offerings("C", limit=5)

    assert len(offerings) == 1
    o = offerings[0]
    assert o.form == "C"
    assert o.cik == "0002133509"
    assert o.accession_no == "0002133509-26-000001"
    assert o.url is not None
    # archive paths use the dash-stripped accession number
    assert o.url.endswith("000213350926000001/primary_doc.xml")


@pytest.mark.asyncio
async def test_get_recent_offerings_rejects_bad_form() -> None:
    with pytest.raises(ValueError):
        await server.get_recent_offerings("X")


@respx.mock
@pytest.mark.asyncio
async def test_get_recent_offerings_lowercase_form_ok() -> None:
    route = respx.get(FULLTEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_EFTS_FORM_C)
    )
    await server.get_recent_offerings("c")
    # "c" should be normalized to "C" and sent as the forms filter
    assert route.called
    assert route.calls.last.request.url.params["forms"] == "C"
