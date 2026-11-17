import asyncio

import pytest

from utils import ttl_cache
from utils.ttl_cache import AsyncTTLCache


def run(coro):
    return asyncio.run(coro)


def test_second_call_within_ttl_is_served_from_cache():
    calls = []
    cache = AsyncTTLCache(ttl=60)

    async def factory():
        calls.append(1)
        return "v"

    async def scenario():
        return [await cache.get_or_compute("k", factory) for _ in range(3)]

    assert run(scenario()) == ["v", "v", "v"] and len(calls) == 1


def test_recomputed_after_ttl(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ttl_cache.time, "monotonic", lambda: now[0])
    calls = []
    cache = AsyncTTLCache(ttl=10)

    async def factory():
        calls.append(1)
        return len(calls)

    async def scenario():
        a = await cache.get_or_compute("k", factory)
        now[0] += 11
        b = await cache.get_or_compute("k", factory)
        return a, b

    assert run(scenario()) == (1, 2)


def test_concurrent_callers_share_one_computation():
    calls = []
    cache = AsyncTTLCache(ttl=60)

    async def factory():
        calls.append(1)
        await asyncio.sleep(0.05)
        return "v"

    async def scenario():
        return await asyncio.gather(*[cache.get_or_compute("k", factory) for _ in range(50)])

    assert run(scenario()) == ["v"] * 50 and len(calls) == 1


def test_errors_are_not_cached():
    calls = []
    cache = AsyncTTLCache(ttl=60)

    async def factory():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db uzildi")
        return "ok"

    async def scenario():
        with pytest.raises(RuntimeError):
            await cache.get_or_compute("k", factory)
        return await cache.get_or_compute("k", factory)

    assert run(scenario()) == "ok" and len(calls) == 2


def test_cancelled_waiter_does_not_break_others():
    cache = AsyncTTLCache(ttl=60)

    async def factory():
        await asyncio.sleep(0.1)
        return "v"

    async def scenario():
        t1 = asyncio.create_task(cache.get_or_compute("k", factory))
        t2 = asyncio.create_task(cache.get_or_compute("k", factory))
        await asyncio.sleep(0.01)
        t1.cancel()
        return await t2

    assert run(scenario()) == "v"


def test_maxsize_evicts_oldest_and_accepts_queryset_like_awaitables():
    cache = AsyncTTLCache(ttl=60, maxsize=2)

    class Awaitable:  # Tortoise QuerySet kabi: korutina emas, lekin await qilinadi
        def __await__(self):
            async def inner():
                return "qs"
            return inner().__await__()

    async def scenario():
        for k in ("a", "b", "c"):
            await cache.get_or_compute(k, Awaitable)
        return list(cache._data)

    assert run(scenario()) == ["b", "c"]
