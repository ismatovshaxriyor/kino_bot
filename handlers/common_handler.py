import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from datetime import date
from math import ceil

from services import ai_assistant
from database import User, Movie, UserMovieHistory
from utils import error_notificator
from utils.settings import MOVIES_PER_PAGE
from utils.decorators import channel_subscription_required, user_registered_required
from utils.movie_card import build_movie_card, build_parts_list_card, get_child_parts

DAILY_LIMIT = 3

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
    if not update.message or not update.message.text:
        return

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
            # AI client sinxron (requests + time.sleep) — event-loopni bloklamaslik
            # uchun alohida threadda ishga tushiramiz.
            response = await asyncio.to_thread(ai_assistant.get_movie_recommendation, user_message)

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
        text = update.message.text.strip()

        if not text.isdecimal():
            return

        movie_code = int(text)
        movie = await Movie.get_or_none(movie_code=movie_code)

        if not movie:
            await update.message.reply_text(
                f"📭 <b>{movie_code}</b> kodli kino topilmadi.\n\n"
                "🔄 Boshqa kod bilan urinib ko'ring.",
                parse_mode="HTML"
            )
            return

        user = await User.get(telegram_id=update.effective_user.id)
        history, created = await UserMovieHistory.get_or_create(user=user, movie=movie)
        if not created:
            await history.save()

        # Qismli kino — qismlar ro'yxatini ko'rsatish
        child_parts = await get_child_parts(movie)
        if child_parts:
            parts_text, markup = build_parts_list_card(movie, child_parts)
            await update.message.reply_text(parts_text, reply_markup=markup, parse_mode="HTML")
            return

        # Qismsiz kino — video + karta
        caption, reply_markup = await build_movie_card(
            movie,
            user=user,
            user_id=update.effective_user.id,
            bot_username=context.bot.username,
        )

        if movie.file_id:
            try:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=movie.file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
            except BadRequest as e:
                await error_notificator.notify(context, e, update)
                await update.message.reply_text(
                    caption + "\n\n⚠️ Video fayli yaroqsiz yoki o'chirilgan.",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
        else:
            await update.message.reply_text(
                caption + "\n\n⚠️ Video fayli hali yuklanmagan.",
                parse_mode="HTML"
            )
