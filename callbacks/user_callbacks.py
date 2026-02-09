from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from math import ceil

from database import Genre, Movie, Rating, User, UserMovieHistory
from utils import user_keyboard, ADMIN_ID, MANAGER_ID
from utils.decorators import user_registered_required
from handlers.history_handler import get_history_keyboard
from handlers.top_handler import get_top_filter_keyboard, get_top_keyboard, get_top_title


MOVIES_PER_PAGE = 15


async def _safe_answer(query, *args, **kwargs) -> bool:
    try:
        await query.answer(*args, **kwargs)
        return True
    except BadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            return False
        raise


async def get_movies_by_filter(filter_type: str, filter_value: str, page: int = 1):
    """Filtrlangan kinolarni olish"""
    offset = (page - 1) * MOVIES_PER_PAGE

    if filter_type == "genre":
        genre = await Genre.get_or_none(genre_id=int(filter_value))
        if not genre:
            return [], 0, 0
        movies_query = Movie.filter(movie_genre=genre)
    elif filter_type == "year":
        movies_query = Movie.filter(movie_year=int(filter_value))
    elif filter_type == "search":
        movies_query = Movie.filter(movie_name__icontains=filter_value)
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

        title = ""
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

    # Kino tanlash - darhol video yuborish
    elif data.startswith("umovie_"):
        movie_id = int(data.split("_")[1])
        movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related('movie_genre', 'movie_country')

        user_id = update.effective_user.id

        if not movie:
            await query.edit_message_text("⚠️ Kino topilmadi.")
            return

        # Tarixga yozish va User olish
        user = await User.get(telegram_id=user_id)

        history, created = await UserMovieHistory.get_or_create(user=user, movie=movie)
        if not created:
            await history.save()

        # Janrlar ro'yxati
        genres = await movie.movie_genre.all()
        genres_text = ", ".join([g.name for g in genres]) if genres else "Nomalum"

        # Davlatlar ro'yxati
        countries = await movie.movie_country.all()
        countries_text = ", ".join([c.name for c in countries]) if countries else "Nomalum"

        # Kino ma'lumotlari
        movie_info = (
            f"🎬 <b>{movie.movie_name}</b>\n\n"
            f"📅 <b>Yil:</b> {movie.movie_year or 'Nomalum'}\n"
            f"🎭 <b>Janr:</b> {genres_text}\n"
            f"🌍 <b>Davlat:</b> {countries_text}\n"
            f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
            f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else 'Nomalum'}\n"
            f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else 'Nomalum'}\n"
            f"⭐ <b>Reyting:</b> {movie.average_rating}/5 ({movie.rating_count} ovoz)\n"
        )

        if movie.movie_description:
            desc = movie.movie_description[:300] + ('...' if len(movie.movie_description or '') > 300 else '')
            movie_info += f"\n📝 <b>Tavsif:</b> {desc}\n"

        movie_info += f"\n📥 <b>Kod:</b> <code>{movie.movie_code}</code>"

        # Xabarni o'chirish
        await query.delete_message()

        # Tugmalar (Baholash va Admin)
        btns = []

        # Baholash
        has_rated = await Rating.exists(user=user, movie=movie)
        if not has_rated:
            btns.append([InlineKeyboardButton("⭐ Baholash", callback_data=f"rate_movie_{movie.movie_id}")])

        # Admin tahrirlash
        if str(user.user_type) == 'admin' or user_id in (ADMIN_ID, MANAGER_ID):
            btns.append([InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_movie_{movie.movie_id}")])

        reply_markup = InlineKeyboardMarkup(btns) if btns else None

        # Video yuborish (ma'lumot bilan)
        if movie.file_id:
            try:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=movie.file_id,
                    caption=movie_info,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            except BadRequest:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=movie_info + "\n\n⚠️ Video fayli yaroqsiz yoki o'chirilgan.",
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=movie_info + "\n\n⚠️ Video fayl topilmadi.",
                parse_mode="HTML",
                reply_markup=reply_markup
            )

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
        if len(parts) == 3 and parts[2].isdigit():
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

        btns = [
             [
                 InlineKeyboardButton("1 ⭐", callback_data=f"set_rating_{movie_id}_1"),
                 InlineKeyboardButton("2 ⭐", callback_data=f"set_rating_{movie_id}_2"),
                 InlineKeyboardButton("3 ⭐", callback_data=f"set_rating_{movie_id}_3"),
                 InlineKeyboardButton("4 ⭐", callback_data=f"set_rating_{movie_id}_4"),
                 InlineKeyboardButton("5 ⭐", callback_data=f"set_rating_{movie_id}_5"),
             ],
             [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"cancel_rating_{movie_id}")]
        ]
        keyboard = InlineKeyboardMarkup(btns)

        # Caption borligini tekshirish
        caption = query.message.caption_html if query.message.caption else ""

        if query.message.caption:
            await query.edit_message_caption(
                caption=caption + "\n\n👇 <b>Kino uchun baho bering:</b>",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
             await query.edit_message_text(
                 text=query.message.text_html + "\n\n👇 <b>Kino uchun baho bering:</b>",
                 reply_markup=keyboard,
                 parse_mode="HTML"
             )

    # Baholashni bekor qilish
    elif data.startswith("cancel_rating_"):
        movie_id = int(data.split("_")[2])
        user_id = update.effective_user.id

        movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related('movie_genre', 'movie_country')
        user = await User.get_or_none(telegram_id=user_id)

        if not movie or not user:
            await _safe_answer(query, "⚠️ Xatolik yuz berdi.", show_alert=True)
            return

        genres = await movie.movie_genre.all()
        genres_text = ", ".join([g.name for g in genres]) if genres else "Nomalum"
        countries = await movie.movie_country.all()
        countries_text = ", ".join([c.name for c in countries]) if countries else "Nomalum"

        movie_info = (
            f"🎬 <b>{movie.movie_name}</b>\n\n"
            f"📅 <b>Yil:</b> {movie.movie_year or 'Nomalum'}\n"
            f"🎭 <b>Janr:</b> {genres_text}\n"
            f"🌍 <b>Davlat:</b> {countries_text}\n"
            f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
            f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else 'Nomalum'}\n"
            f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else 'Nomalum'}\n"
            f"⭐ <b>Reyting:</b> {movie.average_rating}/5 ({movie.rating_count} ovoz)\n"
        )
        if movie.movie_description:
            desc = movie.movie_description[:300] + ('...' if len(movie.movie_description or '') > 300 else '')
            movie_info += f"\n📝 <b>Tavsif:</b> {desc}\n"
        movie_info += f"\n📥 <b>Kod:</b> <code>{movie.movie_code}</code>"

        btns = []
        has_rated = await Rating.exists(user=user, movie=movie)
        if not has_rated:
            btns.append([InlineKeyboardButton("⭐ Baholash", callback_data=f"rate_movie_{movie.movie_id}")])
        if str(user.user_type) == 'admin' or user_id in (ADMIN_ID, MANAGER_ID):
            btns.append([InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_movie_{movie.movie_id}")])
        reply_markup = InlineKeyboardMarkup(btns) if btns else None

        if query.message.caption:
            await query.edit_message_caption(
                caption=movie_info,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                text=movie_info,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

    # Bahoni saqlash
    elif data.startswith("set_rating_"):
        parts = data.split("_")
        movie_id = int(parts[2])
        score = int(parts[3])
        user_id = update.effective_user.id

        movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related('movie_genre', 'movie_country')
        user = await User.get_or_none(telegram_id=user_id)

        if not movie or not user:
            await _safe_answer(query, "⚠️ Xatolik yuz berdi.", show_alert=True)
            return

        if await Rating.exists(user=user, movie=movie):
            await _safe_answer(query, "⚠️ Siz allaqachon ovoz bergansiz!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        await Rating.create(user=user, movie=movie, score=score)

        movie.total_rating_sum += score
        movie.rating_count += 1
        await movie.save()

        await _safe_answer(query, f"✅ {score} ⭐ baho qo'yildi!", show_alert=True)

        new_rating_text = f"⭐ <b>Reyting:</b> {movie.average_rating}/5 ({movie.rating_count} ovoz)"

        genres = await movie.movie_genre.all()
        genres_text = ", ".join([g.name for g in genres]) if genres else "Nomalum"
        countries = await movie.movie_country.all()
        countries_text = ", ".join([c.name for c in countries]) if countries else "Nomalum"

        new_caption = (
            f"🎬 <b>{movie.movie_name}</b>\n\n"
            f"📅 <b>Yil:</b> {movie.movie_year or 'Nomalum'}\n"
            f"🎭 <b>Janr:</b> {genres_text}\n"
            f"🌍 <b>Davlat:</b> {countries_text}\n"
            f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
            f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else 'Nomalum'}\n"
            f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else 'Nomalum'}\n"
            f"{new_rating_text}\n"
        )
        if movie.movie_description:
            desc = movie.movie_description[:300] + ('...' if len(movie.movie_description or '') > 300 else '')
            new_caption += f"\n📝 <b>Tavsif:</b> {desc}\n"
        new_caption += f"\n📥 <b>Kod:</b> <code>{movie.movie_code}</code>"

        if query.message.caption:
            await query.edit_message_caption(
                caption=new_caption,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                text=new_caption,
                reply_markup=None,
                parse_mode="HTML"
            )

    # Noop
    elif data == "noop":
        await _safe_answer(query)
