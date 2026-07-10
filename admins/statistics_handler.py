import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import gettempdir

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Channels, Countries, Genre, Movie, Rating, User, UserMovieHistory
from utils import admin_required, error_notificator

logger = logging.getLogger(__name__)

PERIOD_LABELS = {"today": "Bugun", "week": "Oxirgi 7 kun", "month": "Oxirgi 30 kun"}

# Grafiklar uchun umumiy rang sxemasi (barcha chart-render funksiyalari shu bilan ishlaydi)
CHART_SURFACE = "#fcfcfb"
CHART_INK_PRIMARY = "#0b0b0b"
CHART_INK_SECONDARY = "#52514e"
CHART_INK_MUTED = "#898781"
CHART_GRID = "#e1e0d9"
CHART_BASELINE = "#c3c2b7"
CHART_BLUE = "#2a78d6"


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
            [InlineKeyboardButton("📊 Grafik hisobot", callback_data="stats_chart_menu")],
            [InlineKeyboardButton("🔄 Yangilash", callback_data="stats_refresh")],
        ]
    )


def _chart_period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 Bugun", callback_data="stats_chart_today"),
                InlineKeyboardButton("🗓 Hafta", callback_data="stats_chart_week"),
                InlineKeyboardButton("📆 Oy", callback_data="stats_chart_month"),
            ],
            [InlineKeyboardButton("⬅️ Ortga", callback_data="stats_overview")],
        ]
    )


def _with_menu(text: str) -> tuple[str, InlineKeyboardMarkup]:
    return text, _stats_menu_keyboard()


async def _overview_text() -> str:
    total_users = await User.all().count()
    total_admins = await User.filter(user_type="admin").count()
    total_movies = await Movie.filter(parent_movie=None).count()
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
    rated_movies = await Movie.filter(rating_count__gt=0, parent_movie=None).all()
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
    rated_movies = await Movie.filter(rating_count__gt=0, parent_movie=None).all()
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


