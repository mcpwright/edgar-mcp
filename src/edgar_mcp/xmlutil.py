"""Shared value coercion for parsing SEC submission XML (Form C, Form D, …).

The element-text extraction differs per form (Form D is namespace-free, Form C
is namespaced), but the value cleaning/coercion is identical — so it lives here.
"""

from __future__ import annotations

_TRUE = {"true", "t", "yes", "y", "1"}
_FALSE = {"false", "f", "no", "n", "0"}


def clean(text: str | None) -> str | None:
    """Strip whitespace; treat empty/whitespace-only as None."""
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def to_int(value: str | None) -> int | None:
    """Parse a count/dollar field to int; non-numeric (e.g. 'Indefinite') -> None."""
    cleaned = value.replace(",", "").strip() if value else ""
    return int(cleaned) if cleaned.lstrip("-").isdigit() else None


def to_float(value: str | None) -> float | None:
    """Parse a decimal field to float; non-numeric -> None."""
    if value is None:
        return None
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return None


def to_bool(value: str | None) -> bool | None:
    """Parse a boolean field — handles true/false, yes/no, Y/N, 1/0."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None
