from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, ContextTypes, CommandHandler, filters
from telegram import ReplyKeyboardMarkup, Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from html import escape

from utils import admin_required, admin_btns, error_notificator, ADMIN_ID, MANAGER_ID
from database import Movie, Genre, Countries, QualityEnum, LanguageEnum


ADD_MOVIE, GET_CODE, GET_NAME, GET_GENRE, GET_COUNTRY, GET_YEAR, GET_QUALITY, GET_LANGUAGE, GET_DURATION, GET_DESCRIPTION, SAVE_DATA = range(11)
admin_keyboard = ReplyKeyboardMarkup(
        admin_btns,
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        user_id = update.effective_chat.id
        if user_id == ADMIN_ID or user_id == MANAGER_ID:
            admin_btns.insert(-1, [KeyboardButton("👤 Managerlar")])
        await update.message.reply_text(
            "❌ <b>Kino qo'shish bekor qilindi.</b>",
            reply_markup=admin_keyboard,
            parse_mode="HTML",
        )
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ <b>Kino qo'shish bekor qilindi.</b>", parse_mode="HTML")

    context.user_data.clear()
    return ConversationHandler.END


@admin_required
async def add_movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_sp = query.data.split(":")

    if data_sp[1] == 'add':
        await query.message.delete()

        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✍️ **Kino kodini kiriting:**",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
            direct=True
        )

        if msg:
            context.user_data["last_msg"] = msg.message_id
        context.user_data['state'] = 'ADD_MOVIE'
        return ADD_MOVIE


async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_code = update.message.text.strip()

    if not movie_code.isdigit():
        await update.message.reply_text("⚠️ <b>Iltimos, faqat raqam kiriting.</b>", parse_mode="HTML")
        return ADD_MOVIE

    context.user_data["movie_code"] = movie_code

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    await update.message.delete()

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🎬 <b>Yangi kino nomini kiriting:</b>",
        parse_mode="HTML",
        direct=True
    )

    if msg:
        context.user_data['last_msg'] = msg.message_id
    return GET_CODE


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movie_name = update.message.text
    context.user_data["movie_name"] = movie_name

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    await update.message.delete()

    genres = await Genre.all()
    genre_btns = []

    if genres:
        btns = []
        for i, genre in enumerate(genres):
            btn = InlineKeyboardButton(text=f"{genre.name}", callback_data=f"movie:genre:{genre.genre_id}")
            btns.append(btn)
            if i % 2 == 1:
                genre_btns.append(btns)
                btns = []

        if btns:
            genre_btns.append(btns)
        keyboard = InlineKeyboardMarkup(genre_btns)

        msg = await context.bot.send_message(
            update.effective_chat.id,
            "🎭 <b>Janrlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.",
            reply_markup=keyboard,
            parse_mode="HTML",
            direct=True,
        )
        if msg:
            context.user_data['last_msg'] = msg.message_id
        return GET_NAME
    else:
        await update.message.reply_text(
            "📭 <b>Janrlar topilmadi.</b>\n\nAvval janr qo'shing.",
            reply_markup=admin_keyboard,
            parse_mode="HTML",
        )
        return ConversationHandler.END


async def get_genre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    _, action, data = query.data.split(":")

    if action == "genre":
        if data.isdigit():
            data = int(data)
            genres = context.user_data.setdefault("genres", [])
            if data in genres:
                genres.remove(data)
            else:
                genres.append(data)

            genres = await Genre.all()
            genre_btns = []

            movie_genres = context.user_data["genres"]
            if genres:
                btns = []
                for i, genre in enumerate(genres):
                    btn = InlineKeyboardButton(text=f"{"✅" if genre.genre_id in movie_genres else ""} {genre.name}", callback_data=f"movie:genre:{genre.genre_id}")
                    btns.append(btn)
                    if i % 2 == 1:
                        genre_btns.append(btns)
                        btns = []

                if btns:
                    genre_btns.append(btns)
                genre_btns += [[InlineKeyboardButton("✅ Tasdiqlash", callback_data="movie:genre:confirm")]]
                keyboard = InlineKeyboardMarkup(genre_btns)

                msg = await context.bot.send_message(
                    update.effective_chat.id,
                    "🎭 <b>Janrlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    direct=True,
                )
                if msg:
                    context.user_data['last_msg'] = msg.message_id
                return GET_NAME
        elif data == 'confirm':
            countries = await Countries.all()
            country_btns = []

            if countries:
                btns = []
                for i, country in enumerate(countries):
                    btn = InlineKeyboardButton(text=f"{country.name}", callback_data=f"movie:country:{country.country_id}")
                    btns.append(btn)
                    if i % 2 == 1:
                        country_btns.append(btns)
                        btns = []

                if btns:
                    country_btns.append(btns)
                keyboard = InlineKeyboardMarkup(country_btns)

                msg = await context.bot.send_message(
                    update.effective_chat.id,
                    "🌍 <b>Davlatlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    direct=True,
                )
                context.user_data['last_msg'] = msg.message_id
                return GET_GENRE
            else:
                await query.message.reply_text(
                    "📭 <b>Davlatlar topilmadi.</b>\n\nAvval davlat qo'shing.",
                    reply_markup=admin_keyboard,
                    parse_mode="HTML",
                )
                return ConversationHandler.END


