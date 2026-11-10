"""Oddiy tezlik chegaralagich: so'rovlar boshlanishini kamida 1/rate soniya oraliq bilan joylashtiradi.

asyncio'da xavfsiz (await'siz hisoblanadi). Telegram umumiy limiti ~30 xabar/s — broadcast va
worker shu limitdan oshib ketmasligi uchun ishlatiladi.
"""

import asyncio


class RateLimiter:
    def __init__(self, rate: float):
        self._interval = 1.0 / rate
        self._next = 0.0

    async def wait(self) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        start = max(now, self._next)
        self._next = start + self._interval
        if start > now:
            await asyncio.sleep(start - now)
