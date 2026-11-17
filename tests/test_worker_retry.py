import asyncio

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

import utils.redis_manager as rm


class _Limiter:
    async def wait(self):
        pass


@pytest.fixture
def deliver(monkeypatch):
    """errors: har chaqiruvda ketma-ket ko'tariladigan xatolar (None = muvaffaqiyat)."""

    def run(errors):
        seq = list(errors)
        handled, sleeps, notified = [], [], []

        async def fake_handle(bot, msg):
            handled.append(1)
            err = seq.pop(0) if seq else None
            if err:
                raise err

        async def fake_notify(bot, text):
            notified.append(text)

        real_sleep = asyncio.sleep

        async def fake_sleep(delay, *a, **k):
            sleeps.append(delay)
            await real_sleep(0)

        monkeypatch.setattr(rm, "_handle_message", fake_handle)
        monkeypatch.setattr(rm, "_notify_admin", fake_notify)
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        msg = {"method": "send_message", "chat_id": 5, "content": "x", "args": {}}
        asyncio.run(rm._deliver(None, msg, _Limiter(), asyncio.Semaphore(1)))
        return len(handled), sleeps, notified

    return run


def test_network_error_backs_off_then_delivers(deliver):
    assert deliver([NetworkError("Bad Gateway")] * 3 + [None]) == (4, [1, 2, 4], [])


def test_persistent_network_error_is_dropped_after_max_retries(deliver):
    attempts, sleeps, notified = deliver([NetworkError("Bad Gateway")] * 20)
    assert attempts == 6 and sleeps == [1, 2, 4, 8, 16] and len(notified) == 1


def test_bad_request_is_not_retried_and_is_reported_once(deliver):
    attempts, sleeps, notified = deliver([BadRequest("Message is too long")])
    assert attempts == 1 and sleeps == [] and len(notified) == 1 and "too long" in notified[0]


def test_benign_bad_request_is_dropped_silently(deliver):
    assert deliver([BadRequest("Message to edit not found")]) == (1, [], [])


def test_forbidden_is_dropped_silently(deliver):
    assert deliver([Forbidden("Forbidden: bot was blocked by the user")]) == (1, [], [])


def test_retry_after_waits_then_delivers(deliver):
    assert deliver([RetryAfter(3), None]) == (2, [4], [])


def test_timeout_and_unexpected_error_are_retried(deliver):
    attempts, sleeps, _ = deliver([TimedOut("Timed out"), RuntimeError("kutilmagan"), None])
    assert attempts == 3 and sleeps == [1, 2]
