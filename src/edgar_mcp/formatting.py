"""Helpers that shape raw SEC data into the tool return models."""

from __future__ import annotations

ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


def build_filing_url(
    cik: str | int, accession_no: str, primary_document: str | None
) -> str:
    """Build a link to a filing's primary document, or its index page if unknown.

    EDGAR archive paths use the integer CIK and the accession number with dashes
    stripped, e.g.
        https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm
    """
    cik_int = int(str(cik).lstrip("0") or "0")
    acc_nodash = accession_no.replace("-", "")
    base = f"{ARCHIVES_BASE}/{cik_int}/{acc_nodash}"
    if primary_document:
        return f"{base}/{primary_document}"
    return f"{base}/{accession_no}-index.htm"
