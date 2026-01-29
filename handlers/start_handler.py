from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from database import User
from utils import error_notificator



async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.effective_chat.first_name
    last_name = update.effective_chat.last_name
    username = update.effective_chat.username
    telegram_id = update.effective_chat.id

    try:
        user, created = await User.get_or_create(telegram_id=telegram_id, defaults={
            'first_name': first_name,
            'last_name': last_name if last_name else None,
            'username': username if username else None
        })

        if created:
            await update.message.reply_text(f'Salom {update.effective_chat.first_name}', reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text(f'Salom {update.effective_chat.first_name}, Botga qaytganingizdan xursandmiz', reply_markup=ReplyKeyboardRemove())

    except Exception as e:
        await error_notificator.notify(context, e, update)
        await update.message.reply_text("Botda xatolik, iltimos qayta /start bosing", reply_markup=ReplyKeyboardRemove())

