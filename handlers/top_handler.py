from math import ceil

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from tortoise.functions import Count

from database import Movie
from utils.decorators import channel_subscription_required, user_registered_required

MOVIES_PER_PAGE = 5
TOP_FILTERS = {
    "views": "Ko'rishlar bo'yicha",
    "rating": "Reyting bo'yicha",
    "recent": "Oxirgi qo'shilganlar",
}


def get_top_title(filter_type: str) -> str:
    label = TOP_FILTERS.get(filter_type, TOP_FILTERS["rating"])
    return f"🏆 <b>Top kinolar ({label})</b>"


def get_top_filter_keyboard() -> InlineKeyboardMarkup:
    btns = [
        [
            InlineKeyboardButton("Ko'rishlar", callback_data="utop_filter_views"),
            InlineKeyboardButton("Reyting", callback_data="utop_filter_rating"),
            InlineKeyboardButton("Yangi", callback_data="utop_filter_recent"),
        ]
    ]
    return InlineKeyboardMarkup(btns)


async def _get_movies_for_filter(filter_type: str) -> list[Movie]:
    if filter_type == "views":
        movies = await Movie.annotate(views_count=Count("viewed_by")).all()
        movies.sort(
            key=lambda m: (getattr(m, "views_count", 0), m.average_rating, m.rating_count),
            reverse=True,
        )
        return movies

    if filter_type == "recent":
        return await Movie.all().order_by("-created_at")

    movies = await Movie.filter(rating_count__gt=0).all()
    movies.sort(key=lambda m: (m.average_rating, m.rating_count), reverse=True)
    return movies


def _movie_metric(movie: Movie, filter_type: str) -> str:
    if filter_type == "views":
        return f"👁 {getattr(movie, 'views_count', 0)}"
    if filter_type == "recent":
        return f"🆕 {movie.created_at.strftime('%d.%m.%Y')}"
    return f"⭐ {movie.average_rating}"


async def get_top_keyboard(filter_type: str = "rating", page: int = 1):
    """Tanlangan filter bo'yicha top kinolar."""
    movies = await _get_movies_for_filter(filter_type)

    total = len(movies)
    if total == 0:
        return None, 0, 0

    total_pages = ceil(total / MOVIES_PER_PAGE)
    page = max(1, min(page, total_pages))

    start = (page - 1) * MOVIES_PER_PAGE
    end = start + MOVIES_PER_PAGE
    current_movies = movies[start:end]

    btns = []
    for movie in current_movies:
        metric = _movie_metric(movie, filter_type)
        text = f"🎬 {movie.movie_name} ({movie.movie_year or '?'}) {metric}"
        btns.append([InlineKeyboardButton(text, callback_data=f"umovie_{movie.movie_id}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"utop_page_{filter_type}_{page-1}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"utop_page_{filter_type}_{page+1}"))

    if nav_row:
        btns.append(nav_row)

    btns.append([InlineKeyboardButton("Filtrlar", callback_data="utop_filter_menu")])
    return InlineKeyboardMarkup(btns), total, total_pages


@user_registered_required
@channel_subscription_required
async def top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top bo'limini ochish (filtrlar bilan)."""
    await update.message.reply_text(
        "🏆 <b>Top kinolar</b>\n\nKerakli filtrni tanlang:",
        reply_markup=get_top_filter_keyboard(),
        parse_mode="HTML",
    )
