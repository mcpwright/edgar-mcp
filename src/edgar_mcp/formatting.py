"""Helpers that shape raw SEC data into the tool return models."""

from __future__ import annotations

from typing import Any

from .edgar_client import pad_cik

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


def filing_fields_from_efts(hit: dict[str, Any]) -> dict[str, Any]:
    """Extract the common filing fields from one EDGAR full-text search hit.

    Shared by ``search_filings`` and ``get_recent_offerings`` — both consume the
    same efts hit shape. Accession comes from ``adsh``; the primary-document
    filename (when present) is the part after ``:`` in the hit ``_id``.
    """
    src = hit.get("_source", {})
    ciks = src.get("ciks") or []
    cik = pad_cik(ciks[0]) if ciks else None
    accession = src.get("adsh") or hit.get("_id", "").partition(":")[0]
    filename = hit.get("_id", "").partition(":")[2] or None
    names = src.get("display_names") or []
    root_forms = src.get("root_forms") or [""]
    return {
        "issuer": names[0] if names else "",
        "cik": cik,
        "form": src.get("form") or root_forms[0],
        "filed": src.get("file_date", ""),
        "accession_no": accession,
        "url": build_filing_url(cik, accession, filename)
        if cik and accession
        else None,
    }
