"""Extract a compact financial summary from an SEC XBRL ``companyfacts`` payload.

The companyfacts JSON is huge (hundreds of us-gaap concepts, each with a full
history). This pulls the handful of headline metrics a reader actually wants,
taking each one's latest annual (10-K / full-year) value. Different filers tag
the same metric under different concepts, so each metric tries a candidate list.
"""

from __future__ import annotations

from typing import Any

from .models import CompanyFacts, FinancialFact

# (human label, candidate us-gaap concept tags in priority order)
_KEY_CONCEPTS: list[tuple[str, list[str]]] = [
    (
        "Revenue",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
        ],
    ),
    ("Gross profit", ["GrossProfit"]),
    ("Operating income", ["OperatingIncomeLoss"]),
    ("Net income", ["NetIncomeLoss"]),
    ("Total assets", ["Assets"]),
    ("Total liabilities", ["Liabilities"]),
    (
        "Stockholders equity",
        [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
    ),
    ("Cash & equivalents", ["CashAndCashEquivalentsAtCarryingValue"]),
]


def _latest_annual(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the most recent full-year (10-K / FY) entry, else the most recent."""
    annual = [
        e
        for e in entries
        if str(e.get("form", "")).startswith("10-K") and e.get("fp") == "FY"
    ]
    pool = annual or entries
    if not pool:
        return None
    return max(pool, key=lambda e: e.get("end", ""))


def extract_company_facts(data: dict[str, Any], *, cik: str) -> CompanyFacts:
    """Build a :class:`CompanyFacts` summary from a companyfacts payload."""
    gaap = data.get("facts", {}).get("us-gaap", {})
    facts: list[FinancialFact] = []

    for label, candidates in _KEY_CONCEPTS:
        for concept in candidates:
            node = gaap.get(concept)
            if not node:
                continue
            usd = node.get("units", {}).get("USD")
            if not usd:
                continue
            entry = _latest_annual(usd)
            if entry is None or entry.get("val") is None:
                continue
            facts.append(
                FinancialFact(
                    concept=concept,
                    label=label,
                    value=float(entry["val"]),
                    unit="USD",
                    fiscal_year=entry.get("fy"),
                    period_end=entry.get("end"),
                    form=entry.get("form"),
                )
            )
            break  # first matching concept wins for this metric

    return CompanyFacts(
        cik=cik,
        entity_name=data.get("entityName", ""),
        facts=facts,
    )
