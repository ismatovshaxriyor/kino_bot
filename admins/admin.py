from telegram import Update
from telegram.ext import ContextTypes

from utils import admin_required, user_keyboard
from utils.admin_btns import get_admin_keyboard


@admin_required
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_keyboard = get_admin_keyboard(user_id)

    await update.message.reply_text("🔐 <b>Admin Panel</b>\n\nKerakli amalni tanlang:", reply_markup=admin_keyboard, parse_mode="HTML")


@admin_required
async def admin_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Oddiy menyuga qaytdingiz.",
        reply_markup=user_keyboard
    )
