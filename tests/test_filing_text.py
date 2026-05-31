import httpx
import pytest
import respx

from edgar_mcp import server
from edgar_mcp.htmltext import html_to_text

_HTML = """<html><head><title>nope</title><style>.x{color:red}</style></head>
<body>
  <h1>Risk Factors</h1>
  <p>We may not become&nbsp;profitable.</p>
  <script>console.log('drop me')</script>
  <div>Competition is intense.</div>
</body></html>"""


def test_html_to_text_strips_tags_and_scripts() -> None:
    text = html_to_text(_HTML)
    assert "Risk Factors" in text
    assert "We may not become profitable." in text
    assert "Competition is intense." in text
    # script / style / title contents are dropped
    assert "drop me" not in text
    assert "color:red" not in text
    assert "nope" not in text


@respx.mock
@pytest.mark.asyncio
async def test_get_filing_text_paginates() -> None:
    url = "https://www.sec.gov/Archives/edgar/data/320193/x/doc.htm"
    respx.get(url).mock(
        return_value=httpx.Response(200, text="<p>" + "A" * 50 + "</p>")
    )

    page1 = await server.get_filing_text(url, offset=0, max_chars=20)
    assert page1.total_chars == 50
    assert len(page1.text) == 20
    assert page1.truncated is True

    page2 = await server.get_filing_text(url, offset=40, max_chars=20)
    assert len(page2.text) == 10
    assert page2.truncated is False


@pytest.mark.asyncio
async def test_get_filing_text_rejects_non_sec_url() -> None:
    with pytest.raises(ValueError):
        await server.get_filing_text("https://evil.example.com/x.htm")
