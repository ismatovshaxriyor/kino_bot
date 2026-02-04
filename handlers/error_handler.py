import logging
from telegram.ext import ContextTypes
from utils import error_notificator

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xatoliklarni log qilish va adminga yuborish"""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Error Notificator orqali adminga yuborish
    await error_notificator.notify(context, context.error, update)
