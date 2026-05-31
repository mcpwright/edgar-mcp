import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.formd import NotFormDError, parse_form_d

_FORM_D_XML = """<?xml version="1.0"?>
<edgarSubmission>
  <submissionType>D</submissionType>
  <primaryIssuer>
    <cik>0002137812</cik>
    <entityName>GTOWN CENTURY LP, LLC</entityName>
    <jurisdictionOfInc>WYOMING</jurisdictionOfInc>
    <entityType>Limited Liability Company</entityType>
    <yearOfInc><withinFiveYears>true</withinFiveYears><value>2025</value></yearOfInc>
  </primaryIssuer>
  <relatedPersonsList>
    <relatedPersonInfo>
      <relatedPersonName><firstName>Corban</firstName><lastName>Tomlinson</lastName></relatedPersonName>
      <relatedPersonRelationshipList>
        <relationship>Executive Officer</relationship>
        <relationship>Director</relationship>
      </relatedPersonRelationshipList>
    </relatedPersonInfo>
  </relatedPersonsList>
  <offeringData>
    <industryGroup><industryGroupType>Commercial</industryGroupType></industryGroup>
    <issuerSize><revenueRange>$1,000,001 - $5,000,000</revenueRange></issuerSize>
    <federalExemptionsExclusions><item>06c</item></federalExemptionsExclusions>
    <typeOfFiling>
      <newOrAmendment><isAmendment>false</isAmendment></newOrAmendment>
      <dateOfFirstSale><value>2025-06-19</value></dateOfFirstSale>
    </typeOfFiling>
    <durationOfOffering><moreThanOneYear>false</moreThanOneYear></durationOfOffering>
    <typesOfSecuritiesOffered><isEquityType>true</isEquityType></typesOfSecuritiesOffered>
    <minimumInvestmentAccepted>50000</minimumInvestmentAccepted>
    <offeringSalesAmounts>
      <totalOfferingAmount>3650000</totalOfferingAmount>
      <totalAmountSold>1450000</totalAmountSold>
      <totalRemaining>2200000</totalRemaining>
    </offeringSalesAmounts>
    <investors>
      <hasNonAccreditedInvestors>false</hasNonAccreditedInvestors>
      <totalNumberAlreadyInvested>7</totalNumberAlreadyInvested>
    </investors>
    <salesCommissionsFindersFees>
      <salesCommissions><dollarAmount>0</dollarAmount></salesCommissions>
      <findersFees><dollarAmount>0</dollarAmount></findersFees>
    </salesCommissionsFindersFees>
  </offeringData>
</edgarSubmission>"""


def test_parse_form_d_fields() -> None:
    d = parse_form_d(
        _FORM_D_XML,
        cik="0002137812",
        accession_no="0002137812-26-000001",
        url="http://x/index.htm",
    )
    assert d.issuer_name == "GTOWN CENTURY LP, LLC"
    assert d.jurisdiction == "WYOMING"
    assert d.entity_type == "Limited Liability Company"
    assert d.year_of_inc == "2025"
    assert d.total_offering_amount == 3_650_000
    assert d.total_amount_sold == 1_450_000
    assert d.total_remaining == 2_200_000
    assert d.minimum_investment == 50_000
    assert d.total_investors == 7
    assert d.has_non_accredited_investors is False
    assert d.industry_group == "Commercial"
    assert d.revenue_range == "$1,000,001 - $5,000,000"
    assert d.security_types == ["Equity"]
    assert d.federal_exemptions == ["06c"]
    assert d.is_amendment is False
    assert d.date_of_first_sale == "2025-06-19"
    assert d.sales_commissions == 0
    assert len(d.related_persons) == 1
    assert d.related_persons[0].name == "Corban Tomlinson"
    assert d.related_persons[0].relationships == ["Executive Officer", "Director"]


def test_parse_form_d_rejects_non_form_d() -> None:
    with pytest.raises(NotFormDError):
        parse_form_d(
            "<edgarSubmission><primaryIssuer/></edgarSubmission>",
            cik="1",
            accession_no="x",
        )


@respx.mock
@pytest.mark.asyncio
async def test_get_form_d_details_tool() -> None:
    base = "https://www.sec.gov/Archives/edgar/data/2137812/000213781226000001"
    respx.get(f"{base}/primary_doc.xml").mock(
        return_value=httpx.Response(200, text=_FORM_D_XML)
    )
    d = await server.get_form_d_details(f"{base}/primary_doc.xml")
    assert d.cik == "0002137812"
    assert d.total_offering_amount == 3_650_000
    assert d.total_investors == 7
