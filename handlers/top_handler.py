from math import ceil

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from tortoise import Tortoise
from tortoise.functions import Count

from database import Movie
from utils.settings import MOVIES_PER_PAGE
from utils.decorators import channel_subscription_required, user_registered_required

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
            InlineKeyboardButton("👁 Ko'rishlar", callback_data="utop_filter_views"),
            InlineKeyboardButton("🏆 Reyting", callback_data="utop_filter_rating"),
            InlineKeyboardButton("📅 Yangi", callback_data="utop_filter_recent"),
        ]
    ]
    return InlineKeyboardMarkup(btns)


async def _filter_total(filter_type: str) -> int:
    if filter_type == "rating":
        return await Movie.filter(rating_count__gt=0, parent_movie=None).count()
    return await Movie.filter(parent_movie=None).count()


async def _rating_ordered_ids(limit: int, offset: int) -> list[int]:
    """Reyting (o'rtacha ball) bo'yicha kino ID'lari.

    ``average_rating`` saqlanadigan ustun emas (total_rating_sum/rating_count
    dan hisoblanadi), shuning uchun DB darajasida saralash uchun raw SQL
    ishlatiladi — utils/search.py dagi bir xil naqsh.
    """
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(
        """
        SELECT movie_id FROM "movie"
        WHERE rating_count > 0 AND parent_movie_id IS NULL
        ORDER BY (total_rating_sum::float / rating_count) DESC, rating_count DESC, movie_id DESC
        LIMIT %s OFFSET %s
        """,
        [limit, offset],
    )
    return [r["movie_id"] for r in rows]


async def _get_movies_page(filter_type: str, *, limit: int, offset: int) -> list[Movie]:
    """Tanlangan filtr uchun bitta sahifalik kinolarni DB darajasida oladi
    (saralash va LIMIT/OFFSET DBda bajariladi — butun katalog xotiraga
    yuklanmaydi)."""
    if filter_type == "views":
        return await (
            Movie.filter(parent_movie=None)
            .annotate(views_count=Count("viewed_by"))
            .order_by("-views_count", "-movie_id")
            .offset(offset)
            .limit(limit)
        )

    if filter_type == "recent":
        return await (
            Movie.filter(parent_movie=None)
            .order_by("-created_at", "-movie_id")
            .offset(offset)
            .limit(limit)
        )

    ids = await _rating_ordered_ids(limit, offset)
    if not ids:
        return []
    movies = await Movie.filter(movie_id__in=ids)
    by_id = {m.movie_id: m for m in movies}
    return [by_id[i] for i in ids if i in by_id]


def _movie_metric(movie: Movie, filter_type: str) -> str:
    if filter_type == "views":
        return f"👁 {getattr(movie, 'views_count', 0)}"
    if filter_type == "recent":
        return f"🆕 {movie.created_at.strftime('%d.%m.%Y')}"
    return f"⭐ {movie.average_rating}"


async def get_top_keyboard(filter_type: str = "rating", page: int = 1):
    """Tanlangan filter bo'yicha top kinolar."""
    total = await _filter_total(filter_type)
    if total == 0:
        return None, 0, 0

    total_pages = ceil(total / MOVIES_PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * MOVIES_PER_PAGE

    current_movies = await _get_movies_page(filter_type, limit=MOVIES_PER_PAGE, offset=offset)

    btns = []
    for movie in current_movies:
        metric = _movie_metric(movie, filter_type)
        text = f"{metric} 🎬 {movie.movie_name} ({movie.movie_year or '?'})"
        btns.append([InlineKeyboardButton(text, callback_data=f"umovie_{movie.movie_id}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"utop_page_{filter_type}_{page-1}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"utop_page_{filter_type}_{page+1}"))

    if nav_row:
        btns.append(nav_row)

    btns.append([InlineKeyboardButton("🔄 Filtrlar", callback_data="utop_filter_menu")])
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