async def _chart_data(period: str) -> dict:
    """Tanlangan davr uchun ko'rishlar dinamikasi va top kinolarni yig'ish."""
    now = datetime.now()

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        buckets = 24
        labels = [f"{h:02d}" for h in range(buckets)]
    elif period == "week":
        start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        buckets = 7
        labels = [(start + timedelta(days=i)).strftime("%d.%m") for i in range(buckets)]
    else:  # month
        start = (now - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        buckets = 30
        labels = [(start + timedelta(days=i)).strftime("%d.%m") for i in range(buckets)]

    history = await UserMovieHistory.filter(viewed_at__gte=start).prefetch_related("movie")

    counts = [0] * buckets
    view_map: dict[int, list] = {}
    unique_users = set()

    for h in history:
        unique_users.add(h.user_id)

        idx = h.viewed_at.hour if period == "today" else (h.viewed_at.date() - start.date()).days
        if 0 <= idx < buckets:
            counts[idx] += 1

        movie_id = h.movie.movie_id
        if movie_id not in view_map:
            view_map[movie_id] = [h.movie.movie_name, 0]
        view_map[movie_id][1] += 1

    top_movies = sorted(view_map.values(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "labels": labels,
        "counts": counts,
        "top_movies": [(name, count) for name, count in top_movies],
        "total_views": len(history),
        "unique_viewers": len(unique_users),
    }


def _render_stats_chart(data: dict, period: str) -> Path:
    """Ko'rishlar dinamikasi + top kinolar grafigini PNG faylga chizish (CPU-bound, sync)."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import MaxNLocator

    SURFACE = CHART_SURFACE
    INK_PRIMARY = CHART_INK_PRIMARY
    INK_SECONDARY = CHART_INK_SECONDARY
    INK_MUTED = CHART_INK_MUTED
    GRID = CHART_GRID
    BASELINE = CHART_BASELINE
    BLUE = CHART_BLUE

    period_label = PERIOD_LABELS[period]
    labels = data["labels"]
    counts = data["counts"]
    top_movies = data["top_movies"]

    fig = Figure(figsize=(9, 9), dpi=150, facecolor=SURFACE)
    ax1, ax2 = fig.subplots(2, 1, height_ratios=[1, 1.3])
    fig.subplots_adjust(hspace=0.4, left=0.1, right=0.95, top=0.94, bottom=0.06)

    # --- Ko'rishlar dinamikasi (chiziqli grafik) ---
    ax1.set_facecolor(SURFACE)
    x = list(range(len(labels)))
    ax1.plot(x, counts, color=BLUE, linewidth=2, solid_capstyle="round", zorder=3)
    ax1.scatter(x, counts, s=32, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=4)
    ax1.fill_between(x, counts, color=BLUE, alpha=0.10, zorder=2)

    if counts:
        ax1.annotate(
            str(counts[-1]), (x[-1], counts[-1]),
            textcoords="offset points", xytext=(6, 8),
            fontsize=10, color=INK_PRIMARY, fontweight="bold",
        )

    ax1.set_title(f"Ko'rishlar dinamikasi — {period_label}", fontsize=13, color=INK_PRIMARY, fontweight="bold", loc="left", pad=12)
    step = max(1, len(labels) // 12)
    ax1.set_xticks(x[::step])
    ax1.set_xticklabels([labels[i] for i in x[::step]], fontsize=9, color=INK_MUTED)
    ax1.tick_params(axis="y", labelsize=9, colors=INK_MUTED)
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.grid(axis="y", color=GRID, linewidth=1)
    ax1.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax1.spines[side].set_visible(False)
    ax1.spines["bottom"].set_color(BASELINE)
    ax1.set_ylim(bottom=0)

    # --- Top 10 ko'rilgan kinolar (gorizontal ustunli diagramma) ---
    ax2.set_facecolor(SURFACE)
    if top_movies:
        names = [n if len(n) <= 28 else n[:27] + "…" for n, _ in top_movies][::-1]
        values = [c for _, c in top_movies][::-1]
        y = list(range(len(names)))
        bars = ax2.barh(y, values, color=BLUE, height=0.6, zorder=3)
        for rect, v in zip(bars, values):
            ax2.annotate(
                str(v), (rect.get_width(), rect.get_y() + rect.get_height() / 2),
                textcoords="offset points", xytext=(6, 0),
                va="center", fontsize=9, color=INK_PRIMARY, fontweight="bold",
            )
        ax2.set_yticks(y)
        ax2.set_yticklabels(names, fontsize=9.5, color=INK_SECONDARY)
        ax2.set_xlim(0, max(values) * 1.18)
    else:
        ax2.text(0.5, 0.5, "Ma'lumot yo'q", ha="center", va="center", fontsize=11, color=INK_MUTED, transform=ax2.transAxes)
        ax2.set_yticks([])

    ax2.set_title(f"Top 10 ko'rilgan kinolar — {period_label}", fontsize=13, color=INK_PRIMARY, fontweight="bold", loc="left", pad=12)
    ax2.tick_params(axis="x", labelsize=9, colors=INK_MUTED)
    ax2.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax2.grid(axis="x", color=GRID, linewidth=1)
    ax2.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax2.spines[side].set_visible(False)
    ax2.spines["bottom"].set_color(BASELINE)

    out_path = Path(gettempdir()) / f"kino_stats_{period}_{datetime.now():%Y%m%d_%H%M%S}.png"
    canvas = FigureCanvasAgg(fig)
    canvas.print_png(out_path)
    return out_path


MOVIE_CHART_DAYS = 30


async def _movie_chart_data(movie_id: int, days: int = MOVIE_CHART_DAYS) -> dict:
    """Bitta kino uchun oxirgi N kunlik kunlik ko'rishlar sonini yig'ish."""
    now = datetime.now()
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    labels = [(start + timedelta(days=i)).strftime("%d.%m") for i in range(days)]

    history = await UserMovieHistory.filter(movie_id=movie_id, viewed_at__gte=start)

    counts = [0] * days
    unique_users = set()
    for h in history:
        idx = (h.viewed_at.date() - start.date()).days
        if 0 <= idx < days:
            counts[idx] += 1
        unique_users.add(h.user_id)

    return {
        "labels": labels,
        "counts": counts,
        "total_views": len(history),
        "unique_viewers": len(unique_users),
    }


def _render_movie_chart(movie_name: str, data: dict) -> Path:
    """Bitta kino uchun kunlik ko'rishlar chizig'ini PNG faylga chizish (CPU-bound, sync)."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import MaxNLocator

    labels = data["labels"]
    counts = data["counts"]

    fig = Figure(figsize=(9, 5), dpi=150, facecolor=CHART_SURFACE)
    ax = fig.subplots()
    fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.12)

    ax.set_facecolor(CHART_SURFACE)
    x = list(range(len(labels)))
    ax.plot(x, counts, color=CHART_BLUE, linewidth=2, solid_capstyle="round", zorder=3)
    ax.scatter(x, counts, s=32, color=CHART_BLUE, edgecolor=CHART_SURFACE, linewidth=1.5, zorder=4)
    ax.fill_between(x, counts, color=CHART_BLUE, alpha=0.10, zorder=2)

    if counts:
        ax.annotate(
            str(counts[-1]), (x[-1], counts[-1]),
            textcoords="offset points", xytext=(6, 8),
            fontsize=10, color=CHART_INK_PRIMARY, fontweight="bold",
        )

    title = movie_name if len(movie_name) <= 45 else movie_name[:44] + "…"
    ax.set_title(
        f"{title} — kunlik ko'rishlar (oxirgi {len(labels)} kun)",
        fontsize=12.5, color=CHART_INK_PRIMARY, fontweight="bold", loc="left", pad=12,
    )
    step = max(1, len(labels) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([labels[i] for i in x[::step]], fontsize=9, color=CHART_INK_MUTED)
    ax.tick_params(axis="y", labelsize=9, colors=CHART_INK_MUTED)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color=CHART_GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(CHART_BASELINE)
    ax.set_ylim(bottom=0)

    out_path = Path(gettempdir()) / f"kino_movie_chart_{datetime.now():%Y%m%d_%H%M%S}.png"
    canvas = FigureCanvasAgg(fig)
    canvas.print_png(out_path)
    return out_path


async def send_movie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, movie) -> None:
    """Bitta kino uchun ko'rishlar grafigini yaratib, rasm sifatida yuboradi va serverdan o'chiradi.

    Diqqat: bu yerda ``query.answer()`` chaqirilmaydi — chaqiruvchi (movie_callback)
    allaqachon callback query'ga javob bergan; Telegram bitta query'ga faqat bitta
    marta samarali javob qabul qiladi.
    """
    query = update.callback_query
    chat_id = query.message.chat_id

    out_path = None
    try:
        data = await _movie_chart_data(movie.movie_id)
        out_path = await asyncio.to_thread(_render_movie_chart, movie.movie_name, data)

        caption = (
            f"📈 <b>{movie.movie_name}</b> — kunlik ko'rishlar (oxirgi {MOVIE_CHART_DAYS} kun)\n\n"
            f"▶️ Jami ko'rishlar: <b>{data['total_views']}</b>\n"
            f"👤 Noyob foydalanuvchilar: <b>{data['unique_viewers']}</b>"
        )

        with out_path.open("rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
            )
    except Exception as e:
        logger.exception("Kino grafigida xato: %s", e)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>Grafik yaratishda xato:</b>\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
            direct=True,
        )
    finally:
        if out_path is not None:
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass


