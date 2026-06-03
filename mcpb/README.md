# edgar-mcp — MCPB desktop-extension bundle

This directory builds the **[MCPB](https://github.com/modelcontextprotocol/mcpb)**
(`.mcpb`) bundle for one-click install in Claude Desktop / Claude Code, and for
submission to Anthropic's Connectors Directory. The recipe was proven on
[census-mcp](https://github.com/mcpwright/census-mcp) (verified installing and
working in Claude Desktop).

## Why `type: "uv"` (not a vendored bundle)

edgar depends on `pydantic`, whose `pydantic-core` is a **compiled, platform-specific**
wheel — MCPB explicitly *"cannot portably bundle compiled dependencies."* So this is a
**`uv`-type** bundle: it ships the **source + `pyproject.toml`** (no vendored `server/lib`),
and the host's `uv` installs the correct-platform dependencies at install time. That keeps it
cross-platform (`darwin` / `win32` / `linux`).

No API key. The one `user_config` field is the **SEC User-Agent** (the SEC's fair-access
policy asks for contact info); it has a **default**, because `edgar_client.py` reads
`EDGAR_MCP_USER_AGENT` with `os.environ.get(..., default)` semantics — an empty injected env
var would override the package default with an empty string.

> Note: MCPB's `uv` runtime is officially **experimental**
> ([mcpb#84](https://github.com/modelcontextprotocol/mcpb/issues/84)), but it verified working
> in Claude Desktop on 2026-06-02 with census-mcp's identical setup.

## Build

Requires the `mcpb` CLI: `npm i -g @anthropic-ai/mcpb`.

```bash
./build.sh        # validates manifest.json, stages source + pyproject, packs the .mcpb
```

Output: `../dist/mcpwright-edgar-<version>.mcpb` (gitignored). The build stages only the files
the bundle needs (`manifest.json`, `icon.png`, `pyproject.toml`, `README.md`, `LICENSE`,
`uv.lock`, `src/`) and strips bytecode caches.

## Install (manual, before Directory listing)

In Claude Desktop: **Settings → Extensions → Advanced settings → Install extension…** and pick
the `.mcpb`. Optionally set your SEC User-Agent contact string when prompted; then ask about a
company or recent raises.

## Versioning

`manifest.json` `version` tracks the package version (keep it in lockstep with `pyproject.toml`
and `server.json`). Bump all three together on release.
