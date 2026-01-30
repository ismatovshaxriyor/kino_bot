from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils import admin_required
from database import User
from .managers_handler import get_managers_btns

@admin_required
async def general_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')

    if state == 'WAITING_GENRE_NAME':
        genre = update.message.text
        context.user_data['new_genre'] = genre.capitalize()
        context.user_data['state'] = "WAITING_FOR_CONFIRM_GENRE"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_genre_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_genre_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi janr: {genre.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_COUNTRY_NAME":
        country = update.message.text
        context.user_data['new_country'] = country.capitalize()
        context.user_data['state'] = "WAITING_FOR_CONFIRM_COUNTRY"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_country_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_country_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi davlat: {country.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_MANAGER_ID":
        keyboard, i = await get_managers_btns()

        try:
            manager_id = int(update.message.text)
            context.user_data['new_manager'] = manager_id
        except:
            await update.message.reply_text("Noto'g'ri formatdagi id\n\nId faqat raqamlardan iborat bo'lishi kerak", reply_markup=keyboard)
            return

        new_manager = await User.get_or_none(telegram_id=manager_id)

        if new_manager is None:
            await update.message.reply_text("Bu Id da foydalanuvchi topilmadi\n\nIltimos botdan ro'yxatdan o'tgan foydalanuvchining Id sini yuboring.", reply_markup=keyboard)
            return

        context.user_data['state'] = "WAITING_FOR_CONFIRM_MANAGER"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_manager_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_manager_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi Manager: {new_manager.first_name} {new_manager.last_name if new_manager.last_name else None}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)