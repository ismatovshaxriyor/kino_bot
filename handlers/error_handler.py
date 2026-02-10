import logging
from telegram import Update
from telegram.error import BadRequest, NetworkError
from telegram.ext import ContextTypes

from utils import error_notificator

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def _is_transient_network_error(error: Exception) -> bool:
    if not isinstance(error, NetworkError):
        return False

    text = str(error).lower()
    transient_markers = (
        "remoteprotocolerror",
        "server disconnected without sending a response",
        "readerror",
        "timed out",
        "timeout",
        "connection reset",
    )
    return any(marker in text for marker in transient_markers)


def _is_expired_query_error(error: Exception) -> bool:
    if not isinstance(error, BadRequest):
        return False
    text = str(error).lower()
    return "query is too old" in text or "query id is invalid" in text


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xatoliklarni log qilish va adminga yuborish"""
    err = context.error
    if err is None:
        return

    # Telegram callback/inline queries expire quickly; this is expected on delayed clicks.
    if _is_expired_query_error(err):
        logger.info("Ignored expired callback/inline query error: %s", err)
        return

    # Transport-level errors happen intermittently; avoid spamming admin for each one.
    if _is_transient_network_error(err):
        logger.warning("Transient network error: %s", err)
        return

    logger.error("Exception while handling an update:", exc_info=err)
    # Error Notificator orqali adminga yuborish
    await error_notificator.notify(context, err, update if isinstance(update, Update) else None)
