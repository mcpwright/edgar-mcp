"""Typed models returned by the EDGAR MCP tools.

These are the tool *return* types — the MCP SDK derives an output schema from them,
so agents receive structured data, not just text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Issuer(BaseModel):
    """A company (or other filer) identified in SEC EDGAR."""

    cik: str = Field(description="10-digit zero-padded SEC Central Index Key")
    name: str = Field(description="Legal / display name as recorded by the SEC")
    tickers: list[str] = Field(
        default_factory=list, description="Known trading symbols"
    )
    exchange: str | None = Field(
        default=None, description="Primary listing exchange, if any"
    )


class FilingHit(BaseModel):
    """A single filing — from an issuer's history or a full-text search."""

    issuer: str = Field(description="Filer name")
    cik: str | None = Field(default=None, description="10-digit CIK of the filer")
    form: str = Field(description="Form type, e.g. 10-K, 8-K, C, D")
    filed: str = Field(description="Filing date, YYYY-MM-DD")
    accession_no: str = Field(
        description="SEC accession number, e.g. 0000320193-23-000106"
    )
    url: str | None = Field(
        default=None, description="Link to the primary document or filing index"
    )


class Offering(BaseModel):
    """A securities offering filing — Reg CF (Form C) or Reg D (Form D)."""

    issuer: str = Field(description="Issuer name")
    cik: str | None = Field(default=None, description="10-digit CIK of the issuer")
    form: str = Field(description="Form family, e.g. C, C/A, D, D/A")
    filed: str = Field(description="Filing date, YYYY-MM-DD")
    accession_no: str = Field(description="SEC accession number")
    url: str | None = Field(default=None, description="Link to the filing")
