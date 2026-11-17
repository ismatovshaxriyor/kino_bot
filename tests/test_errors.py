import asyncio
import re
import sys

from telegram import Update
from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut

from utils.error_notificator import ErrorNotificator, TELEGRAM_TEXT_LIMIT, is_transient_network_error


def test_transient_errors_are_detected():
    for err in (NetworkError("Bad Gateway"), NetworkError("Gateway Time-out"), NetworkError("Service Unavailable"),
                TimedOut(), NetworkError("httpx.ReadError: ")):
        assert is_transient_network_error(err), err


def test_permanent_errors_are_not_transient():
    assert not is_transient_network_error(NetworkError("something else entirely"))
    assert not is_transient_network_error(BadRequest("Message is too long"))
    assert not is_transient_network_error(BadRequest("Bad Gateway in text"))  # BadRequest doimiy xato
    assert not is_transient_network_error(Forbidden("blocked"))
    assert not is_transient_network_error(ValueError("Bad Gateway"))


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


def _notify(error, update=None):
    ctx = _Ctx()
    asyncio.run(ErrorNotificator([111]).notify(ctx, error, update))
    return ctx.bot.sent


def test_error_handler_skips_transient_but_reports_real_errors():
    import importlib

    eh = importlib.import_module("handlers.error_handler")  # paket star-import qilgani uchun `import ... as` ishonchsiz

    calls = []

    class N:
        async def notify(self, ctx, err, upd):
            calls.append(err)

    class C:
        def __init__(self, e):
            self.error = e

    old = eh.error_notificator
    eh.error_notificator = N()
    try:
        asyncio.run(eh.error_handler(None, C(NetworkError("Bad Gateway"))))
        assert calls == []
        asyncio.run(eh.error_handler(None, C(ValueError("haqiqiy xato"))))
        assert len(calls) == 1
    finally:
        eh.error_notificator = old


def test_notification_fits_telegram_limit_after_html_escaping():
    def deep(i):
        if i == 0:
            raise RuntimeError("<" * 400 + "&" * 400)
        deep(i - 1)

    try:
        deep(60)
    except Exception as e:  # noqa: BLE001
        err = e
    text = _notify(err)[0]["text"]
    assert len(text) <= TELEGRAM_TEXT_LIMIT
    pre = text[text.index("<pre>") + 5:text.rindex("</pre>")]
    assert re.findall(r"&(?!(?:lt|gt|amp|quot|#x27);)", pre) == []  # yarim qolgan entity yo'q
    assert text.rstrip().endswith("</pre>") and text.count("<pre>") == 1


def test_short_error_is_kept_whole_and_user_info_is_escaped():
    try:
        raise KeyError("x")
    except KeyError as e:
        sent = _notify(e)
    assert "KeyError" in sent[0]["text"] and "Traceback" in sent[0]["text"]

    class U:
        first_name = "<b>Ali</b>"
        username = "x&y"

    class Upd(Update):
        def __init__(self):
            pass
        effective_user = U()
        effective_chat = None

    sent = _notify(ValueError("v"), Upd())
    assert "&lt;b&gt;Ali&lt;/b&gt;" in sent[0]["text"]


def test_transient_error_is_not_sent_to_admin():
    assert _notify(NetworkError("Bad Gateway")) == []
