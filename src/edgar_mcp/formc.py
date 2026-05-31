"""Parser for the structured Form C (Reg CF crowdfunding) submission XML.

Unlike Form D, Form C's ``primary_doc.xml`` is XML-namespaced
(``http://www.sec.gov/edgar/formc``). It carries the offering terms (target /
max raise, price, security type, deadline), the funding-portal intermediary,
employee count, and a two-year financial snapshot.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .models import FormCDetails, FormCFinancials
from .xmlutil import clean, to_bool, to_float, to_int

_NS = {"f": "http://www.sec.gov/edgar/formc"}


class NotFormCError(ValueError):
    """Raised when the document isn't a Form C submission."""


def _text(node: ET.Element | None, tag: str) -> str | None:
    """Descendant findtext within ``node`` for a formc-namespaced tag."""
    if node is None:
        return None
    el = node.find(f".//f:{tag}", _NS)
    return clean(el.text) if el is not None else None


def parse_form_c(
    xml_text: str, *, cik: str, accession_no: str, url: str | None = None
) -> FormCDetails:
    """Parse a Form C ``primary_doc.xml`` into a :class:`FormCDetails`."""
    root = ET.fromstring(xml_text)
    submission_type = _text(root, "submissionType")
    if root.find(".//f:formData", _NS) is None or not (
        submission_type or ""
    ).upper().startswith("C"):
        raise NotFormCError("Document is not a Form C submission")

    issuer_information = root.find(".//f:issuerInformation", _NS)
    issuer_info = root.find(".//f:issuerInformation/f:issuerInfo", _NS)
    offering = root.find(".//f:offeringInformation", _NS)
    annual = root.find(".//f:annualReportDisclosureRequirements", _NS)

    financials = FormCFinancials(
        revenue_recent=to_float(_text(annual, "revenueMostRecentFiscalYear")),
        revenue_prior=to_float(_text(annual, "revenuePriorFiscalYear")),
        net_income_recent=to_float(_text(annual, "netIncomeMostRecentFiscalYear")),
        net_income_prior=to_float(_text(annual, "netIncomePriorFiscalYear")),
        total_assets_recent=to_float(_text(annual, "totalAssetMostRecentFiscalYear")),
        total_assets_prior=to_float(_text(annual, "totalAssetPriorFiscalYear")),
        cash_recent=to_float(_text(annual, "cashEquiMostRecentFiscalYear")),
        cash_prior=to_float(_text(annual, "cashEquiPriorFiscalYear")),
        accounts_receivable_recent=to_float(
            _text(annual, "actReceivedMostRecentFiscalYear")
        ),
        accounts_receivable_prior=to_float(_text(annual, "actReceivedPriorFiscalYear")),
        short_term_debt_recent=to_float(
            _text(annual, "shortTermDebtMostRecentFiscalYear")
        ),
        short_term_debt_prior=to_float(_text(annual, "shortTermDebtPriorFiscalYear")),
        long_term_debt_recent=to_float(
            _text(annual, "longTermDebtMostRecentFiscalYear")
        ),
        long_term_debt_prior=to_float(_text(annual, "longTermDebtPriorFiscalYear")),
        cost_of_goods_sold_recent=to_float(
            _text(annual, "costGoodsSoldMostRecentFiscalYear")
        ),
        cost_of_goods_sold_prior=to_float(
            _text(annual, "costGoodsSoldPriorFiscalYear")
        ),
        taxes_paid_recent=to_float(_text(annual, "taxPaidMostRecentFiscalYear")),
        taxes_paid_prior=to_float(_text(annual, "taxPaidPriorFiscalYear")),
    )

    return FormCDetails(
        cik=cik,
        accession_no=accession_no,
        url=url,
        submission_type=submission_type,
        is_amendment=bool(submission_type and submission_type.upper().endswith("/A")),
        issuer_name=_text(issuer_info, "nameOfIssuer") or "",
        legal_status=_text(issuer_info, "legalStatusForm"),
        jurisdiction=_text(issuer_info, "jurisdictionOrganization"),
        date_incorporation=_text(issuer_info, "dateIncorporation"),
        issuer_website=_text(issuer_info, "issuerWebsite"),
        intermediary=_text(issuer_information, "companyName"),
        intermediary_crd=_text(issuer_information, "crdNumber"),
        security_type=_text(offering, "securityOfferedType"),
        security_other_desc=_text(offering, "securityOfferedOtherDesc"),
        number_of_securities=to_int(_text(offering, "noOfSecurityOffered")),
        price=to_float(_text(offering, "price")),
        price_determination_method=_text(offering, "priceDeterminationMethod"),
        target_offering_amount=to_float(_text(offering, "offeringAmount")),
        max_offering_amount=to_float(_text(offering, "maximumOfferingAmount")),
        oversubscription_accepted=to_bool(_text(offering, "overSubscriptionAccepted")),
        deadline=_text(offering, "deadlineDate"),
        current_employees=to_int(_text(annual, "currentEmployees")),
        financials=financials,
    )
