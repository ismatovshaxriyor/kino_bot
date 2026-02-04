from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from math import ceil

from database import Movie
from utils.decorators import channel_subscription_required

MOVIES_PER_PAGE = 5

async def get_top_keyboard(page: int = 1):
    """Top reytingli kinolar tugmalari"""
    # Reytingi bor kinolarni olish
    movies = await Movie.filter(rating_count__gt=0).all()

    # Reyting bo'yicha saralash (average_rating property)
    movies.sort(key=lambda m: m.average_rating, reverse=True)

    total = len(movies)
    if total == 0:
        return None, 0, 0

    total_pages = ceil(total / MOVIES_PER_PAGE)

    # Pagination slicing
    start = (page - 1) * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE
    current_movies = movies[start:end]

    btns = []
    for movie in current_movies:
        rating = f"⭐ {movie.average_rating}"
        text = f"🎬 {movie.movie_name} ({movie.movie_year or '?'}) {rating}"
        btns.append([InlineKeyboardButton(text, callback_data=f"umovie_{movie.movie_id}")])

    # Pagination tugmalari
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"utop_page_{page-1}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"utop_page_{page+1}"))

    if nav_row:
        btns.append(nav_row)

    return InlineKeyboardMarkup(btns), total, total_pages


@channel_subscription_required
async def top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/top komandasi handleri"""
    keyboard, total, total_pages = await get_top_keyboard(1)

    if total == 0:
        await update.message.reply_text("📭 Hozircha reytingli kinolar yo'q.")
        return

    await update.message.reply_text(
        f"🏆 <b>Top Reyting Kinolar:</b>\n\n"
        f"📊 Jami: {total} ta kino",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
