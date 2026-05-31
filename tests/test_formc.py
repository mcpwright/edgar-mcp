import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.formc import NotFormCError, parse_form_c

# Namespaced Form C XML (matches the real edgar/formc schema).
_FORM_C_XML = """<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/formc"
                 xmlns:com="http://www.sec.gov/edgar/common">
  <headerData><submissionType>C</submissionType></headerData>
  <formData>
    <issuerInformation>
      <issuerInfo>
        <nameOfIssuer>Keem Ventures Inc</nameOfIssuer>
        <legalStatus>
          <legalStatusForm>Corporation</legalStatusForm>
          <jurisdictionOrganization>MI</jurisdictionOrganization>
          <dateIncorporation>04-20-2026</dateIncorporation>
        </legalStatus>
        <issuerWebsite>https://wefunder.com/keemventures</issuerWebsite>
      </issuerInfo>
      <companyName>Wefunder Portal LLC</companyName>
      <crdNumber>283503</crdNumber>
    </issuerInformation>
    <offeringInformation>
      <securityOfferedType>Preferred Stock</securityOfferedType>
      <noOfSecurityOffered>358</noOfSecurityOffered>
      <price>140.00000</price>
      <priceDeterminationMethod>Dividing pre-money valuation $1,120,000</priceDeterminationMethod>
      <offeringAmount>50000.00</offeringAmount>
      <overSubscriptionAccepted>Y</overSubscriptionAccepted>
      <maximumOfferingAmount>124000.00</maximumOfferingAmount>
      <deadlineDate>04-30-2027</deadlineDate>
    </offeringInformation>
    <annualReportDisclosureRequirements>
      <currentEmployees>1</currentEmployees>
      <totalAssetMostRecentFiscalYear>1000.00</totalAssetMostRecentFiscalYear>
      <revenueMostRecentFiscalYear>5000.00</revenueMostRecentFiscalYear>
      <revenuePriorFiscalYear>2000.00</revenuePriorFiscalYear>
      <netIncomeMostRecentFiscalYear>-3000.00</netIncomeMostRecentFiscalYear>
    </annualReportDisclosureRequirements>
  </formData>
</edgarSubmission>"""


def test_parse_form_c_fields() -> None:
    c = parse_form_c(
        _FORM_C_XML,
        cik="0002136568",
        accession_no="0002136568-26-000001",
        url="http://x/index.htm",
    )
    assert c.submission_type == "C"
    assert c.is_amendment is False
    assert c.issuer_name == "Keem Ventures Inc"
    assert c.legal_status == "Corporation"
    assert c.jurisdiction == "MI"
    assert c.issuer_website == "https://wefunder.com/keemventures"
    assert c.intermediary == "Wefunder Portal LLC"
    assert c.intermediary_crd == "283503"
    assert c.security_type == "Preferred Stock"
    assert c.number_of_securities == 358
    assert c.price == 140.0
    assert c.target_offering_amount == 50_000.0
    assert c.max_offering_amount == 124_000.0
    assert c.oversubscription_accepted is True
    assert c.deadline == "04-30-2027"
    assert c.current_employees == 1
    assert c.financials.revenue_recent == 5_000.0
    assert c.financials.revenue_prior == 2_000.0
    assert c.financials.net_income_recent == -3_000.0
    assert c.financials.total_assets_recent == 1_000.0


def test_parse_form_c_rejects_non_form_c() -> None:
    # Form D-style doc (no formc namespace / no formData) must be rejected.
    with pytest.raises(NotFormCError):
        parse_form_c(
            "<edgarSubmission><offeringData/></edgarSubmission>",
            cik="1",
            accession_no="x",
        )


@respx.mock
@pytest.mark.asyncio
async def test_get_form_c_details_tool() -> None:
    base = "https://www.sec.gov/Archives/edgar/data/2136568/000213656826000001"
    respx.get(f"{base}/primary_doc.xml").mock(
        return_value=httpx.Response(200, text=_FORM_C_XML)
    )
    c = await server.get_form_c_details(f"{base}/primary_doc.xml")
    assert c.cik == "0002136568"
    assert c.target_offering_amount == 50_000.0
    assert c.max_offering_amount == 124_000.0
    assert c.current_employees == 1
