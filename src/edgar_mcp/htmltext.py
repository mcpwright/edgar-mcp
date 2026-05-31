"""Minimal HTML-to-text conversion (stdlib only) for reading filing documents."""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Tags whose contents we drop entirely. ix:header wraps the inline-XBRL hidden
# facts / references that otherwise dump metadata noise at the top of modern
# filings (10-K, 10-Q); visible inline facts (ix:nonfraction, …) sit outside it.
_SKIP = {"script", "style", "head", "title", "ix:header", "ix:hidden"}
# Tags that imply a line/paragraph break around their content.
_BLOCK = {
    "p",
    "div",
    "br",
    "tr",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "section",
    "article",
    "header",
    "footer",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(html: str) -> str:
    """Strip HTML to readable plain text, collapsing whitespace."""
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.text()
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n\s*", "\n\n", text)
    return text.strip()
