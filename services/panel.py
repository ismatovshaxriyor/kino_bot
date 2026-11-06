"""/panel — admin uchun server holati paneli (Telegram Mini App) tugmasi.

Panel alohida `webapp` konteynerida ishlaydi; ngrok havolasini u Redis'ga (`webapp:url`) yozib turadi.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from utils.redis_manager import r
from utils.settings import ADMIN_ID, MANAGER_ID

URL_KEY = "webapp:url"  # webapp/ngrok_link.py yozadi


async def panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/panel — faqat ADMIN_ID/MANAGER_ID."""
    user = update.effective_user
    if not user or user.id not in (ADMIN_ID, MANAGER_ID):
        return

    url = await r.get(URL_KEY)
    if isinstance(url, bytes):
        url = url.decode()
    if not url:
        text = ("📊 Panel hozir ishlamayapti: ngrok havolasi topilmadi.\n"
                "Serverda <code>make logs</code> bilan <code>my_bot_ngrok</code> va <code>my_bot_webapp</code> ni tekshiring.")
        markup = None
    else:
        text = "📊 <b>Server holati</b> — real vaqtdagi grafiklar."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Serverni ochish", web_app=WebAppInfo(url))]])
    # direct=True: Redis navbati yiqilgan bo'lsa ham panel tugmasi yetib boradi
    await context.bot.send_message(chat_id=user.id, text=text, parse_mode="HTML", reply_markup=markup, direct=True)
