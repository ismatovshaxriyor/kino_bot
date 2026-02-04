from telegram import Update
from telegram.ext import ContextTypes
from datetime import date

from services import ai_assistant
from database import User
from utils import error_notificator

DAILY_LIMIT = 3

async def can_use_ai(user: User) -> bool:
    today = date.today()

    if user.ai_usage_date != today:
        user.ai_usage = 0
        user.ai_usage_date = today
        await user.save()

    return user.ai_usage < DAILY_LIMIT

async def increase_ai_usage(user: User):
    user.ai_usage += 1
    await user.save()

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id
    user = await User.get(telegram_id=update.effective_user.id)

    if not await can_use_ai(user):
        await update.message.reply_text(
            "❌ Sizning bugungi AI'dan foydalanish limitingiz tugadi.\n"
            "⏳ Ertaga yana urinib ko'ring."
        )
        return

    await update.message.chat.send_action(action="typing")

    try:
        response = ai_assistant.get_movie_recommendation(user_message)

        try:
            await context.bot.send_message(chat_id, response, parse_mode="Markdown")
            await increase_ai_usage(user)
        except Exception as e:
            await error_notificator.notify(context, e, update)
            await context.bot.send_message(chat_id, response)

    except Exception as e:
        await update.message.reply_text(
            f"❌ Javob berishda xatolik yuz berdi: {str(e)}\n\n"
            "Iltimos keyinroq urinib ko'ring!"
        )