async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    _, action, data = query.data.split(":")

    if action == "country":
        if data.isdigit():
            data = int(data)
            countries = context.user_data.setdefault("countries", [])
            if data in countries:
                countries.remove(data)
            else:
                countries.append(data)

            countries = await Countries.all()
            country_btns = []

            movie_countries = context.user_data["countries"]
            if countries:
                btns = []
                for i, country in enumerate(countries):
                    btn = InlineKeyboardButton(text=f"{"✅" if country.country_id in movie_countries else ""} {country.name}", callback_data=f"movie:country:{country.country_id}")
                    btns.append(btn)
                    if i % 2 == 1:
                        country_btns.append(btns)
                        btns = []

                if btns:
                    country_btns.append(btns)
                country_btns += [[InlineKeyboardButton("✅ Tasdiqlash", callback_data="movie:country:confirm")]]
                keyboard = InlineKeyboardMarkup(country_btns)

                msg = await context.bot.send_message(
                    update.effective_chat.id,
                    "🌍 <b>Davlatlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    direct=True,
                )
                if msg:
                    context.user_data['last_msg'] = msg.message_id
                return GET_GENRE
        elif data == 'confirm':
            msg = await context.bot.send_message(
                update.effective_chat.id,
                "📅 <b>Kino yilini kiriting:</b>\n\nMasalan: <code>2024</code>",
                parse_mode="HTML",
                direct=True,
            )
            if msg:
                context.user_data['last_msg'] = msg.message_id
            return GET_COUNTRY