async def _send_stats_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Grafikni yaratib, so'ragan adminga rasm sifatida yuboradi va serverdan o'chiradi."""
    query = update.callback_query
    chat_id = query.message.chat_id

    await query.edit_message_text("⏳ <b>Grafik tayyorlanmoqda...</b>", parse_mode="HTML")

    out_path = None
    try:
        data = await _chart_data(period)
        out_path = await asyncio.to_thread(_render_stats_chart, data, period)

        caption = (
            f"📊 <b>Kinolar statistikasi — {PERIOD_LABELS[period]}</b>\n\n"
            f"▶️ Ko'rishlar: <b>{data['total_views']}</b>\n"
            f"👤 Faol foydalanuvchilar: <b>{data['unique_viewers']}</b>"
        )

        with out_path.open("rb") as photo:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
            )
    except Exception as e:
        logger.exception("Statistika grafigida xato: %s", e)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>Grafik yaratishda xato:</b>\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
            direct=True,
        )
    finally:
        if out_path is not None:
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass

    text, keyboard = _with_menu(
        "📊 <b>Statistika bo'limi</b>\n\nQuyidagi bo'limlardan birini tanlang:"
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML", direct=True)


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

        if section == "chart_menu":
            await query.edit_message_text(
                "📊 <b>Grafik hisobot</b>\n\nQaysi davr uchun grafik tayyorlaymiz?",
                reply_markup=_chart_period_keyboard(),
                parse_mode="HTML",
            )
            return

        if section in ("chart_today", "chart_week", "chart_month"):
            period = section.removeprefix("chart_")
            await _send_stats_chart(update, context, period)
            return

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
