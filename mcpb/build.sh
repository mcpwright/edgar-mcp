#!/usr/bin/env bash
# Build the edgar-mcp MCPB desktop-extension bundle.
#
# Produces dist/mcpwright-edgar-<version>.mcpb — a `uv`-type bundle: it ships
# the source + pyproject.toml (deps declared there, NO vendored libs), and the
# host's uv installs the correct-platform deps (incl. pydantic-core) at install
# time. Recipe proven on census-mcp.
#
# Requires: the `mcpb` CLI (`npm i -g @anthropic-ai/mcpb`).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
# Read the manifest version via node (already required for the `mcpb` CLI — no extra dep).
version="$(node -p "require('$here/manifest.json').version")"
# Guard the lockstep: manifest version must match pyproject.
py_version="$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/pyproject.toml" | head -1)"
if [ "$version" != "$py_version" ]; then
  echo "version mismatch: manifest.json=$version pyproject.toml=$py_version" >&2
  exit 1
fi
out="$root/dist/mcpwright-edgar-$version.mcpb"

stage="$(mktemp -d)/edgar"
mkdir -p "$stage"
# Bundle contents: manifest + icon, plus the project (source + pyproject so uv
# can build/install it) and the files pyproject references (README, LICENSE).
cp "$here/manifest.json" "$here/icon.png" "$stage/"
cp "$root/pyproject.toml" "$root/README.md" "$root/LICENSE" "$stage/"
[ -f "$root/uv.lock" ] && cp "$root/uv.lock" "$stage/"
cp -R "$root/src" "$stage/"
# Strip bytecode caches that `cp -R` may have carried over.
find "$stage" -name '__pycache__' -type d -prune -exec rm -rf {} +
# Never pack a venv, caches, tests, or vcs cruft (the CLI honors .mcpbignore).
printf '%s\n' '.venv/' '__pycache__/' '*.pyc' '.git/' 'dist/' 'tests/' '.mypy_cache/' '.pytest_cache/' '.ruff_cache/' > "$stage/.mcpbignore"

mkdir -p "$root/dist"
mcpb validate "$stage/manifest.json"
mcpb pack "$stage" "$out"
echo
mcpb info "$out"
rm -rf "$(dirname "$stage")"
echo
echo "Built: $out"
