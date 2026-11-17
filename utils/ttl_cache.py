"""Kichik asinxron TTL kesh: bir xil kalitga bir vaqtda kelgan so'rovlar BITTA hisoblashga birlashadi.

Ko'p foydalanuvchi bir xil og'ir so'rovni (masalan, "Top kinolar" yoki mashhur qidiruv) bir vaqtda bossa,
DB har safar qayta hisoblamaydi. Xato (exception) keshga yozilmaydi.
"""
import asyncio
import time
from typing import Any, Callable, Hashable


class AsyncTTLCache:
    def __init__(self, ttl: float, maxsize: int = 500):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: dict[Hashable, tuple[float, Any]] = {}
        self._inflight: dict[Hashable, asyncio.Future] = {}

    async def get_or_compute(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        hit = self._data.get(key)
        if hit is not None and hit[0] > time.monotonic():
            return hit[1]

        task = self._inflight.get(key)
        if task is None:

            async def _compute():
                return await factory()  # factory korutina yoki QuerySet (awaitable) bo'lishi mumkin

            task = asyncio.ensure_future(_compute())
            self._inflight[key] = task
            task.add_done_callback(lambda _t, k=key: self._inflight.pop(k, None))
        # shield: bitta kutuvchi bekor qilinsa (masalan, foydalanuvchi xabarni o'chirsa), boshqalar zarar ko'rmaydi
        value = await asyncio.shield(task)

        self._store(key, value)
        return value

    def _store(self, key: Hashable, value: Any) -> None:
        now = time.monotonic()
        self._data[key] = (now + self.ttl, value)
        if len(self._data) > self.maxsize:
            for k in [k for k, (until, _) in self._data.items() if until <= now]:
                del self._data[k]
            while len(self._data) > self.maxsize:
                del self._data[next(iter(self._data))]  # eng eskisi

    def clear(self) -> None:
        self._data.clear()
