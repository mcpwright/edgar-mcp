"""edgar's response-caching behavior. The TTLCache itself is tested in
mcpwright-core; here we only check that EdgarClient caches (and can opt out)."""

import httpx
import pytest
import respx

from edgar_mcp.edgar_client import EdgarClient


@respx.mock
@pytest.mark.asyncio
async def test_client_caches_repeat_requests() -> None:
    url = "https://www.sec.gov/Archives/edgar/data/320193/x/index.json"
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"ok": True}))
    async with EdgarClient() as client:
        first = await client.get_json(url)
        second = await client.get_json(url)
    assert first == second == {"ok": True}
    assert route.call_count == 1  # second served from cache


@respx.mock
@pytest.mark.asyncio
async def test_client_cache_can_be_disabled() -> None:
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    route = respx.get(url).mock(return_value=httpx.Response(200, json={"n": 1}))
    async with EdgarClient(cache=False) as client:
        await client.get_json(url)
        await client.get_json(url)
    assert route.call_count == 2  # no caching -> two real requests
