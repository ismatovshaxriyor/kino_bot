from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Channels, Countries, Genre, Movie, Rating, User, UserMovieHistory
from utils import admin_required, error_notificator


def _stats_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📦 Umumiy", callback_data="stats_overview"),
                InlineKeyboardButton("📈 Faollik", callback_data="stats_activity"),
            ],
            [
                InlineKeyboardButton("🤖 AI", callback_data="stats_ai"),
                InlineKeyboardButton("⭐ Reyting", callback_data="stats_rating"),
            ],
            [InlineKeyboardButton("🏆 Top kinolar", callback_data="stats_top")],
            [InlineKeyboardButton("🔄 Yangilash", callback_data="stats_refresh")],
        ]
    )


def _with_menu(text: str) -> tuple[str, InlineKeyboardMarkup]:
    return text, _stats_menu_keyboard()


async def _overview_text() -> str:
    total_users = await User.all().count()
    total_admins = await User.filter(user_type="admin").count()
    total_movies = await Movie.all().count()
    total_genres = await Genre.all().count()
    total_countries = await Countries.all().count()
    total_channels = await Channels.all().count()

    return (
        "📊 <b>Statistika — Umumiy</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total_users}</b>\n"
        f"🛡 Admin/Manager: <b>{total_admins}</b>\n"
        f"🎬 Kinolar: <b>{total_movies}</b>\n"
        f"🎭 Janrlar: <b>{total_genres}</b>\n"
        f"🌍 Davlatlar: <b>{total_countries}</b>\n"
        f"📢 Kanallar: <b>{total_channels}</b>"
    )


async def _activity_text() -> str:
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=7)

    active_user_ids_today = await UserMovieHistory.filter(viewed_at__gte=day_start).values_list("user_id", flat=True)
    active_user_ids_week = await UserMovieHistory.filter(viewed_at__gte=week_start).values_list("user_id", flat=True)
    active_users_today = len(set(active_user_ids_today))
    active_users_week = len(set(active_user_ids_week))
    views_today = await UserMovieHistory.filter(viewed_at__gte=day_start).count()
    views_week = await UserMovieHistory.filter(viewed_at__gte=week_start).count()

    return (
        "📈 <b>Statistika — Faollik</b>\n\n"
        f"📅 Bugun aktiv userlar: <b>{active_users_today}</b>\n"
        f"🗓 Oxirgi 7 kun aktiv userlar: <b>{active_users_week}</b>\n"
        f"▶️ Bugungi ko'rishlar: <b>{views_today}</b>\n"
        f"⏱ Oxirgi 7 kun ko'rishlar: <b>{views_week}</b>"
    )


async def _ai_text() -> str:
    today = datetime.now().date()
    ai_users_today = await User.filter(ai_usage_date=today, ai_usage__gt=0).all()
    ai_requests_today = sum(u.ai_usage for u in ai_users_today)
    ai_limit_reached_today = sum(1 for u in ai_users_today if u.ai_usage >= 3)

    return (
        "🤖 <b>Statistika — AI</b>\n\n"
        f"🧾 Bugungi AI so'rovlar: <b>{ai_requests_today}</b>\n"
        f"👤 AI ishlatgan userlar: <b>{len(ai_users_today)}</b>\n"
        f"🚫 Limitga yetgan userlar: <b>{ai_limit_reached_today}</b>"
    )


async def _rating_text() -> str:
    ratings_total = await Rating.all().count()
    rated_movies_total = await Movie.filter(rating_count__gt=0).count()

    avg_rating_global = 0.0
    rated_movies = await Movie.filter(rating_count__gt=0).all()
    if rated_movies:
        avg_rating_global = round(sum(m.average_rating for m in rated_movies) / len(rated_movies), 2)

    return (
        "⭐ <b>Statistika — Reyting</b>\n\n"
        f"🗳 Jami ovozlar: <b>{ratings_total}</b>\n"
        f"🎥 Reytingli kinolar: <b>{rated_movies_total}</b>\n"
        f"📊 Umumiy o'rtacha reyting: <b>{avg_rating_global}</b>"
    )


async def _top_text() -> str:
    # Ko'rilish bo'yicha top
    view_map = {}
    histories = await UserMovieHistory.all().prefetch_related("movie")
    for item in histories:
        movie_id = item.movie.movie_id
        if movie_id not in view_map:
            view_map[movie_id] = [item.movie, 0]
        view_map[movie_id][1] += 1
    top_viewed = sorted(view_map.values(), key=lambda x: x[1], reverse=True)[:5]
    viewed_text = (
        "\n".join(f"{i}. {m.movie_name} — {count} marta" for i, (m, count) in enumerate(top_viewed, start=1))
        if top_viewed else
        "—"
    )

    # Reyting bo'yicha top
    rated_movies = await Movie.filter(rating_count__gt=0).all()
    top_rated = sorted(rated_movies, key=lambda m: (m.average_rating, m.rating_count), reverse=True)[:5]
    rated_text = (
        "\n".join(
            f"{i}. {m.movie_name} — ⭐ {m.average_rating} ({m.rating_count} ovoz)"
            for i, m in enumerate(top_rated, start=1)
        )
        if top_rated else
        "—"
    )

    return (
        "🏆 <b>Statistika — Top kinolar</b>\n\n"
        "<b>Top 5 ko'p ko'rilgan:</b>\n"
        f"{viewed_text}\n\n"
        "<b>Top 5 eng yuqori reytingli:</b>\n"
        f"{rated_text}"
    )


@admin_required
async def statistics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text, keyboard = _with_menu(
            "📊 <b>Statistika bo'limi</b>\n\n"
            "Quyidagi bo'limlardan birini tanlang:"
        )
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await error_notificator.notify(context, e, update)


@admin_required
async def statistics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        section = query.data.split("_", 1)[1]
        builders = {
            "overview": _overview_text,
            "activity": _activity_text,
            "ai": _ai_text,
            "rating": _rating_text,
            "top": _top_text,
            "refresh": _overview_text,
        }
        build = builders.get(section, _overview_text)
        text, keyboard = _with_menu(await build())
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        await error_notificator.notify(context, e, update)
