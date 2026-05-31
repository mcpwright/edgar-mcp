import httpx
import pytest
import respx

from edgar_mcp.cache import TTLCache
from edgar_mcp.edgar_client import EdgarClient


@pytest.mark.asyncio
async def test_cache_hit_and_miss() -> None:
    c = TTLCache()
    assert await c.get("k") == (False, None)
    await c.set("k", 123, ttl=60, size=8)
    assert await c.get("k") == (True, 123)


@pytest.mark.asyncio
async def test_cache_expiry() -> None:
    c = TTLCache()
    await c.set("k", "v", ttl=-1, size=1)  # already expired
    hit, _ = await c.get("k")
    assert hit is False


@pytest.mark.asyncio
async def test_cache_byte_budget_eviction() -> None:
    c = TTLCache(max_bytes=100)
    await c.set("a", "x", ttl=60, size=60)
    await c.set("b", "y", ttl=60, size=60)  # 120 > 100 -> evict oldest ("a")
    assert (await c.get("a"))[0] is False
    assert (await c.get("b"))[0] is True


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
