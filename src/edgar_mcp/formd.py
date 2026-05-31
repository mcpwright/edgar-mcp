"""Parser for the structured Form D (Reg D) submission XML (``primary_doc.xml``).

Form D filings carry a clean, namespace-free ``edgarSubmission`` XML with the
fields a private-markets reader actually wants — offering size, amount sold,
minimum check, investor count, industry, revenue, security types, exemptions,
and the officers/directors/promoters behind the raise.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .models import FormDDetails, RelatedPerson

# typesOfSecuritiesOffered boolean flags -> human labels
_SECURITY_TYPE_LABELS = {
    "isEquityType": "Equity",
    "isDebtType": "Debt",
    "isOptionToAcquireType": "Option to Acquire",
    "isSecurityToBeAcquiredType": "Security to be Acquired",
    "isPooledInvestmentFundType": "Pooled Investment Fund",
    "isTenantInCommonType": "Tenant-in-Common",
    "isMineralPropertyType": "Mineral Property",
    "isOtherType": "Other",
}


def _text(node: ET.Element | None, path: str) -> str | None:
    """findtext that treats empty elements as None."""
    if node is None:
        return None
    value = node.findtext(path)
    value = value.strip() if value else ""
    return value or None


def _int(value: str | None) -> int | None:
    """Parse a dollar/count field to int; non-numeric (e.g. 'Indefinite') -> None."""
    if value and value.replace(",", "").strip().isdigit():
        return int(value.replace(",", "").strip())
    return None


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return {"true": True, "false": False}.get(value.strip().lower())


class NotFormDError(ValueError):
    """Raised when the document isn't a Form D submission."""


def parse_form_d(
    xml_text: str, *, cik: str, accession_no: str, url: str | None = None
) -> FormDDetails:
    """Parse a Form D ``primary_doc.xml`` into a :class:`FormDDetails`."""
    root = ET.fromstring(xml_text)
    if root.tag != "edgarSubmission" or root.find("offeringData") is None:
        raise NotFormDError("Document is not a Form D submission")

    issuer = root.find("primaryIssuer")
    offering = root.find("offeringData")
    assert offering is not None  # guaranteed by the check above

    # Securities offered (the "true" boolean flags).
    sec = offering.find("typesOfSecuritiesOffered")
    security_types = [
        label
        for tag, label in _SECURITY_TYPE_LABELS.items()
        if sec is not None and (sec.findtext(tag) or "").strip().lower() == "true"
    ]

    exemptions = [
        i.text.strip()
        for i in offering.findall("federalExemptionsExclusions/item")
        if i.text and i.text.strip()
    ]

    # Date of first sale, or the "yet to occur" flag.
    first_sale = _text(offering, "typeOfFiling/dateOfFirstSale/value")
    if first_sale is None and _bool(
        _text(offering, "typeOfFiling/dateOfFirstSale/yetToOccur")
    ):
        first_sale = "Yet to occur"

    related_persons: list[RelatedPerson] = []
    for rp in root.findall("relatedPersonsList/relatedPersonInfo"):
        parts = [
            rp.findtext("relatedPersonName/firstName") or "",
            rp.findtext("relatedPersonName/middleName") or "",
            rp.findtext("relatedPersonName/lastName") or "",
        ]
        name = " ".join(p.strip() for p in parts if p.strip())
        rels = [
            r.text.strip()
            for r in rp.findall("relatedPersonRelationshipList/relationship")
            if r.text and r.text.strip()
        ]
        related_persons.append(RelatedPerson(name=name, relationships=rels))

    return FormDDetails(
        cik=cik,
        accession_no=accession_no,
        url=url,
        is_amendment=bool(
            _bool(_text(offering, "typeOfFiling/newOrAmendment/isAmendment"))
        ),
        issuer_name=_text(issuer, "entityName") or "",
        entity_type=_text(issuer, "entityType"),
        jurisdiction=_text(issuer, "jurisdictionOfInc"),
        year_of_inc=_text(issuer, "yearOfInc/value"),
        industry_group=_text(offering, "industryGroup/industryGroupType"),
        revenue_range=_text(offering, "issuerSize/revenueRange"),
        net_asset_value_range=_text(offering, "issuerSize/aggregateNetAssetValueRange"),
        security_types=security_types,
        federal_exemptions=exemptions,
        date_of_first_sale=first_sale,
        more_than_one_year=_bool(_text(offering, "durationOfOffering/moreThanOneYear")),
        minimum_investment=_int(_text(offering, "minimumInvestmentAccepted")),
        total_offering_amount=_int(
            _text(offering, "offeringSalesAmounts/totalOfferingAmount")
        ),
        total_amount_sold=_int(_text(offering, "offeringSalesAmounts/totalAmountSold")),
        total_remaining=_int(_text(offering, "offeringSalesAmounts/totalRemaining")),
        has_non_accredited_investors=_bool(
            _text(offering, "investors/hasNonAccreditedInvestors")
        ),
        number_non_accredited=_int(
            _text(offering, "investors/numberOfNonAccreditedInvestors")
        ),
        total_investors=_int(_text(offering, "investors/totalNumberAlreadyInvested")),
        sales_commissions=_int(
            _text(offering, "salesCommissionsFindersFees/salesCommissions/dollarAmount")
        ),
        finders_fees=_int(
            _text(offering, "salesCommissionsFindersFees/findersFees/dollarAmount")
        ),
        related_persons=related_persons,
    )
