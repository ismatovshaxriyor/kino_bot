from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Genre
from admins import get_genre_btns


async def genre_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_sp = query.data.split('_')

    if data_sp[1] == 'add':
        await query.delete_message()
        context.user_data['state'] = "WAITING_GENRE_NAME"

        await update.effective_message.reply_text("Yangi janrni kiriting:")

    elif data_sp[1].isdigit():
        genre_id = data_sp[1]
        genre = await Genre.get(genre_id=genre_id)

        btns = [
            [
                InlineKeyboardButton("O'chirish", callback_data=f"genre_delete_{genre_id}"),
                InlineKeyboardButton("Ortga qaytish", callback_data='genre_back')
            ]
        ]
        keyboard = InlineKeyboardMarkup(btns)

        await query.edit_message_text(f"Janr: {genre.name}\n\n harakatni tanlang:", reply_markup=keyboard)

    elif data_sp[1] == 'delete':
        genre_id = data_sp[2]

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data=f'confirm_genre_delete_{genre_id}'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_genre_delete')
            ]
        ]

        genre = await Genre.get(genre_id=genre_id)
        keyboard = InlineKeyboardMarkup(confirm_btns)
        await query.edit_message_text(f"Janr: {genre.name}\n\nO'chirishni tasdiqlang.", reply_markup=keyboard)

    elif data_sp[1] == 'back':
        keyboard, i = await get_genre_btns()

        if i == 1:
            await query.edit_message_text("Janrlar topilmadi.", reply_markup=keyboard)
        else:
            await query.edit_message_text('Janrlar:', reply_markup=keyboard)



