from itertools import count
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils import admin_required


@admin_required
async def general_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')

    if state == 'WAITING_GENRE_NAME':
        genre = update.message.text
        context.user_data['new_genre'] = genre.capitalize()
        context.user_data['add_genre_state'] = "WAITING_FOR_CONFIRM"

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
        context.user_data['add_country_state'] = "WAITING_FOR_CONFIRM"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_country_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_country_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi davlat: {country.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)