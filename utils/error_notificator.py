from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import traceback
import logging
import html

from utils import ADMIN_ID

logger = logging.getLogger(__name__)

class ErrorNotificator:
    def __init__(self, admin_ids: list[int]):
        self.admin_ids = admin_ids

    async def notify(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        error: Exception,
        update: Update = None
    ):
        user_info = "N/A"
        chat_info = "N/A"

        if update:
            if update.effective_user:
                u = update.effective_user
                user_info = f"{u.first_name} (@{u.username or 'None'})"

            if update.effective_chat:
                chat_info = f"{update.effective_chat.id}"

        tb = traceback.format_exc()[:3000]
        tb_escaped = html.escape(tb)

        message = f"""
🚨 <b>XATOLIK!</b>

⏰ {datetime.now().strftime('%H:%M:%S')}

❌ <code>{html.escape(type(error).__name__)}: {html.escape(str(error))}</code>

👤 User: <code>{user_info}</code>
💬 Chat Id: <code>{chat_info}</code>

<pre>{tb_escaped}</pre>
"""

        for admin_id in self.admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Admin {admin_id} ga yuborib bo'lmadi: {e}")


error_notificator = ErrorNotificator([ADMIN_ID])
