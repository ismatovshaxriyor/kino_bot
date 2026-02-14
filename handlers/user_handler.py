from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import Genre, Movie
from utils.decorators import channel_subscription_required, user_registered_required


MOVIES_PER_PAGE = 15


async def get_genre_keyboard():
    """Janrlar ro'yxati tugmalari"""
    genres = await Genre.all()
    btns = []
    row = []

    for i, genre in enumerate(genres):
        row.append(InlineKeyboardButton(f"🎭 {genre.name}", callback_data=f"ugenre_{genre.genre_id}"))
        if len(row) == 2:
            btns.append(row)
            row = []

    if row:
        btns.append(row)

    btns.append([InlineKeyboardButton("🔙 Ortga", callback_data="user_back")])
    return InlineKeyboardMarkup(btns)


async def get_year_keyboard():
    """Yillar ro'yxati tugmalari"""
    # Kinolar yillarini olish
    movies = await Movie.filter(parent_movie__isnull=True).distinct().values_list('movie_year', flat=True)
    years = sorted(set([y for y in movies if y]), reverse=True)

    btns = []
    row = []

    for year in years[:20]:  # Oxirgi 20 yil
        row.append(InlineKeyboardButton(f"📅 {year}", callback_data=f"uyear_{year}"))
        if len(row) == 4:
            btns.append(row)
            row = []

    if row:
        btns.append(row)

    btns.append([InlineKeyboardButton("🔙 Ortga", callback_data="user_back")])
    return InlineKeyboardMarkup(btns)


async def get_movies_keyboard(movies, page: int, total_pages: int, filter_type: str, filter_value: str):
    """Kinolar ro'yxati tugmalari (pagination bilan)"""
    btns = []

    for movie in movies:
        rating = f"⭐ {movie.average_rating}" if movie.rating_count > 0 else ""
        btns.append([InlineKeyboardButton(
            f"🎬 {movie.movie_name} ({movie.movie_year or '?'}) {rating}",
            callback_data=f"umovie_{movie.movie_id}"
        )])

    # Pagination tugmalari
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"upage_{filter_type}_{filter_value}_{page-1}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"upage_{filter_type}_{filter_value}_{page+1}"))

    if nav_row:
        btns.append(nav_row)

    btns.append([InlineKeyboardButton("🔙 Ortga", callback_data="user_back")])
    return InlineKeyboardMarkup(btns)


@user_registered_required
@channel_subscription_required
async def search_by_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🔍 Nomi bo'yicha qidirish"""
    context.user_data['state'] = "SEARCH_BY_NAME"

    await update.message.reply_text(
        "🔍 <b>Kino nomini kiriting:</b>\n\n"
        "📌 Masalan: Titanic, Avatar, Joker...\n\n"
        "❌ Bekor qilish uchun /start bosing",
        parse_mode="HTML"
    )


@user_registered_required
@channel_subscription_required
async def search_by_genre_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎭 Janr bo'yicha qidirish"""
    keyboard = await get_genre_keyboard()

    await update.message.reply_text(
        "🎭 <b>Janrni tanlang:</b>\n\n"
        "Tanlangan janrdagi barcha kinolar ko'rsatiladi.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@user_registered_required
@channel_subscription_required
async def search_by_year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📅 Yil bo'yicha qidirish"""
    keyboard = await get_year_keyboard()

    await update.message.reply_text(
        "📅 <b>Yilni tanlang:</b>\n\n"
        "Tanlangan yildagi barcha kinolar ko'rsatiladi.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@user_registered_required
@channel_subscription_required
async def ai_assistant_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🤖 AI yordamchi"""
    context.user_data['state'] = "CHAT_WITH_AI"

    await update.message.reply_text(
        "🤖 <b>AI Kino Yordamchi</b>\n\n"
        "Men sizga kino tanlashda yordam beraman!\n\n"
        "📝 <b>Masalan yozing:</b>\n"
        "• \"Qo'rqinchli kino tavsiya qil\"\n"
        "• \"Oilaviy komediya kerak\"\n"
        "• \"2023 yilning eng yaxshi filmlari\"\n\n"
        "❌ Chiqish uchun /start bosing\n\n"
        "⚠️ <i>Kunlik limit: 3 ta so'rov</i>",
        parse_mode="HTML"
    )
