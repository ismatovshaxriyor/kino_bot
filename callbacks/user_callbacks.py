from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from math import ceil

from database import Genre, Movie
from utils import user_keyboard


MOVIES_PER_PAGE = 5


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


async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User qidiruv callbacklari"""
    query = update.callback_query
    await query.answer()
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

    # Kino tanlash - darhol video yuborish
    elif data.startswith("umovie_"):
        movie_id = int(data.split("_")[1])
        movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related('movie_genre', 'movie_country')

        if not movie:
            await query.edit_message_text("⚠️ Kino topilmadi.")
            return

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
            f"⭐ <b>Reyting:</b> {movie.average_rating}/10 ({movie.rating_count} ovoz)\n"
        )

        if movie.movie_description:
            desc = movie.movie_description[:300] + ('...' if len(movie.movie_description or '') > 300 else '')
            movie_info += f"\n📝 <b>Tavsif:</b> {desc}\n"

        movie_info += f"\n📥 <b>Kod:</b> <code>{movie.movie_code}</code>"

        # Xabarni o'chirish
        await query.delete_message()

        # Video yuborish (ma'lumot bilan)
        if movie.file_id:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=movie.file_id,
                caption=movie_info,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=movie_info + "\n\n⚠️ Video fayl topilmadi.",
                parse_mode="HTML"
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

    # Noop
    elif data == "noop":
        pass
