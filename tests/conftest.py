"""Shared test fixtures."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from edgar_mcp.edgar_client import EdgarClient


@pytest.fixture
async def ctx() -> AsyncIterator[SimpleNamespace]:
    """A minimal stand-in for the MCP Context the server injects.

    Tools read the EDGAR client via ``ctx.request_context.lifespan_context.edgar``;
    this provides exactly that (with a real client whose HTTP is intercepted by
    respx in the tests).
    """
    edgar = EdgarClient()
    try:
        yield SimpleNamespace(
            request_context=SimpleNamespace(
                lifespan_context=SimpleNamespace(edgar=edgar)
            )
        )
    finally:
        await edgar.aclose()
