import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.edgar_client import COMPANYFACTS_URL, TICKERS_EXCHANGE_URL
from edgar_mcp.xbrl import extract_company_facts

_FACTS = {
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        {
                            "val": 100,
                            "end": "2024-09-28",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                        },
                        {
                            "val": 416,
                            "end": "2025-09-27",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                        },
                        {
                            "val": 90,
                            "end": "2025-06-30",
                            "fy": 2025,
                            "fp": "Q3",
                            "form": "10-Q",
                        },
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "val": 112,
                            "end": "2025-09-27",
                            "fy": 2025,
                            "fp": "FY",
                            "form": "10-K",
                        },
                    ]
                }
            },
        }
    },
}


def test_extract_company_facts_latest_annual() -> None:
    cf = extract_company_facts(_FACTS, cik="0000320193")
    assert cf.entity_name == "Apple Inc."
    by_label = {f.label: f for f in cf.facts}
    # picks the latest FY 10-K value, not the quarterly one
    assert by_label["Revenue"].value == 416.0
    assert by_label["Revenue"].fiscal_year == 2025
    assert by_label["Net income"].value == 112.0


@respx.mock
@pytest.mark.asyncio
async def test_get_company_facts_tool() -> None:
    respx.get(COMPANYFACTS_URL.format(cik="0000320193")).mock(
        return_value=httpx.Response(200, json=_FACTS)
    )
    cf = await server.get_company_facts("320193")  # numeric CIK -> no ticker lookup
    assert cf.cik == "0000320193"
    assert any(f.label == "Revenue" and f.value == 416.0 for f in cf.facts)


@respx.mock
@pytest.mark.asyncio
async def test_get_company_facts_missing_xbrl_raises() -> None:
    respx.get(COMPANYFACTS_URL.format(cik="0009999999")).mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(ValueError):
        await server.get_company_facts("9999999")
