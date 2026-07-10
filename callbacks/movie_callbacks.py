from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Movie, Genre, Countries
from admins import get_movies_keyboard, send_movie_chart
from utils import get_movies_page, ADMIN_ID, MANAGER_ID


async def movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")

    # movie_{id} - View Movie
    if len(parts) == 2:
        movie_id = parts[1]
        movie = await Movie.get_or_none(movie_id=int(movie_id)).prefetch_related('movie_genre', 'movie_country')

        if not movie:
            await query.edit_message_text("⚠️ Kino topilmadi.")
            return

        # Janrlar
        genres = await movie.movie_genre.all().order_by('name')
        genres_text = ", ".join([g.name for g in genres]) if genres else "Nomalum"

        # Davlatlar
        countries = await movie.movie_country.all().order_by('name')
        countries_text = ", ".join([c.name for c in countries]) if countries else "Nomalum"

        text = (
            f"🎬 <b>{movie.movie_name}</b>\n\n"
            f"🔢 <b>Kodi:</b> {movie.movie_code}\n"
            f"📅 <b>Yili:</b> {movie.movie_year}\n"
            f"🎭 <b>Janr:</b> {genres_text}\n"
            f"🌍 <b>Davlat:</b> {countries_text}\n"
            f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
            f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else 'Nomalum'}\n"
            f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else 'Nomalum'}\n"
            f"⭐ <b>Reyting:</b> {movie.average_rating}\n\n"
            f"📝 <b>Tavsif:</b> {movie.movie_description or 'Mavjud emas'}"
        )

        btns = [
             [InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_movie_{movie.movie_id}")],
             [InlineKeyboardButton("📈 Ko'rishlar grafigi", callback_data=f"movie_chart_{movie.movie_id}")],
             [InlineKeyboardButton("🔙 Ortga", callback_data=f"movie_page_{context.user_data.get('MOVIE_PAGE', 1)}")]
        ]

        if movie.file_id:
             await context.bot.send_video(
                 chat_id=update.effective_chat.id,
                 video=movie.file_id,
                 caption=text,
                 parse_mode="HTML",
                 reply_markup=InlineKeyboardMarkup(btns)
             )
             await query.delete_message()
        else:
             await query.edit_message_text(
                 text=text,
                 parse_mode="HTML",
                 reply_markup=InlineKeyboardMarkup(btns)
             )
        return

    # movie_chart_{id} - Ko'rishlar grafigi
    if len(parts) == 3 and parts[1] == "chart":
        movie_id = int(parts[2])
        movie = await Movie.get_or_none(movie_id=movie_id)
        if not movie:
            await query.answer("⚠️ Kino topilmadi.", show_alert=True)
            return
        await send_movie_chart(update, context, movie)
        return

    # movie_page_{page} - Pagination
    if len(parts) == 3 and parts[1] == "page":
        value = parts[2]
        page = int(value)
        context.user_data["MOVIE_PAGE"] = page

        data = await get_movies_page(page)

        keyboard = get_movies_keyboard(
            data["movies"],
            data["page"],
            data["has_prev"],
            data["has_next"]
        )

        await query.edit_message_reply_markup(reply_markup=keyboard)
