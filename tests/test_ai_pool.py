import asyncio
import importlib
import threading
import time

import pytest

# `services/__init__` star-import qilgani uchun `services.ai_assistant` atributi MODUL emas, namuna — importlib bilan olamiz
ai = importlib.import_module("services.ai_assistant")


def test_rate_limit_spaces_concurrent_calls():
    """Bir vaqtda kelgan so'rovlar ham >= interval oralig'ida boshlanishi kerak (avval poyga bor edi)."""
    a = ai.MovieAIAssistant("test-key")
    a._min_request_interval = 0.2
    starts = []

    def call():
        a._wait_for_rate_limit()
        starts.append(time.time())

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    starts.sort()
    gaps = [b - a_ for a_, b in zip(starts, starts[1:])]
    assert all(g >= 0.18 for g in gaps), gaps


def test_ai_work_runs_in_dedicated_pool_not_default_executor():
    names = []

    def work():
        names.append(threading.current_thread().name)
        return 42

    assert asyncio.run(ai.run_in_ai_pool(work)) == 42
    assert names[0].startswith("ai")


def test_pool_rejects_when_queue_is_full(monkeypatch):
    monkeypatch.setattr(ai, "AI_MAX_PENDING", 2)

    async def scenario():
        gate = threading.Event()
        tasks = [asyncio.create_task(ai.run_in_ai_pool(gate.wait, 5)) for _ in range(2)]
        await asyncio.sleep(0.05)
        with pytest.raises(ai.AIBusyError):
            await ai.run_in_ai_pool(lambda: None)
        gate.set()
        await asyncio.gather(*tasks)
        # navbat bo'shagach yana qabul qiladi
        assert await ai.run_in_ai_pool(lambda: "ok") == "ok"

    asyncio.run(scenario())
