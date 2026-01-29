from telegram import Update
from telegram.ext import ContextTypes

from utils import admin_required, admin_keyboard

@admin_required
async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔐 <b>Admin Panel</b>\n\nKerakli amalni tanlang:", reply_markup=admin_keyboard, parse_mode="HTML")