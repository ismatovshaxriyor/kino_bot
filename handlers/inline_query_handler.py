import re
import logging
from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import Movie, Rating, User, UserMovieHistory
from utils import ADMIN_ID, INLINE_THUMB_URL, MANAGER_ID
from utils.decorators import channel_subscription_required, user_registered_required


MAX_INLINE_RESULTS = 15
logger = logging.getLogger(__name__)


async def _answer_inline_query_safely(query, results, cache_time: int = 30) -> None:
    try:
        await query.answer(results=results, cache_time=cache_time, is_personal=True)
    except BadRequest as e:
        msg = str(e).lower()
        # Inline query expires quickly; in this case we just ignore it.
        if "query is too old" in msg or "query id is invalid" in msg:
            logger.warning("Skipped expired inline query answer: %s", e)
            return
        raise


def _to_result(movie: Movie) -> InlineQueryResultArticle:
    title = f"{movie.movie_name} ({movie.movie_year or '?'})"
    desc_rating = f"{movie.average_rating}/5" if movie.rating_count > 0 else "N/A"
    description = f"⭐ {desc_rating} • Kod: {movie.movie_code}"

    return InlineQueryResultArticle(
        id=f"mv_{movie.movie_id}",
        title=title[:80],
        description=description[:256],
        thumbnail_url=INLINE_THUMB_URL if INLINE_THUMB_URL else None,
        input_message_content=InputTextMessageContent(
            f"/kino movie_{movie.movie_code}"
        ),
    )


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query
    if not query:
        return

    q = (query.query or "").strip()
    movies: list[Movie] = []

    if not q:
        await _answer_inline_query_safely(query, [], cache_time=5)
        return
    elif q.isdigit():
        # code first
        exact = await Movie.get_or_none(movie_code=int(q))
        if exact:
            movies = [exact]
        name_matches = await Movie.filter(movie_name__icontains=q, parent_movie__isnull=True).limit(MAX_INLINE_RESULTS)
        if exact:
            movies.extend([m for m in name_matches if m.movie_id != exact.movie_id])
        else:
            movies = list(name_matches)
    else:
        movies = await Movie.filter(movie_name__icontains=q, parent_movie__isnull=True).limit(MAX_INLINE_RESULTS)

    results = []
    for movie in movies[:MAX_INLINE_RESULTS]:
        r = _to_result(movie)
        if r:
            results.append(r)

    await _answer_inline_query_safely(query, results, cache_time=30)


def _extract_movie_code(raw_arg: str) -> int | None:
    value = raw_arg.strip()
    if value.isdigit():
        return int(value)
    m = re.match(r"^movie_(\d+)$", value)
    if m:
        return int(m.group(1))
    return None


@user_registered_required
@channel_subscription_required
async def inline_movie_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text("⚠️ Foydalanish: /kino <kod>\nMasalan: /kino 41")
        return

    movie_code = _extract_movie_code(context.args[0])
    if movie_code is None:
        await update.message.reply_text("⚠️ Kod noto'g'ri formatda. Masalan: /kino 41 yoki /kino movie_41")
        return

    movie = await Movie.get_or_none(movie_code=movie_code).prefetch_related(
        "movie_genre", "movie_country"
    )
    if not movie:
        await update.message.reply_text(f"📭 <b>{movie_code}</b> kodli kino topilmadi.", parse_mode="HTML")
        return

    genres = await movie.movie_genre.all()
    genres_text = ", ".join([g.name for g in genres]) if genres else "Noma'lum"

    countries = await movie.movie_country.all()
    countries_text = ", ".join([c.name for c in countries]) if countries else "Noma'lum"

    unknown = "Noma'lum"
    movie_info = (
        f"🎬 <b>{escape(movie.movie_name)}</b>\n\n"
        f"📅 <b>Yil:</b> {movie.movie_year or unknown}\n"
        f"🎭 <b>Janr:</b> {escape(genres_text)}\n"
        f"🌍 <b>Davlat:</b> {escape(countries_text)}\n"
        f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
        f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else unknown}\n"
        f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else unknown}\n"
        f"⭐ <b>Reyting:</b> {movie.average_rating}/5 ({movie.rating_count} ovoz)\n"
        f"📥 <b>Kod:</b> <code>{movie.movie_code}</code>\n"
    )

    if movie.movie_description:
        desc = movie.movie_description[:300] + ("..." if len(movie.movie_description or "") > 300 else "")
        movie_info += f"\n📝 <b>Tavsif:</b> {escape(desc)}\n"

    user = await User.get(telegram_id=update.effective_user.id)
    history, created = await UserMovieHistory.get_or_create(user=user, movie=movie)
    if not created:
        await history.save()

    btns = []
    has_rated = await Rating.exists(user=user, movie=movie)
    if not has_rated:
        btns.append([InlineKeyboardButton("⭐ Baholash", callback_data=f"rate_movie_{movie.movie_id}")])

    if str(user.user_type) == "admin" or update.effective_user.id in (ADMIN_ID, MANAGER_ID):
        btns.append([InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_movie_{movie.movie_id}")])

    reply_markup = InlineKeyboardMarkup(btns) if btns else None

    if movie.file_id:
        try:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=movie.file_id,
                caption=movie_info,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return
        except BadRequest:
            pass

    await update.message.reply_text(
        movie_info + "\n⚠️ Video fayli yaroqsiz yoki topilmadi.",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
