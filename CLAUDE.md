# edgar-mcp — working agreement

`edgar-mcp` is the **reference server** of the **mcpwright** suite (`github.com/mcpwright`):
polished, public MCP servers that bring a real-world data source into any agent. **This
repo sets the bar** the rest of the suite copies.

> The full written rubric is
> `~/my-notes/professional-self-improvement/mcpwright/mcp-standards.md`.
> To scaffold a new suite server from this one, use the `new-mcpwright-server` skill.

## Non-negotiable policies

- **Lots of unit tests.** Every tool and every parser/formatter has tests, with **all
  external I/O mocked** (`respx`). A new tool ships with its tests **in the same PR**.
  `pytest -v` must be green before a PR opens.
- **Use the latest patterns.** Official `mcp` Python SDK via `mcp.server.fastmcp` (NOT the
  standalone `fastmcp` package). Python 3.12+ idioms, `from __future__ import annotations`,
  pydantic v2 models with a `Field(description=...)` on **every** field, `uv` for deps +
  build, async `httpx`. Tools return typed pydantic models (structured output) and are
  annotated `readOnlyHint=True`.
- **PR per change, CI-gated.** Standard flow:
  **feature branch → code → code-review subagent → fold in findings → PR → CI green → squash-merge.**
  - *Code-review subagent:* before opening the PR, review the diff (`git diff main...HEAD`) with
    the **`code-reviewer`** subagent (`.claude/agents/code-reviewer.md`) — or just run
    **`/review-pr`**. It runs in a **fresh context with no memory of the coding session** and
    returns severity-tagged findings (**Blocker / High / Medium / Low**). Address Blocker/High
    (and add a regression test for any real bug) before the PR opens.
  - *Merge:* the `Code Quality & Tests` check green and branch up to date → squash-merge with a
    `(#N)` suffix. `main` is branch-protected; **no direct pushes**.
  - *Commits:* imperative subject + a short body, ending with the dual trailer
    (`Co-authored-by: Devender …` + `Co-authored-by: Claude …`).
- **Green locally before pushing:**
  ```bash
  uv run ruff check src/ && uv run ruff format --check src/ && uv run mypy && uv run pytest -v
  ```
  `uv run pre-commit run --all-files` mirrors CI (ruff, ruff-format, mypy, detect-secrets, hygiene).

## Layout

```
src/edgar_mcp/
  __init__.py        # from .server import main
  edgar_client.py    # async httpx client: User-Agent, throttle, retry/backoff
  cache.py           # in-memory TTL + byte-budgeted LRU cache
  models.py          # pydantic tool RETURN types (Field(description=...) on every field)
  formatting.py      # raw SEC data → model helpers
  <parsers>.py       # formc / formd / forms345 / xbrl / htmltext / xmlutil / issuers
  server.py          # FastMCP app: instructions + lifespan + @mcp.tool(readOnlyHint)
tests/               # respx-mocked SEC responses; one file per module/tool group
```
Errors users/agents see are actionable `ValueError`s with a next step. SEC etiquette
(descriptive `User-Agent`, ~10 req/s throttle, retry) lives in `edgar_client.py`.

## Publishing & the website

- Publish (PyPI `mcpwright-edgar` + the MCP Registry `io.github.mcpwright/edgar-mcp`):
  use the **`publish-mcp-server`** skill.
- The server's page is **mcpwright.com/edgar**, in the `mcpwright.github.io` repo, using the
  suite typography (**Fraunces** serif + **JetBrains Mono**): use the
  **`add-mcpwright-site-page`** skill.
