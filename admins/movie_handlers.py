from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import admin_required
from utils import get_movies_page


def get_movies_keyboard(movies, page, has_prev, has_next):
    buttons = []

    for movie in movies:
        buttons.append([
            InlineKeyboardButton(
                text=f"{movie.movie_name} → {movie.movie_code}",
                callback_data=f"movie_{movie.movie_id}"
            )
        ])

    nav_btns = []

    if has_prev:
        nav_btns.append(
            InlineKeyboardButton("⬅️ Oldingi", callback_data=f"movie_page_{page-1}")
        )

    if has_next:
        nav_btns.append(
            InlineKeyboardButton("➡️ Keyingisi", callback_data=f"movie_page_{page+1}")
        )

    if nav_btns:
        buttons.append(nav_btns)

    buttons.append([
        InlineKeyboardButton("➕ Kino qo'shish", callback_data="movie:add")
    ])

    return InlineKeyboardMarkup(buttons)


@admin_required
async def get_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 1
    context.user_data["MOVIE_PAGE"] = page

    data = await get_movies_page(page)

    keyboard = get_movies_keyboard(
        data["movies"],
        data["page"],
        data["has_prev"],
        data["has_next"]
    )

    text = "🎬 <b>Kinolar ro‘yxati</b>"

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )







