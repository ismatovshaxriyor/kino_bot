from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from math import ceil

from tortoise.expressions import F
from tortoise.exceptions import IntegrityError

from database import Genre, Movie, Rating, User, UserMovieHistory
from utils import user_keyboard
from utils.settings import MOVIES_PER_PAGE
from utils.decorators import user_registered_required
from utils.error_notificator import error_notificator
from utils.movie_card import (
    build_movie_card,
    build_parts_list_card,
    get_child_parts,
    movie_caption,
)
from handlers.history_handler import get_history_keyboard
from handlers.top_handler import get_top_filter_keyboard, get_top_keyboard, get_top_title


async def _safe_answer(query, *args, **kwargs) -> bool:
    try:
        await query.answer(*args, **kwargs)
        return True
    except BadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            return False
        raise


async def _record_history(user: User, movie: Movie) -> None:
    """Ko'rilgan kinoni tarixga yozish (yoki vaqtini yangilash)."""
    history, created = await UserMovieHistory.get_or_create(user=user, movie=movie)
    if not created:
        await history.save()


async def _send_movie(update: Update, context: ContextTypes.DEFAULT_TYPE, movie: Movie, user: User) -> None:
    """Bitta (qismsiz) kinoni video + karta ko'rinishida yuborish."""
    caption, reply_markup = await build_movie_card(
        movie,
        user=user,
        user_id=update.effective_user.id,
        bot_username=context.bot.username,
    )
    chat_id = update.effective_chat.id

    if movie.file_id:
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=movie.file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except BadRequest as e:
            await error_notificator.notify(context, e, update)
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption + "\n\n⚠️ Video fayli yaroqsiz yoki o'chirilgan.",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption + "\n\n⚠️ Video fayli hali yuklanmagan.",
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


async def get_movies_by_filter(filter_type: str, filter_value: str, page: int = 1):
    """Filtrlangan kinolarni olish"""
    offset = (page - 1) * MOVIES_PER_PAGE

    if filter_type == "genre":
        genre = await Genre.get_or_none(genre_id=int(filter_value))
        if not genre:
            return [], 0, 0
        movies_query = Movie.filter(movie_genre=genre, parent_movie=None)
    elif filter_type == "year":
        movies_query = Movie.filter(movie_year=int(filter_value), parent_movie=None)
    elif filter_type == "search":
        movies_query = Movie.filter(movie_name__icontains=filter_value, parent_movie=None)
    else:
        return [], 0, 0

    total = await movies_query.count()
    total_pages = ceil(total / MOVIES_PER_PAGE) if total > 0 else 1
    movies = await movies_query.offset(offset).limit(MOVIES_PER_PAGE)

    return movies, total, total_pages


async def get_movies_keyboard(movies, page: int, total_pages: int, filter_type: str, filter_value: str):
    """Kinolar ro'yxati tugmalari (pagination bilan)"""
    btns = []

    for movie in movies:
        rating = f"⭐ {movie.average_rating}" if movie.rating_count > 0 else ""
        text = f"🎬 {movie.movie_name} ({movie.movie_year or '?'}) {rating}"
        btns.append([InlineKeyboardButton(text, callback_data=f"umovie_{movie.movie_id}")])

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
async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User qidiruv callbacklari"""
    query = update.callback_query
    await _safe_answer(query)
    data = query.data

    # Janr tanlash
    if data.startswith("ugenre_"):
        genre_id = data.split("_")[1]
        genre = await Genre.get_or_none(genre_id=int(genre_id))

        if not genre:
            await query.edit_message_text("⚠️ Janr topilmadi.")
            return

        movies, total, total_pages = await get_movies_by_filter("genre", genre_id, 1)

        if not movies:
            await query.edit_message_text(
                f"📭 <b>{genre.name}</b> janrida kinolar topilmadi.",
                parse_mode="HTML"
            )
            return

        keyboard = await get_movies_keyboard(movies, 1, total_pages, "genre", genre_id)
        await query.edit_message_text(
            f"🎭 <b>{genre.name}</b> janridagi kinolar:\n\n"
            f"📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    # Yil tanlash
    elif data.startswith("uyear_"):
        year = data.split("_")[1]
        movies, total, total_pages = await get_movies_by_filter("year", year, 1)

        if not movies:
            await query.edit_message_text(
                f"📭 <b>{year}</b> yilda kinolar topilmadi.",
                parse_mode="HTML"
            )
            return

        keyboard = await get_movies_keyboard(movies, 1, total_pages, "year", year)
        await query.edit_message_text(
            f"📅 <b>{year}</b> yildagi kinolar:\n\n"
            f"📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    # Pagination
    elif data.startswith("upage_"):
        parts = data.split("_")
        filter_type = parts[1]
        filter_value = parts[2]
        page = int(parts[3])

        movies, total, total_pages = await get_movies_by_filter(filter_type, filter_value, page)
        keyboard = await get_movies_keyboard(movies, page, total_pages, filter_type, filter_value)

        if filter_type == "genre":
            genre = await Genre.get_or_none(genre_id=int(filter_value))
            title = f"🎭 <b>{genre.name if genre else 'Janr'}</b> janridagi kinolar:"
        elif filter_type == "year":
            title = f"📅 <b>{filter_value}</b> yildagi kinolar:"
        else:
            title = f"🔍 <b>\"{filter_value}\"</b> bo'yicha natijalar:"

        await query.edit_message_text(
            f"{title}\n\n📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    # Kino tanlash
    elif data.startswith("umovie_"):
        movie_id = int(data.split("_")[1])
        movie = await Movie.get_or_none(movie_id=movie_id)

        if not movie:
            await query.edit_message_text("⚠️ Kino topilmadi.")
            return

        user = await User.get(telegram_id=update.effective_user.id)
        await _record_history(user, movie)

        # Qismli kino — qismlar ro'yxatini ko'rsatish
        child_parts = await get_child_parts(movie)
        if child_parts:
            text, markup = build_parts_list_card(movie, child_parts)
            if query.message.text:
                await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
            else:
                await query.delete_message()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML",
                )
            return

        # Qismsiz kino — to'g'ridan-to'g'ri video
        await query.delete_message()
        await _send_movie(update, context, movie, user)

    # Kino ko'rish (qismni tekshirmasdan to'g'ridan-to'g'ri video)
    elif data.startswith("uwatch_"):
        movie_id = int(data.split("_")[1])
        movie = await Movie.get_or_none(movie_id=movie_id)

        if not movie:
            await _safe_answer(query, "⚠️ Kino topilmadi.", show_alert=True)
            return

        user = await User.get(telegram_id=update.effective_user.id)
        await _record_history(user, movie)

        try:
            await query.delete_message()
        except BadRequest:
            pass

        await _send_movie(update, context, movie, user)

    # Ortga
    elif data == "user_back":
        await query.edit_message_text(
            "🎬 <b>Kino qidirish</b>\n\n"
            "Quyidagi tugmalardan foydalaning:",
            parse_mode="HTML"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👇 Menyu:",
            reply_markup=user_keyboard
        )

    # Tarix pagination
    elif data.startswith("uhistory_page_"):
        page = int(data.split("_")[2])
        user_id = update.effective_user.id

        keyboard, total, total_pages = await get_history_keyboard(user_id, page)

        await query.edit_message_text(
            f"📜 <b>Siz ko'rgan kinolar tarixi:</b>\n\n"
            f"📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    # Top filter menyusi
    elif data == "utop_filter_menu":
        await query.edit_message_text(
            "🏆 <b>Top kinolar</b>\n\nKerakli filtrni tanlang:",
            reply_markup=get_top_filter_keyboard(),
            parse_mode="HTML",
        )

    # Top filter tanlash
    elif data.startswith("utop_filter_"):
        filter_type = data.split("_")[2]
        keyboard, total, total_pages = await get_top_keyboard(filter_type, 1)

        if total == 0:
            await query.edit_message_text(
                "📭 Hozircha bu filtr bo'yicha kinolar yo'q.",
                reply_markup=get_top_filter_keyboard(),
            )
            return

        await query.edit_message_text(
            f"{get_top_title(filter_type)}\n\n"
            f"📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    # Top pagination
    elif data.startswith("utop_page_"):
        parts = data.split("_")
        if len(parts) == 3 and parts[2].isdecimal():
            filter_type = "rating"
            page = int(parts[2])
        else:
            filter_type = parts[2]
            page = int(parts[3])

        keyboard, total, total_pages = await get_top_keyboard(filter_type, page)

        if total == 0:
            await query.edit_message_text(
                "📭 Hozircha bu filtr bo'yicha kinolar yo'q.",
                reply_markup=get_top_filter_keyboard(),
            )
            return

        await query.edit_message_text(
            f"{get_top_title(filter_type)}\n\n"
            f"📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    # Baholash tugmasi bosilganda
    elif data.startswith("rate_movie_"):
        movie_id = int(data.split("_")[2])
        movie = await Movie.get_or_none(movie_id=movie_id)

        if not movie:
            await _safe_answer(query, "⚠️ Kino topilmadi.", show_alert=True)
            return

        btns = [
            [InlineKeyboardButton(f"{i} ⭐", callback_data=f"set_rating_{movie_id}_{i}") for i in range(1, 6)],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"cancel_rating_{movie_id}")],
        ]
        keyboard = InlineKeyboardMarkup(btns)

        caption = await movie_caption(movie) + "\n\n👇 <b>Kino uchun baho bering:</b>"

        if query.message.caption:
            await query.edit_message_caption(caption=caption, reply_markup=keyboard, parse_mode="HTML")
        else:
            await query.edit_message_text(text=caption, reply_markup=keyboard, parse_mode="HTML")

    # Baholashni bekor qilish
    elif data.startswith("cancel_rating_"):
        movie_id = int(data.split("_")[2])
        user_id = update.effective_user.id

        movie = await Movie.get_or_none(movie_id=movie_id)
        user = await User.get_or_none(telegram_id=user_id)

        if not movie or not user:
            await _safe_answer(query, "⚠️ Xatolik yuz berdi.", show_alert=True)
            return

        caption, reply_markup = await build_movie_card(
            movie, user=user, user_id=user_id, bot_username=context.bot.username
        )

        if query.message.caption:
            await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await query.edit_message_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")

    # Bahoni saqlash
    elif data.startswith("set_rating_"):
        parts = data.split("_")
        movie_id = int(parts[2])
        score = int(parts[3])
        user_id = update.effective_user.id

        movie = await Movie.get_or_none(movie_id=movie_id)
        user = await User.get_or_none(telegram_id=user_id)

        if not movie or not user:
            await _safe_answer(query, "⚠️ Xatolik yuz berdi.", show_alert=True)
            return

        if await Rating.exists(user=user, movie=movie):
            await _safe_answer(query, "⚠️ Siz allaqachon ovoz bergansiz!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        try:
            await Rating.create(user=user, movie=movie, score=score)
        except IntegrityError:
            # Poyga holati: exists() va create() orasida boshqa so'rov ovoz qo'ygan.
            # UNIQUE (user, movie) cheklovi himoya qiladi — foydalanuvchiga do'stona xabar.
            await _safe_answer(query, "⚠️ Siz allaqachon ovoz bergansiz!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        # Atomik yangilash — bir vaqtdagi ovozlar bir-birini yo'qotmaydi
        await Movie.filter(movie_id=movie_id).update(
            total_rating_sum=F("total_rating_sum") + score,
            rating_count=F("rating_count") + 1,
        )

        await _safe_answer(query, f"✅ {score} ⭐ baho qo'yildi!", show_alert=True)

        # Yangilangan reyting bilan qayta yuklash
        movie = await Movie.get(movie_id=movie_id)
        caption, reply_markup = await build_movie_card(
            movie, user=user, user_id=user_id, bot_username=context.bot.username
        )

        if query.message.caption:
            await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await query.edit_message_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")

    # Noop
    elif data == "noop":
        await _safe_answer(query)
