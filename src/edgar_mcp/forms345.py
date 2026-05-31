"""Parser for Section 16 insider filings — Forms 3/4/5 (``ownershipDocument`` XML).

These report who a company's insiders are (officers, directors, >10% owners) and
their trades. The XML is namespace-free. Note the filing's ``primaryDocument``
points at the XSL-rendered HTML (``xslF345.../...xml``); the raw structured XML
is the same path with that prefix stripped (see :func:`strip_xsl_prefix`).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .models import InsiderFiling, InsiderTransaction
from .xmlutil import clean, to_bool, to_float

# SEC Section 16 transaction codes -> human labels (common ones).
_TXN_CODES = {
    "P": "Open-market purchase",
    "S": "Open-market sale",
    "A": "Grant / award",
    "D": "Disposition to the issuer",
    "F": "Shares withheld for taxes",
    "M": "Option / derivative exercise",
    "X": "Option exercise",
    "G": "Gift",
    "C": "Conversion of derivative",
    "V": "Voluntary early report",
    "J": "Other acquisition / disposition",
}

_XSL_PREFIX_RE = re.compile(r"^xsl[^/]+/")


class NotOwnershipDocError(ValueError):
    """Raised when a document isn't a parseable Form 3/4/5 ownership XML."""


def strip_xsl_prefix(document: str) -> str:
    """Turn a Form 3/4/5 ``primaryDocument`` into its raw structured-XML name."""
    return _XSL_PREFIX_RE.sub("", document)


def _t(node: ET.Element | None, path: str) -> str | None:
    return clean(node.findtext(path)) if node is not None else None


def _parse_transaction(txn: ET.Element, *, derivative: bool) -> InsiderTransaction:
    code = _t(txn, "transactionCoding/transactionCode")
    shares = to_float(_t(txn, "transactionAmounts/transactionShares/value"))
    price = to_float(_t(txn, "transactionAmounts/transactionPricePerShare/value"))
    value = shares * price if shares is not None and price is not None else None
    return InsiderTransaction(
        security=_t(txn, "securityTitle/value"),
        date=_t(txn, "transactionDate/value"),
        code=code,
        action=_TXN_CODES.get(code or ""),
        acquired_disposed=_t(
            txn, "transactionAmounts/transactionAcquiredDisposedCode/value"
        ),
        shares=shares,
        price_per_share=price,
        value=value,
        shares_owned_after=to_float(
            _t(txn, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
        ),
        direct_or_indirect=_t(txn, "ownershipNature/directOrIndirectOwnership/value"),
        derivative=derivative,
    )


def parse_ownership_doc(
    xml_text: str,
    *,
    accession_no: str,
    filed: str | None = None,
    url: str | None = None,
) -> InsiderFiling:
    """Parse a Form 3/4/5 ``ownershipDocument`` into an :class:`InsiderFiling`."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise NotOwnershipDocError("Not a valid ownership document") from exc
    if root.tag != "ownershipDocument":
        raise NotOwnershipDocError("Document is not a Form 3/4/5 ownership document")

    # The first reporting owner (joint filings are rare; we report the primary).
    owner = root.find("reportingOwner")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    title = _t(rel, "officerTitle")
    roles: list[str] = []
    if rel is not None:
        if to_bool(rel.findtext("isDirector")):
            roles.append("Director")
        if to_bool(rel.findtext("isOfficer")):
            roles.append(f"Officer ({title})" if title else "Officer")
        if to_bool(rel.findtext("isTenPercentOwner")):
            roles.append("10% owner")
        if to_bool(rel.findtext("isOther")):
            roles.append("Other")

    transactions: list[InsiderTransaction] = []
    for table_tag, txn_tag, deriv in (
        ("nonDerivativeTable", "nonDerivativeTransaction", False),
        ("derivativeTable", "derivativeTransaction", True),
    ):
        table = root.find(table_tag)
        if table is None:
            continue
        for txn in table.findall(txn_tag):
            transactions.append(_parse_transaction(txn, derivative=deriv))

    return InsiderFiling(
        form=_t(root, "documentType") or "",
        filed=filed,
        accession_no=accession_no,
        url=url,
        owner_name=_t(owner, "reportingOwnerId/rptOwnerName") or "",
        owner_cik=_t(owner, "reportingOwnerId/rptOwnerCik"),
        roles=roles,
        officer_title=title,
        transactions=transactions,
    )
