from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils import admin_required, admin_btns, user_keyboard
from utils.settings import ADMIN_ID, MANAGER_ID


@admin_required
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    keyboard_rows = [row[:] for row in admin_btns]
    if user_id in (ADMIN_ID, MANAGER_ID):
        keyboard_rows.insert(3, [KeyboardButton("👤 Managerlar")])

    admin_keyboard = ReplyKeyboardMarkup(
        keyboard_rows,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    await update.message.reply_text("🔐 <b>Admin Panel</b>\n\nKerakli amalni tanlang:", reply_markup=admin_keyboard, parse_mode="HTML")


@admin_required
async def admin_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Oddiy menyuga qaytdingiz.",
        reply_markup=user_keyboard
    )
