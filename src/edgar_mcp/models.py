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


class FilingDocument(BaseModel):
    """A single document contained within a filing."""

    name: str = Field(description="File name within the filing")
    url: str = Field(description="Direct link to the document")
    size: int | None = Field(default=None, description="Size in bytes, if reported")


class RelatedPerson(BaseModel):
    """An executive officer, director, or promoter named on a filing."""

    name: str = Field(description="Person's full name")
    relationships: list[str] = Field(
        default_factory=list,
        description="Roles, e.g. Executive Officer, Director, Promoter",
    )


class FormDDetails(BaseModel):
    """Structured data parsed from a Form D (Reg D) offering filing."""

    cik: str = Field(description="10-digit CIK of the issuer")
    accession_no: str = Field(description="SEC accession number")
    url: str | None = Field(default=None, description="Link to the filing index")
    is_amendment: bool = Field(description="True if this is a Form D/A amendment")

    issuer_name: str = Field(description="Issuer's legal name")
    entity_type: str | None = Field(
        default=None, description="e.g. Limited Liability Company"
    )
    jurisdiction: str | None = Field(
        default=None, description="Jurisdiction of incorporation"
    )
    year_of_inc: str | None = Field(default=None, description="Year of incorporation")

    industry_group: str | None = Field(default=None, description="Industry group")
    revenue_range: str | None = Field(default=None, description="Issuer revenue range")
    net_asset_value_range: str | None = Field(
        default=None, description="Aggregate net asset value range (funds)"
    )

    security_types: list[str] = Field(
        default_factory=list,
        description="Types of securities offered, e.g. Equity, Debt",
    )
    federal_exemptions: list[str] = Field(
        default_factory=list,
        description="Claimed federal exemptions/exclusions, e.g. 06b",
    )
    date_of_first_sale: str | None = Field(
        default=None, description="Date of first sale (YYYY-MM-DD) or 'Yet to occur'"
    )
    more_than_one_year: bool | None = Field(
        default=None, description="Whether the offering is expected to last over a year"
    )

    minimum_investment: int | None = Field(
        default=None, description="Minimum investment accepted, in dollars"
    )
    total_offering_amount: int | None = Field(
        default=None, description="Total offering amount, in dollars"
    )
    total_amount_sold: int | None = Field(
        default=None, description="Amount sold so far, in dollars"
    )
    total_remaining: int | None = Field(
        default=None, description="Amount remaining to be sold, in dollars"
    )

    has_non_accredited_investors: bool | None = Field(
        default=None, description="Whether any non-accredited investors participated"
    )
    number_non_accredited: int | None = Field(
        default=None, description="Number of non-accredited investors"
    )
    total_investors: int | None = Field(
        default=None, description="Total number of investors already in the offering"
    )

    sales_commissions: int | None = Field(
        default=None, description="Sales commissions paid, in dollars"
    )
    finders_fees: int | None = Field(
        default=None, description="Finders' fees paid, in dollars"
    )

    related_persons: list[RelatedPerson] = Field(
        default_factory=list, description="Executive officers, directors, and promoters"
    )


class Filing(BaseModel):
    """A single filing: its metadata and the documents it contains."""

    cik: str = Field(description="10-digit CIK of the filer")
    accession_no: str = Field(description="SEC accession number")
    form: str | None = Field(default=None, description="Form type, e.g. 10-K, C, D")
    filed: str | None = Field(default=None, description="Filing date, YYYY-MM-DD")
    primary_document: str | None = Field(
        default=None, description="Link to the filing's main document"
    )
    primary_doc_description: str | None = Field(
        default=None, description="Description of the primary document"
    )
    index_url: str = Field(description="Link to the filing's index page")
    documents: list[FilingDocument] = Field(
        default_factory=list, description="All documents in the filing"
    )
