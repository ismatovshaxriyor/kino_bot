from telegram import Update
from telegram.error import BadRequest, NetworkError
from telegram.ext import ContextTypes
from datetime import datetime
import traceback
import logging
import html

from utils import ADMIN_ID

logger = logging.getLogger(__name__)

# Telegram yoki tarmoq tomonidagi vaqtinchalik uzilishlar (502/504 "Bad Gateway", timeout...): o'zi tiklanadi,
# adminga xabar yuborish ham o'sha uzilishga tushib, xatolarni yanada ko'paytiradi.
TRANSIENT_NETWORK_MARKERS = (
    "remoteprotocolerror",
    "server disconnected without sending a response",
    "readerror",
    "timed out",
    "timeout",
    "connection reset",
    "temporarily unavailable",
    "service unavailable",
    "gateway",  # "Bad Gateway", "Gateway Time-out"
)

TELEGRAM_TEXT_LIMIT = 4096


def is_transient_network_error(error: Exception) -> bool:
    # BadRequest ham NetworkError'ning avlodi, lekin u doimiy xato (so'rovning o'zi noto'g'ri)
    if not isinstance(error, NetworkError) or isinstance(error, BadRequest):
        return False
    text = str(error).lower()
    return any(marker in text for marker in TRANSIENT_NETWORK_MARKERS)


def _fit_traceback(tb: str, budget: int) -> str:
    """HTML-escape qilingandan KEYIN ham budget belgidan oshmaydigan traceback (oxiri saqlanadi: xato shu yerda)."""
    if budget <= 0:
        return ""
    escaped = html.escape(tb)
    while len(escaped) > budget and tb:
        tb = tb[max(len(tb) // 10, 1):]
        escaped = "…\n" + html.escape(tb)
    return escaped


class ErrorNotificator:
    def __init__(self, admin_ids: list[int]):
        self.admin_ids = admin_ids

    async def notify(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        error: Exception,
        update: Update = None
    ):
        if self._should_skip_notification(error):
            logger.warning("Skipped noisy error notification: %s", error)
            return

        user_info = "N/A"
        chat_info = "N/A"

        if isinstance(update, Update):
            if update.effective_user:
                u = update.effective_user
                user_info = f"{u.first_name} (@{u.username or 'None'})"

            if update.effective_chat:
                chat_info = f"{update.effective_chat.id}"

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        if not tb.strip():
            tb = "Traceback mavjud emas."

        head = f"""
🚨 <b>XATOLIK!</b>

⏰ {datetime.now().strftime('%H:%M:%S')}

❌ <code>{html.escape(type(error).__name__)}: {html.escape(str(error)[:500])}</code>

👤 User: <code>{html.escape(user_info)}</code>
💬 Chat Id: <code>{chat_info}</code>

<pre>"""
        tail = "</pre>\n"
        # Telegram 4096 belgidan uzun xabarni qabul qilmaydi ("Message is too long")
        message = head + _fit_traceback(tb, TELEGRAM_TEXT_LIMIT - len(head) - len(tail) - 16) + tail

        for admin_id in self.admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Admin {admin_id} ga yuborib bo'lmadi: {e}")

    @staticmethod
    def _should_skip_notification(error: Exception) -> bool:
        if is_transient_network_error(error):
            return True

        if isinstance(error, BadRequest):
            text = str(error).lower()
            if "query is too old" in text or "query id is invalid" in text:
                return True

        return False


error_notificator = ErrorNotificator([ADMIN_ID])