async def get_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    movie_year = update.message.text
    if not movie_year.isdigit():
        msg = await context.bot.send_message(
            update.effective_chat.id,
            "⚠️ <b>Iltimos, yilni faqat son ko'rinishida kiriting.</b>",
            parse_mode="HTML",
            direct=True,
        )
        if msg:
            context.user_data['last_msg'] = msg.message_id
        return GET_COUNTRY

    context.user_data['movie_year'] = int(movie_year)

    qualities = [
            [
            InlineKeyboardButton(
                text=quality.value,
                callback_data=f"quality:{quality.value}"
            )
        ]
        for quality in QualityEnum
    ]
    keyboard = InlineKeyboardMarkup(qualities)

    msg = await context.bot.send_message(
        update.effective_chat.id,
        "📺 <b>Kino sifatini tanlang:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
        direct=True,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return GET_YEAR


async def get_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, quantity = query.data.split(":")

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    context.user_data['quatity'] = quantity

    language_btn = [
        [
            InlineKeyboardButton(
                text=language.value,
                callback_data=f"language:{language.value}"
            )
        ]
        for language in LanguageEnum
    ]

    keyboard = InlineKeyboardMarkup(language_btn)

    msg = await context.bot.send_message(
        update.effective_chat.id,
        "🗣 <b>Kino tilini tanlang:</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
        direct=True,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return GET_QUALITY


async def get_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, language = query.data.split(":")

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    context.user_data['language'] = language

    msg = await context.bot.send_message(
        update.effective_chat.id,
        "⏱ <b>Kino davomiyligini kiriting (minutlarda):</b>\n\nBo'sh qoldirish uchun <code>.</code> yuboring.",
        parse_mode="HTML",
        direct=True,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return GET_LANGUAGE


async def get_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    movie_duration = update.message.text
    if not movie_duration.isdigit() and movie_duration != ".":
        msg = await context.bot.send_message(
            update.effective_chat.id,
            "⚠️ <b>Iltimos, faqat son yoki <code>.</code> kiriting.</b>",
            parse_mode="HTML",
            direct=True,
        )
        if msg:
            context.user_data['last_msg'] = msg.message_id
        return GET_LANGUAGE

    if movie_duration != '.':
        context.user_data['movie_duration'] = int(movie_duration)
    else:
        context.user_data['movie_duration'] = movie_duration

    msg = await context.bot.send_message(
        update.effective_chat.id,
        "📝 <b>Kino haqida qisqacha ma'lumot kiriting:</b>\n\nBo'sh qoldirish uchun <code>.</code> yuboring.",
        parse_mode="HTML",
        direct=True,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return GET_DURATION


async def get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        await update.message.delete()

    movie_description = update.message.text
    context.user_data['movie_description'] = movie_description

    msg = await context.bot.send_message(
        update.effective_chat.id,
        "🎞 <b>Endi kino faylini yuboring:</b>",
        parse_mode="HTML",
        direct=True,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return GET_DESCRIPTION


async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    video = update.message.video

    if not video:
        msg = await context.bot.send_message(
            update.effective_chat.id,
            "⚠️ <b>Iltimos, faqat video fayl yuboring.</b>",
            parse_mode="HTML",
            direct=True,
        )
        if msg:
            context.user_data['last_msg'] = msg.message_id
        return GET_DESCRIPTION

    context.user_data['file_id'] = video.file_id

    confirm_btns = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data='movie:confirm:add'),
            InlineKeyboardButton("❌ Bekor qilish", callback_data='movie:reject:add')
        ]
    ]

    keyboard = InlineKeyboardMarkup(confirm_btns)
    genres = await Genre.filter(genre_id__in=context.user_data.get('genres', []))
    genres_name = ", ".join(g.name for g in genres)

    countries = await Countries.filter(country_id__in=context.user_data.get('countries', []))
    countries_name = ", ".join(c.name for c in countries)
    duration_text = (
        escape(str(context.user_data['movie_duration']))
        if context.user_data['movie_duration'] != "."
        else "Ko'rsatilmagan"
    )
    description_text = (
        escape(str(context.user_data['movie_description']))
        if context.user_data['movie_description'] != "."
        else "Ko'rsatilmagan"
    )

    text = (
        f"🎬 <b>Kino ma'lumotlarini tekshiring</b>\n\n"
        f"🏷 <b>Nomi:</b> {escape(str(context.user_data['movie_name']))}\n"
        f"🔢 <b>Kodi:</b> {escape(str(context.user_data['movie_code']))}\n"
        f"🎭 <b>Janrlar:</b> {escape(genres_name or 'Tanlanmagan')}\n"
        f"🌍 <b>Davlatlar:</b> {escape(countries_name or 'Tanlanmagan')}\n"
        f"📅 <b>Yili:</b> {escape(str(context.user_data['movie_year']))}\n"
        f"📺 <b>Sifati:</b> {escape(str(context.user_data['quatity']))}\n"
        f"🗣 <b>Tili:</b> {escape(str(context.user_data['language']))}\n"
        f"⏱ <b>Davomiyligi:</b> {duration_text}\n"
        f"📝 <b>Kino haqida:</b> {description_text}\n\n"
        f"Tasdiqlaysizmi?"
    )

    msg = await context.bot.send_video(
        update.effective_chat.id,
        context.user_data['file_id'],
        caption=text,
        reply_markup=keyboard,
        parse_mode="HTML",
        direct=True,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return SAVE_DATA


async def save_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    _, action, _ = query.data.split(":")

    if action == 'confirm':
        try:
            duration = context.user_data.get('movie_duration')
            description = context.user_data.get('movie_description')

            movie = await Movie.create(
                movie_code=int(context.user_data['movie_code']),
                file_id=context.user_data['file_id'],
                movie_name=context.user_data['movie_name'],
                movie_year=int(context.user_data['movie_year']),
                movie_duration=int(duration) if str(duration).isdigit() else None,
                movie_description=description if description != '.' else None,
                movie_quality=context.user_data.get('quatity'),
                movie_language=context.user_data.get('language')
            )

            genre_ids = context.user_data.get('genres', [])
            if genre_ids:
                genres = await Genre.filter(genre_id__in=genre_ids)
                await movie.movie_genre.add(*genres)

            country_ids = context.user_data.get('countries', [])
            if country_ids:
                countries = await Countries.filter(country_id__in=country_ids)
                await movie.movie_country.add(*countries)

            await query.message.reply_text(
                f"✅ <b>{escape(movie.movie_name)}</b> muvaffaqiyatli bazaga qo'shildi!",
                parse_mode="HTML",
                reply_markup=admin_keyboard,
            )

            context.user_data.clear()
            return ConversationHandler.END

        except Exception as e:

            await error_notificator.notify(context, e, update)

    elif action == 'reject':
        await query.message.reply_text("❌ <b>Jarayon bekor qilindi.</b>", reply_markup=admin_keyboard, parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END



add_movie_conf_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_movie_callback, pattern=r"^movie:add")],
    states={
        ADD_MOVIE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
        GET_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        GET_NAME: [CallbackQueryHandler(get_genre, pattern=r"^movie:genre:")],
        GET_GENRE: [CallbackQueryHandler(get_country, pattern=r"movie:country:")],
        GET_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_year)],
        GET_YEAR: [CallbackQueryHandler(get_quality, pattern=r"quality:")],
        GET_QUALITY: [CallbackQueryHandler(get_language, pattern=r"language:")],
        GET_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_duration)],
        GET_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
        GET_DESCRIPTION: [MessageHandler(filters.VIDEO, get_video)],
        SAVE_DATA: [CallbackQueryHandler(save_data, pattern=r'movie:(confirm|reject):add')]
    },
    fallbacks=[CommandHandler('cancel', cancel_command)],
    per_user=True,
    block=True
)
