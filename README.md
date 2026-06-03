# edgar-mcp

<!-- mcp-name: io.github.mcpwright/edgar-mcp -->

**SEC EDGAR filings, inside your agent.** An [MCP](https://modelcontextprotocol.io) server that
lets an LLM resolve companies, search filings, and pull recent securities offerings straight from
the SEC — built on Anthropic's official [`mcp` Python SDK](https://github.com/modelcontextprotocol/python-sdk).

All tools are **read-only** and hit **public** SEC endpoints (no API key required).

> Status: 11 tools, working today (see below). Published on PyPI as
> [`mcpwright-edgar`](https://pypi.org/project/mcpwright-edgar/) and in the
> [official MCP Registry](https://registry.modelcontextprotocol.io). See the roadmap for what's next.

## Tools

| Tool | What it does |
|---|---|
| `lookup_issuer(query, limit=10)` | Resolve a ticker or company name → CIK, legal name, tickers, exchange. Works for exchange-listed **and** private / non-exchange filers (Reg CF / Reg A issuers, funds). |
| `list_filings(cik_or_query, form_type=None, limit=20)` | An issuer's most recent filings, newest first. Optional form-type filter (e.g. `10-K`, `C`, `D`). |
| `search_filings(query, forms=None, date_from=None, date_to=None, limit=20)` | Full-text search across filing documents. |
| `get_recent_offerings(form="C", since=None, state=None, limit=20)` | Recent securities offerings, newest first — `form="C"` (Reg CF), `"D"` (Reg D), or `"A"` (Reg A), optionally filtered by issuer `state` (e.g. `"CA"`). |
| `get_filing(accession_or_url, cik=None)` | Open one filing: form, filing date, primary-document link, and every document in the filing. |
| `get_form_d_details(accession_or_url, cik=None)` | Parse a Form D (Reg D) raise: offering amount, sold/remaining, min investment, # investors, industry, revenue range, security types, exemptions, and the officers/directors/promoters. |
| `get_form_c_details(accession_or_url, cik=None)` | Parse a Form C (Reg CF) raise: target/max amount, price, security type, deadline, intermediary, employees, and a two-year financial snapshot (revenue, net income, assets, debt). |
| `get_company_facts(cik_or_query)` | Headline financials from a public company's XBRL facts: latest annual revenue, gross/operating income, net income, assets, liabilities, equity, cash. |
| `get_filing_text(url, offset=0, max_chars=20000)` | Fetch a document's text (HTML stripped) for reading/summarizing — paginated, since filings can exceed 1M characters. |
| `get_insiders(cik_or_query, limit=25)` | A company's insiders (officers, directors, >10% owners) from recent Section 16 filings, with roles. |
| `get_insider_trades(cik_or_query, limit=20)` | Recent insider transactions (Form 4): owner, role, buy/sell/grant, shares, price, shares owned after. |

## Install

Requires Python 3.12+. The zero-clone way to run it (the PyPI package is
`mcpwright-edgar`; the command, server, and tools are all "edgar"):

```bash
uvx mcpwright-edgar
```

### Claude Code

```bash
claude mcp add edgar -- uvx mcpwright-edgar
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "edgar": { "command": "uvx", "args": ["mcpwright-edgar"] }
  }
}
```

### OpenAI Agents SDK (Python)

It's a standard MCP server, so it works with any MCP-capable client — not just Claude.
With the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/mcp/):

```python
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main():
    async with MCPServerStdio(
        name="edgar",
        params={
            "command": "uvx",
            "args": ["mcpwright-edgar"],
            "env": {"EDGAR_MCP_USER_AGENT": "your-app you@example.com"},
        },
    ) as edgar:
        agent = Agent(
            name="Analyst",
            instructions="Use the EDGAR tools for SEC filings and company data.",
            mcp_servers=[edgar],
        )
        result = await Runner.run(
            agent, "Recent Reg D raises in California — who's behind the biggest?"
        )
        print(result.final_output)
```

### Any other MCP client (Cursor, VS Code, Cline, Goose, Zed, …)

They all launch a stdio MCP server the same way — point yours at:

```json
{
  "mcpServers": {
    "edgar": {
      "command": "uvx",
      "args": ["mcpwright-edgar"],
      "env": { "EDGAR_MCP_USER_AGENT": "your-app you@example.com" }
    }
  }
}
```

> Hosted chat connectors (e.g. ChatGPT connectors) expect a **remote** MCP server over
> Streamable HTTP; `mcpwright-edgar` runs locally over stdio. Running it behind Streamable
> HTTP for a hosted endpoint is straightforward if you need that.

> **SEC etiquette:** the SEC requires a descriptive `User-Agent` with contact info and rate-limits
> to ~10 req/s. Set your own via the `EDGAR_MCP_USER_AGENT` env var
> (e.g. `"your-app your-email@example.com"`). The client throttles and retries for you.

> **Caching:** responses are cached in-memory (byte-budgeted LRU) to cut latency and SEC load —
> immutable filing-archive content for days, the ticker map for 24h, everything else briefly.
> Set `EDGAR_MCP_CACHE=0` to disable.

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
- [x] `get_insiders` / `get_insider_trades` — Section 16 (Form 3/4/5) insiders & trades
- [x] State filter on `get_recent_offerings` (industry isn't filterable — EDGAR omits SIC on these listings; screen via `get_form_d_details.industry_group`)
- [x] Reg A (Form 1-A) support in `get_recent_offerings`
- [x] `get_company_facts(cik)` — XBRL headline financials
- [x] `get_filing_text` — return a document's text for summarization
- [x] Published to PyPI (`mcpwright-edgar`) + the official MCP Registry (`io.github.mcpwright/edgar-mcp`)
- [ ] `get_form_a_details` — parse Reg A (Form 1-A) offering data
- [ ] Older-filing metadata (beyond the recent-submissions window)

## Privacy

edgar-mcp runs entirely **on your machine** and collects, stores, or transmits **no personal
data** — no accounts, no tracking, no telemetry. Its only outbound requests go to the **U.S.
SEC's EDGAR services** (`data.sec.gov`, `efts.sec.gov`, `www.sec.gov`) to fetch the public
filings you ask for; no API key is needed. One honest note: the SEC's fair-access policy asks
for a descriptive `User-Agent` with contact info (`EDGAR_MCP_USER_AGENT="your-app
you@example.com"`) — whatever you set there is sent to the SEC with each request, and nowhere
else. Responses are cached **in memory only**; nothing is persisted to disk.

Full policy: **https://mcpwright.com/privacy/**

## Questions & feedback

- **Questions, ideas, or "could it do X?"** → [**Discussions**](https://github.com/mcpwright/edgar-mcp/discussions)
- **Bugs & concrete feature requests** → [**Issues**](https://github.com/mcpwright/edgar-mcp/issues)

Contributions welcome — and if you build something with it, I'd love to hear about it.

---

Part of [**mcpwright**](https://github.com/mcpwright) · built by [Devender Gollapally](https://github.com/devender)
