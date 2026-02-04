from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import Genre
from utils import error_notificator, admin_required


async def get_genre_btns():
    genres = await Genre.all()
    genre_btns = []

    if genres:
        btns = []
        for i, genre in enumerate(genres):
            btn = InlineKeyboardButton(text=f"🎭 {genre.name}", callback_data=f"genre_{genre.genre_id}")
            btns.append(btn)
            if i % 2 == 1:
                genre_btns.append(btns)
                btns = []

        if btns:
            genre_btns.append(btns)

        genre_btns += [[InlineKeyboardButton('➕ Janr qo\'shish', callback_data='genre_add')]]
        keyboard = InlineKeyboardMarkup(genre_btns)

    else:
        genre_btns += [[InlineKeyboardButton('➕ Janr qo\'shish', callback_data='genre_add')]]
        keyboard = InlineKeyboardMarkup(genre_btns)
        i = 1

    return [keyboard, i]

@admin_required
async def get_genres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        genre_btns, i = await get_genre_btns()
        if i == 1:
            await update.message.reply_text("📭 Janrlar topilmadi.", reply_markup=genre_btns)
        else:
            await update.message.reply_text("🎭 <b>Janrlar ro'yxati:</b>", reply_markup=genre_btns, parse_mode="HTML")
    except Exception as e:
        await error_notificator.notify(context, e, update)






