# edgar-mcp

**SEC EDGAR filings, inside your agent.** An [MCP](https://modelcontextprotocol.io) server that
lets an LLM resolve companies, search filings, and pull recent securities offerings straight from
the SEC — built on Anthropic's official [`mcp` Python SDK](https://github.com/modelcontextprotocol/python-sdk).

All tools are **read-only** and hit **public** SEC endpoints (no API key required).

> Status: early but useful. Five tools work today (see below). See the roadmap
> for what's next.

## Tools

| Tool | What it does |
|---|---|
| `lookup_issuer(query, limit=10)` | Resolve a ticker or company name → CIK, legal name, tickers, exchange. Works for exchange-listed **and** private / non-exchange filers (Reg CF / Reg A issuers, funds). |
| `list_filings(cik_or_query, form_type=None, limit=20)` | An issuer's most recent filings, newest first. Optional form-type filter (e.g. `10-K`, `C`, `D`). |
| `search_filings(query, forms=None, date_from=None, date_to=None, limit=20)` | Full-text search across filing documents. |
| `get_recent_offerings(form="C", since=None, state=None, limit=20)` | Recent securities offerings, newest first — `form="C"` (Reg CF) or `form="D"` (Reg D), optionally filtered by issuer `state` (e.g. `"CA"`). |
| `get_filing(accession_or_url, cik=None)` | Open one filing: form, filing date, primary-document link, and every document in the filing. |
| `get_form_d_details(accession_or_url, cik=None)` | Parse a Form D (Reg D) raise: offering amount, sold/remaining, min investment, # investors, industry, revenue range, security types, exemptions, and the officers/directors/promoters. |
| `get_form_c_details(accession_or_url, cik=None)` | Parse a Form C (Reg CF) raise: target/max amount, price, security type, deadline, intermediary, employees, and a two-year financial snapshot (revenue, net income, assets, debt). |

## Install

Requires Python 3.12+. Once published to PyPI, the zero-clone way to run it is:

```bash
uvx edgar-mcp
```

### Claude Code

```bash
claude mcp add edgar -- uvx edgar-mcp
```

### Claude Desktop

Add to `claude_desktop_config.json` (see `examples/`):

```json
{
  "mcpServers": {
    "edgar": { "command": "uvx", "args": ["edgar-mcp"] }
  }
}
```

> **SEC etiquette:** the SEC requires a descriptive `User-Agent` with contact info and rate-limits
> to ~10 req/s. Set your own via the `EDGAR_MCP_USER_AGENT` env var
> (e.g. `"your-app your-email@example.com"`). The client throttles and retries for you.

## Develop

```bash
git clone https://github.com/mcpwright/edgar-mcp && cd edgar-mcp
uv sync
uv run pytest                       # tests (mocked SEC responses)
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy src tests               # strict type checking
uv run mcp dev src/edgar_mcp/server.py   # poke the tools in the MCP Inspector
```

## Roadmap

- [x] `get_recent_offerings(form=C|D)` — recent Reg CF / Reg D raises
- [x] `get_filing(accession_or_url)` — open a filing and list its documents
- [x] `get_form_d_details(...)` — parse Reg D offering data (amount, investors, people)
- [x] `get_form_c_details(...)` — parse Reg CF offering data (target/max, financials, terms)
- [x] State filter on `get_recent_offerings` (industry isn't filterable — EDGAR omits SIC on these listings; screen via `get_form_d_details.industry_group`)
- [ ] `get_company_facts(cik)` — XBRL financials
- [ ] Publish to PyPI + the official MCP Registry

Contributions and issues welcome.

---

Part of [**mcpwright**](https://github.com/mcpwright) · built by [Devender Gollapally](https://github.com/devender)
