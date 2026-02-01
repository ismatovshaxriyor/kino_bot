from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from utils import admin_required, admin_btns
from utils.settings import ADMIN_ID, MANAGER_ID

@admin_required
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id == ADMIN_ID or user_id == MANAGER_ID:
        admin_btns.insert(-1, [KeyboardButton("👤 Managerlar")])

    admin_keyboard = ReplyKeyboardMarkup(
        admin_btns,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    await update.message.reply_text("🔐 <b>Admin Panel</b>\n\nKerakli amalni tanlang:", reply_markup=admin_keyboard, parse_mode="HTML")