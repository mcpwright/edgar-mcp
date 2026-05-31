import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.edgar_client import SUBMISSIONS_URL
from edgar_mcp.forms345 import (
    NotOwnershipDocError,
    parse_ownership_doc,
    strip_xsl_prefix,
)

_FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport>2026-04-27</periodOfReport>
  <issuer>
    <issuerCik>0001661779</issuerCik>
    <issuerName>STARTENGINE CROWDFUNDING, INC.</issuerName>
    <issuerTradingSymbol>STGC</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001934257</rptOwnerCik>
      <rptOwnerName>Marks Howard Edward</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>1</isTenPercentOwner>
      <isOther>0</isOther>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-04-27</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>3827</value></transactionShares>
        <transactionPricePerShare><value>1.6</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>178523500</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
      </ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_strip_xsl_prefix() -> None:
    assert (
        strip_xsl_prefix("xslF345X06/tm2612955-1_4seq1.xml") == "tm2612955-1_4seq1.xml"
    )
    assert strip_xsl_prefix("form4.xml") == "form4.xml"


def test_parse_ownership_doc() -> None:
    f = parse_ownership_doc(
        _FORM4_XML, accession_no="0001104659-26-051451", filed="2026-04-29"
    )
    assert f.form == "4"
    assert f.owner_name == "Marks Howard Edward"
    assert f.owner_cik == "0001934257"
    assert "Director" in f.roles
    assert "Officer (Chief Executive Officer)" in f.roles
    assert "10% owner" in f.roles
    assert len(f.transactions) == 1
    t = f.transactions[0]
    assert t.code == "S"
    assert t.action == "Open-market sale"
    assert t.acquired_disposed == "D"
    assert t.shares == 3827.0
    assert t.price_per_share == 1.6
    assert t.value == pytest.approx(3827 * 1.6)
    assert t.shares_owned_after == 178523500.0
    assert t.direct_or_indirect == "I"


def test_parse_ownership_doc_rejects_non_ownership() -> None:
    with pytest.raises(NotOwnershipDocError):
        parse_ownership_doc("<edgarSubmission/>", accession_no="x")


_SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["4", "10-Q", "4"],
            "filingDate": ["2026-04-29", "2026-05-20", "2026-04-29"],
            "accessionNumber": [
                "0001104659-26-051451",
                "0001104659-26-064442",
                "0001104659-26-051301",
            ],
            "primaryDocument": [
                "xslF345X06/a.xml",
                "stgc-20260331.htm",
                "xslF345X06/b.xml",
            ],
        }
    }
}


@respx.mock
@pytest.mark.asyncio
async def test_get_insider_trades_tool(ctx) -> None:
    respx.get(SUBMISSIONS_URL.format(cik="0001661779")).mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS)
    )
    base = "https://www.sec.gov/Archives/edgar/data/1661779"
    respx.get(f"{base}/000110465926051451/a.xml").mock(
        return_value=httpx.Response(200, text=_FORM4_XML)
    )
    respx.get(f"{base}/000110465926051301/b.xml").mock(
        return_value=httpx.Response(200, text=_FORM4_XML)
    )

    trades = await server.get_insider_trades("1661779", ctx)
    assert len(trades) == 2  # the two Form 4s, not the 10-Q
    assert trades[0].owner_name == "Marks Howard Edward"
    assert trades[0].transactions[0].code == "S"


@respx.mock
@pytest.mark.asyncio
async def test_get_insiders_dedupes_owner(ctx) -> None:
    respx.get(SUBMISSIONS_URL.format(cik="0001661779")).mock(
        return_value=httpx.Response(200, json=_SUBMISSIONS)
    )
    base = "https://www.sec.gov/Archives/edgar/data/1661779"
    respx.get(f"{base}/000110465926051451/a.xml").mock(
        return_value=httpx.Response(200, text=_FORM4_XML)
    )
    respx.get(f"{base}/000110465926051301/b.xml").mock(
        return_value=httpx.Response(200, text=_FORM4_XML)
    )

    insiders = await server.get_insiders("1661779", ctx)
    assert len(insiders) == 1  # same owner across both Form 4s
    assert insiders[0].name == "Marks Howard Edward"
    assert insiders[0].last_filing == "2026-04-29"
