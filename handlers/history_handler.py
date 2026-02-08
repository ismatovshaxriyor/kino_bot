from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from math import ceil

from database import User, UserMovieHistory
from utils.decorators import channel_subscription_required, user_registered_required

MOVIES_PER_PAGE = 15

async def get_history_keyboard(user_id, page: int = 1):
    """Tarix tugmalarini generatsiya qilish"""
    offset = (page - 1) * MOVIES_PER_PAGE
    user = await User.get(telegram_id=user_id)
    history_query = UserMovieHistory.filter(user=user).select_related('movie').order_by('-viewed_at')

    total = await history_query.count()
    if total == 0:
        return None, 0, 0

    total_pages = ceil(total / MOVIES_PER_PAGE)
    histories = await history_query.offset(offset).limit(MOVIES_PER_PAGE)

    btns = []
    for h in histories:
        movie = h.movie
        rating = f"⭐ {movie.average_rating}" if movie.rating_count > 0 else ""
        text = f"🎬 {movie.movie_name} ({movie.movie_year or '?'}) {rating}"
        btns.append([InlineKeyboardButton(text, callback_data=f"umovie_{movie.movie_id}")])

    # Pagination
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"uhistory_page_{page-1}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"uhistory_page_{page+1}"))

    if nav_row:
        btns.append(nav_row)

    return InlineKeyboardMarkup(btns), total, total_pages


@user_registered_required
@channel_subscription_required
async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/history komandasi handleri"""
    user_id = update.effective_user.id
    keyboard, total, total_pages = await get_history_keyboard(user_id, 1)

    if total == 0:
        await update.message.reply_text("📭 Siz hali hech qanday kino ko'rmagansiz.")
        return

    await update.message.reply_text(
        f"📜 <b>Siz ko'rgan kinolar tarixi:</b>\n\n"
        f"📊 Jami: {total} ta kino",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
