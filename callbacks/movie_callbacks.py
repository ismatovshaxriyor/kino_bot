from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Movie
from admins import get_movies_page, get_movies_keyboard


async def movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, action, value = query.data.split(":")

    if action == "page":
        page = int(value)
        context.user_data["MOVIE_PAGE"] = page

        data = await get_movies_page(page)

        keyboard = get_movies_keyboard(
            data["movies"],
            data["page"],
            data["has_prev"],
            data["has_next"]
        )

        await query.edit_message_reply_markup(reply_markup=keyboard)
