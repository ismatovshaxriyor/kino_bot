from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from datetime import date
from math import ceil

from services import ai_assistant
from database import User, Movie, UserMovieHistory, Rating
from utils import error_notificator, ADMIN_ID, MANAGER_ID
from utils.decorators import channel_subscription_required, user_registered_required

DAILY_LIMIT = 3
MOVIES_PER_PAGE = 15

async def can_use_ai(user: User) -> bool:
    today = date.today()

    if user.ai_usage_date != today:
        user.ai_usage = 0
        user.ai_usage_date = today
        await user.save()

    return user.ai_usage < DAILY_LIMIT

async def increase_ai_usage(user: User):
    user.ai_usage += 1
    await user.save()

@user_registered_required
@channel_subscription_required
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')

    if state and state not in ["SEARCH_BY_NAME", "CHAT_WITH_AI"]:
        # Admin/manager text states are handled in admins.common_handler
        from admins.common_handler import general_message_handler
        await general_message_handler(update, context)
        return

    if state == "SEARCH_BY_NAME":
        search_query = update.message.text.strip()

        if len(search_query) < 2:
            await update.message.reply_text(
                "⚠️ Kamida 2 ta harf kiriting!",
                parse_mode="HTML"
            )
            return

        # Kinolarni qidirish
        movies_query = Movie.filter(movie_name__icontains=search_query, parent_movie=None)
        total = await movies_query.count()

        if total == 0:
            await update.message.reply_text(
                f"📭 <b>\"{search_query}\"</b> bo'yicha kinolar topilmadi.\n\n"
                "🔄 Boshqa nom bilan qidiring yoki /start bosing.",
                parse_mode="HTML"
            )
            return

        total_pages = ceil(total / MOVIES_PER_PAGE)
        movies = await movies_query.limit(MOVIES_PER_PAGE)

        # Tugmalar
        btns = []
        for movie in movies:
            rating = f"⭐ {movie.average_rating}" if movie.rating_count > 0 else ""
            btns.append([InlineKeyboardButton(
                f"🎬 {movie.movie_name} ({movie.movie_year or '?'}) {rating}",
                callback_data=f"umovie_{movie.movie_id}"
            )])

        # Pagination
        if total_pages > 1:
            btns.append([InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="noop"),
                        InlineKeyboardButton("▶️", callback_data=f"upage_search_{search_query}_2")])

        btns.append([InlineKeyboardButton("🔙 Ortga", callback_data="user_back")])
        keyboard = InlineKeyboardMarkup(btns)

        context.user_data['state'] = None

        await update.message.reply_text(
            f"🔍 <b>\"{search_query}\"</b> bo'yicha natijalar:\n\n"
            f"📊 Jami: {total} ta kino",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif state == "CHAT_WITH_AI":
        user_message = update.message.text
        chat_id = update.effective_chat.id
        user = await User.get(telegram_id=update.effective_user.id)

        if not await can_use_ai(user):
            await update.message.reply_text(
                "❌ Sizning bugungi AI'dan foydalanish limitingiz tugadi.\n"
                "⏳ Ertaga yana urinib ko'ring."
            )
            return

        await update.message.chat.send_action(action="typing")

        try:
            response = ai_assistant.get_movie_recommendation(user_message)

            try:
                await context.bot.send_message(chat_id, response, parse_mode="Markdown")
                await increase_ai_usage(user)
            except Exception as e:
                await error_notificator.notify(context, e, update)
                await context.bot.send_message(chat_id, response)

        except Exception as e:
            await error_notificator.notify(context, e, update)


    else:
        # Kod orqali qidirish (state = None bo'lganda raqam yuborilsa)
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()

        if text.isdigit():
            movie_code = int(text)
            movie = await Movie.get_or_none(movie_code=movie_code).prefetch_related('movie_genre', 'movie_country')

            if movie:
                # Qismlarni tekshirish (bolalar kinolar)
                child_parts = await Movie.filter(parent_movie=movie).order_by('part_number')
                parts_count = len(child_parts)

                if parts_count > 0:
                    # Qismli kino — qismlar ro'yxatini ko'rsatish
                    # Ota-kino ham 1-qism hisoblanadi agar file_id bor bo'lsa
                    all_parts = []
                    if movie.file_id:
                        all_parts.append((movie, 1, f"1-qism"))
                    for part in child_parts:
                        label = f"{part.part_number}-qism"
                        all_parts.append((part, part.part_number, label))

                    movie_info = (
                        f"🎬 <b>{movie.movie_name}</b>\n\n"
                        f"📀 <b>Qismlar soni:</b> {len(all_parts)} ta\n\n"
                        f"👇 Qaysi qismni ko'rmoqchisiz?"
                    )

                    btns = []
                    row = []
                    for part_movie, num, label in all_parts:
                        row.append(InlineKeyboardButton(f"▶️ {label}", callback_data=f"uwatch_{part_movie.movie_id}"))
                        if len(row) == 3:
                            btns.append(row)
                            row = []
                    if row:
                        btns.append(row)

                    # Tarixga yozish
                    user_id = update.effective_user.id
                    user = await User.get(telegram_id=user_id)
                    history, created = await UserMovieHistory.get_or_create(user=user, movie=movie)
                    if not created:
                        await history.save()

                    reply_markup = InlineKeyboardMarkup(btns)
                    await update.message.reply_text(movie_info, reply_markup=reply_markup, parse_mode="HTML")
                    return

                # Qismsiz kino — hozirgi mantiq
                # Janrlar ro'yxati
                genres = await movie.movie_genre.all()
                genres_text = ", ".join([g.name for g in genres]) if genres else "Noma'lum"

                # Davlatlar ro'yxati
                countries = await movie.movie_country.all()
                countries_text = ", ".join([c.name for c in countries]) if countries else "Noma'lum"

                # Kino ma'lumotlari
                movie_info = (
                    f"🎬 <b>{movie.movie_name}</b>\n\n"
                    f"📅 <b>Yil:</b> {movie.movie_year or 'Nomalum'}\n"
                    f"🎭 <b>Janr:</b> {genres_text}\n"
                    f"🌍 <b>Davlat:</b> {countries_text}\n"
                    f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
                    f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else 'Nomalum'}\n"
                    f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else 'Nomalum'}\n"
                    f"⭐ <b>Reyting:</b> {movie.average_rating}/5 ({movie.rating_count} ovoz)\n\n"
                )

                if movie.movie_description:
                    movie_info += f"📝 <b>Tavsif:</b>\n{movie.movie_description[:500]}{'...' if len(movie.movie_description or '') > 500 else ''}\n\n"

                # Tarixga yozish
                user_id = update.effective_user.id
                user = await User.get(telegram_id=user_id)

                history, created = await UserMovieHistory.get_or_create(user=user, movie=movie)
                if not created:
                    await history.save()

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

                # Video yuborish
                if movie.file_id:
                    try:
                        await context.bot.send_video(
                            chat_id=update.effective_chat.id,
                            video=movie.file_id,
                            caption=movie_info,
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        )
                    except BadRequest as e:
                        await error_notificator.notify(context, e, update)
                        await update.message.reply_text(
                            movie_info + "\n\n⚠️ Video fayli yaroqsiz yoki o'chirilgan.",
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                else:
                    await update.message.reply_text(
                        movie_info + "\n\n⚠️ Video fayli hali yuklanmagan.",
                        parse_mode="HTML"
                    )
            else:
                await update.message.reply_text(
                    f"📭 <b>{movie_code}</b> kodli kino topilmadi.\n\n"
                    "🔄 Boshqa kod bilan urinib ko'ring.",
                    parse_mode="HTML"
                )
