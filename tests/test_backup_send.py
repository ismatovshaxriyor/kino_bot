import asyncio
from pathlib import Path

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

import admins.backup_handler as bh


class _Bot:
    def __init__(self, seq):
        self.seq, self.calls, self.kw = list(seq), 0, None

    async def send_document(self, **kw):
        self.calls += 1
        self.kw = kw
        err = self.seq.pop(0) if self.seq else None
        if err:
            raise err


@pytest.fixture
def send(monkeypatch, tmp_path):
    path = Path(tmp_path) / "b.sql.gz"
    path.write_bytes(b"x" * 10)

    def run(errors):
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(bh.asyncio, "sleep", fake_sleep)
        bot = _Bot(errors)
        ok = asyncio.run(bh._send_document_with_retry(bot, 1, path, "cap"))
        return ok, bot, sleeps

    return run


def test_sent_on_first_attempt_with_long_upload_timeouts(send):
    ok, bot, sleeps = send([])
    assert ok and bot.calls == 1 and sleeps == []
    assert bot.kw["write_timeout"] == 180 and bot.kw["read_timeout"] == 180


def test_transient_errors_are_retried(send):
    ok, bot, sleeps = send([TimedOut(), NetworkError("Bad Gateway")])
    assert ok and bot.calls == 3 and sleeps == [5, 10]


def test_gives_up_after_three_attempts(send):
    ok, bot, sleeps = send([TimedOut()] * 5)
    assert not ok and bot.calls == 3 and sleeps == [5, 10]


@pytest.mark.parametrize("err", [Forbidden("blocked"), BadRequest("chat not found")])
def test_permanent_errors_are_not_retried(send, err):
    ok, bot, sleeps = send([err])
    assert not ok and bot.calls == 1 and sleeps == []


def test_retry_after_is_respected(send):
    ok, bot, sleeps = send([RetryAfter(2)])
    assert ok and bot.calls == 2 and sleeps == [3.0]
