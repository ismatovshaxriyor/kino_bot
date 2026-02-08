from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters, CommandHandler

from database import Countries, Genre, LanguageEnum, Movie, QualityEnum
from utils.decorators import admin_required
from utils import error_notificator, get_movies_page
from admins.movie_handlers import get_movies_keyboard

SELECTING_ACTION, WAITING_INPUT = range(2)
EDIT_MENU_PATTERN = (
    r"^(cancel_edit$|delete_confirm$|delete_yes$|delete_no$|"
    r"edit_field_(name|year|code|duration|genres|countries|quality|lang|desc|file)$|"
    r"set_quality_|set_lang_|"
    r"edit_genre_toggle_|edit_country_toggle_|"
    r"edit_genre_confirm$|edit_country_confirm$|"
    r"back_to_menu$)"
)


async def _edit_message(query, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if query.message.caption:
        await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")


def _build_genre_keyboard(genres: list[Genre], selected_ids: list[int]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    selected = set(selected_ids)
    for idx, genre in enumerate(genres):
        mark = "✅ " if genre.genre_id in selected else ""
        row.append(InlineKeyboardButton(f"{mark}{genre.name}", callback_data=f"edit_genre_toggle_{genre.genre_id}"))
        if idx % 2 == 1:
            rows.append(row)
            row = []

    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✅ Tasdiqlash", callback_data="edit_genre_confirm")])
    rows.append([InlineKeyboardButton("🔙 Ortga", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def _build_country_keyboard(countries: list[Countries], selected_ids: list[int]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    selected = set(selected_ids)
    for idx, country in enumerate(countries):
        mark = "✅ " if country.country_id in selected else ""
        row.append(InlineKeyboardButton(f"{mark}{country.name}", callback_data=f"edit_country_toggle_{country.country_id}"))
        if idx % 2 == 1:
            rows.append(row)
            row = []

    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✅ Tasdiqlash", callback_data="edit_country_confirm")])
    rows.append([InlineKeyboardButton("🔙 Ortga", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

@admin_required
async def start_edit_movie(update: Update, context: ContextTypes.DEFAULT_TYPE, movie_id: int = None):
    """Kinoni tahrirlashni boshlash"""
    query = update.callback_query
    await query.answer()

    if movie_id is None:
        movie_id = int(query.data.split("_")[2])
    context.user_data['edit_movie_id'] = movie_id
    context.user_data['state'] = 'EDIT_MOVIE'

    movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related("movie_genre", "movie_country")
    if not movie:
        await _edit_message(query, "❌ Kino topilmadi.")
        context.user_data['state'] = None
        return ConversationHandler.END

    movie_genres = await movie.movie_genre.all()
    movie_countries = await movie.movie_country.all()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 Nomi: {movie.movie_name[:20]}...", callback_data="edit_field_name")],
        [InlineKeyboardButton(f"📅 Yil: {movie.movie_year or '-'}", callback_data="edit_field_year"),
         InlineKeyboardButton(f"📥 Kod: {movie.movie_code}", callback_data="edit_field_code")],
        [InlineKeyboardButton(f"⏱ Davomiylik: {movie.movie_duration or '-'} min", callback_data="edit_field_duration")],
        [InlineKeyboardButton(f"🎭 Janrlar: {len(movie_genres)} ta", callback_data="edit_field_genres"),
         InlineKeyboardButton(f"🌍 Davlatlar: {len(movie_countries)} ta", callback_data="edit_field_countries")],

        [InlineKeyboardButton(f"📺 Sifat: {movie.movie_quality.value if movie.movie_quality else '-'}", callback_data="edit_field_quality"),
         InlineKeyboardButton(f"🗣 Til: {movie.movie_language.value if movie.movie_language else '-'}", callback_data="edit_field_lang")],

        [InlineKeyboardButton("📝 Tavsifni o'zgartirish", callback_data="edit_field_desc")],
        [InlineKeyboardButton("📁 Fayl ID ni o'zgartirish", callback_data="edit_field_file")],

        [InlineKeyboardButton("🗑 O'chirish", callback_data="delete_confirm")],
        [InlineKeyboardButton("🔙 Bekor qilish", callback_data="cancel_edit")]
    ])

    text = f"📝 <b>Kino tahrirlash:</b>\n\n🎬 {movie.movie_name}\n\nO'zgartirmoqchi bo'lgan ma'lumotni tanlang:"

    # Xabarni tahrirlash (Video caption yoki text)
    if query.message.caption:
        await query.edit_message_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")

    return SELECTING_ACTION

async def select_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qaysi maydonni tahrirlashni tanlash"""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Bekor qilish
    if data == "cancel_edit":
        movie_id = context.user_data.get('edit_movie_id')
        await query.delete_message()
        # Kinoni qayta ko'rsatish (user_callback dagi umovie_ logicni chaqirish o'rniga shunchaki xabar)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ Tahrirlash bekor qilindi. Kino ID: {movie_id}. Qayta ko'rish uchun menyuni ishlating.")

        context.user_data['state'] = None
        return ConversationHandler.END

    # O'chirishni so'rash
    if data == "delete_confirm":
        btns = [
            [InlineKeyboardButton("🗑 HA, O'CHIRISH", callback_data="delete_yes")],
            [InlineKeyboardButton("🔙 YO'Q, QAYTISH", callback_data="delete_no")]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btns))
        return SELECTING_ACTION

    # O'chirishni tasdiqlash
    if data == "delete_yes":
        movie_id = context.user_data.get('edit_movie_id')
        movie = await Movie.get_or_none(movie_id=movie_id)
        if movie:
            await movie.delete()
            if query.message.caption:
                await query.edit_message_caption("🗑 <b>Kino muvaffaqiyatli o'chirildi!</b>", parse_mode="HTML", reply_markup=None)
            else:
                await query.edit_message_text("🗑 <b>Kino muvaffaqiyatli o'chirildi!</b>", parse_mode="HTML", reply_markup=None)
        else:
            if query.message.caption:
                await query.edit_message_caption("⚠️ Kino topilmadi.", reply_markup=None)
            else:
                await query.edit_message_text("⚠️ Kino topilmadi.", reply_markup=None)
        return ConversationHandler.END
        context.user_data['state'] = None

    if data == "delete_no":
        movie_id = context.user_data.get('edit_movie_id')
        return await start_edit_movie(update, context, movie_id=movie_id)

    if data == "edit_field_genres":
        movie_id = context.user_data.get("edit_movie_id")
        movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related("movie_genre")
        if not movie:
            await _edit_message(query, "⚠️ Kino topilmadi.")
            return ConversationHandler.END

        genres = await Genre.all()
        if not genres:
            await query.answer("Janrlar ro'yxati bo'sh.", show_alert=True)
            return SELECTING_ACTION

        selected_genres = await movie.movie_genre.all()
        context.user_data["edit_genre_ids"] = [g.genre_id for g in selected_genres]
        keyboard = _build_genre_keyboard(genres, context.user_data["edit_genre_ids"])
        await _edit_message(query, "🎭 <b>Janrlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.", keyboard)
        return SELECTING_ACTION

    if data.startswith("edit_genre_toggle_"):
        genre_id = int(data.split("_")[3])
        selected = context.user_data.setdefault("edit_genre_ids", [])
        if genre_id in selected:
            selected.remove(genre_id)
        else:
            selected.append(genre_id)

        genres = await Genre.all()
        keyboard = _build_genre_keyboard(genres, selected)
        await _edit_message(query, "🎭 <b>Janrlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.", keyboard)
        return SELECTING_ACTION

    if data == "edit_genre_confirm":
        movie_id = context.user_data.get("edit_movie_id")
        movie = await Movie.get_or_none(movie_id=movie_id)
        if not movie:
            await _edit_message(query, "⚠️ Kino topilmadi.")
            return ConversationHandler.END

        selected_ids = context.user_data.pop("edit_genre_ids", [])
        await movie.movie_genre.clear()
        if selected_ids:
            genres = await Genre.filter(genre_id__in=selected_ids)
            await movie.movie_genre.add(*genres)

        await query.answer("✅ Janrlar yangilandi.", show_alert=True)
        return await start_edit_movie(update, context, movie_id=movie_id)

    if data == "edit_field_countries":
        movie_id = context.user_data.get("edit_movie_id")
        movie = await Movie.get_or_none(movie_id=movie_id).prefetch_related("movie_country")
        if not movie:
            await _edit_message(query, "⚠️ Kino topilmadi.")
            return ConversationHandler.END

        countries = await Countries.all()
        if not countries:
            await query.answer("Davlatlar ro'yxati bo'sh.", show_alert=True)
            return SELECTING_ACTION

        selected_countries = await movie.movie_country.all()
        context.user_data["edit_country_ids"] = [c.country_id for c in selected_countries]
        keyboard = _build_country_keyboard(countries, context.user_data["edit_country_ids"])
        await _edit_message(query, "🌍 <b>Davlatlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.", keyboard)
        return SELECTING_ACTION

    if data.startswith("edit_country_toggle_"):
        country_id = int(data.split("_")[3])
        selected = context.user_data.setdefault("edit_country_ids", [])
        if country_id in selected:
            selected.remove(country_id)
        else:
            selected.append(country_id)

        countries = await Countries.all()
        keyboard = _build_country_keyboard(countries, selected)
        await _edit_message(query, "🌍 <b>Davlatlarni tanlang:</b>\n\nTanlanganlarini ✅ bilan belgilang.", keyboard)
        return SELECTING_ACTION

    if data == "edit_country_confirm":
        movie_id = context.user_data.get("edit_movie_id")
        movie = await Movie.get_or_none(movie_id=movie_id)
        if not movie:
            await _edit_message(query, "⚠️ Kino topilmadi.")
            return ConversationHandler.END

        selected_ids = context.user_data.pop("edit_country_ids", [])
        await movie.movie_country.clear()
        if selected_ids:
            countries = await Countries.filter(country_id__in=selected_ids)
            await movie.movie_country.add(*countries)

        await query.answer("✅ Davlatlar yangilandi.", show_alert=True)
        return await start_edit_movie(update, context, movie_id=movie_id)

    # Sifat va Til uchun alohida menyu
    if data == "edit_field_quality":
        btns = [[InlineKeyboardButton(q.value, callback_data=f"set_quality_{q.value}")] for q in QualityEnum]
        btns.append([InlineKeyboardButton("🔙 Ortga", callback_data="back_to_menu")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btns))
        return SELECTING_ACTION

    if data == "edit_field_lang":
        btns = [[InlineKeyboardButton(l.value, callback_data=f"set_lang_{l.value}")] for l in LanguageEnum]
        btns.append([InlineKeyboardButton("🔙 Ortga", callback_data="back_to_menu")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btns))
        return SELECTING_ACTION

    # Sifat/Til ni saqlash
    if data.startswith("set_quality_") or data.startswith("set_lang_"):
        movie_id = context.user_data.get('edit_movie_id')
        movie = await Movie.get_or_none(movie_id=movie_id)

        if data.startswith("set_quality_"):
            val = data.split("_", 2)[2] # set_quality_1080p -> 1080p
            movie.movie_quality = val
            msg = f"✅ Sifat o'zgartirildi: {val}"
        else:
            val = data.split("_", 2)[2]
            movie.movie_language = val
            msg = f"✅ Til o'zgartirildi: {val}"

        await movie.save()
        await query.answer(msg, show_alert=True)
        # Menyuga qaytish
        return await start_edit_movie(update, context, movie_id=movie_id)

    if data == "back_to_menu":
        movie_id = context.user_data.get('edit_movie_id')
        context.user_data.pop("edit_genre_ids", None)
        context.user_data.pop("edit_country_ids", None)
        return await start_edit_movie(update, context, movie_id=movie_id)

    # Text input talab qiladigan fieldlar
    field_map = {
        'edit_field_name': 'Nomi',
        'edit_field_year': 'Yili',
        'edit_field_code': 'Kodi (Dublicate bo\'lmasligi kerak)',
        'edit_field_duration': 'Davomiylik (daqiqada)',
        'edit_field_desc': 'Tavsif',
        'edit_field_file': 'Fayl ID (Video)',
    }

    field_name = field_map.get(data)
    if not field_name:
        return SELECTING_ACTION

    context.user_data['edit_field'] = data

    prompt_text = f"✍️ <b>Yangi {field_name}ni kiriting:</b>\n\n(Bekor qilish uchun /cancel bosing)"
    if query.message.caption:
        await query.edit_message_caption(
            caption=prompt_text,
            reply_markup=None, # Keyboardni olib tashlash
            parse_mode="HTML"
        )
    else:
        await query.edit_message_text(
            text=prompt_text,
            reply_markup=None, # Keyboardni olib tashlash
            parse_mode="HTML"
        )

    return WAITING_INPUT

async def receive_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yangi qiymatni qabul qilish va saqlash"""
    new_value = update.message.text
    movie_id = context.user_data.get('edit_movie_id')
    edit_field = context.user_data.get('edit_field')

    movie = await Movie.get_or_none(movie_id=movie_id)
    if not movie:
        await update.message.reply_text("❌ Kino topilmadi.")
        return ConversationHandler.END

    try:
        if edit_field == 'edit_field_name':
            movie.movie_name = new_value
        elif edit_field == 'edit_field_year':
            if not new_value.isdigit():
                await update.message.reply_text("⚠️ Yil raqam bo'lishi kerak!")
                return WAITING_INPUT
            movie.movie_year = int(new_value)
        elif edit_field == 'edit_field_code':
            if not new_value.isdigit():
                await update.message.reply_text("⚠️ Kod raqam bo'lishi kerak!")
                return WAITING_INPUT
            # Check duplicate
            existing = await Movie.get_or_none(movie_code=int(new_value))
            if existing and existing.movie_id != movie_id:
                await update.message.reply_text("⚠️ Bu kod band!")
                return WAITING_INPUT
            movie.movie_code = int(new_value)
        elif edit_field == 'edit_field_duration':
            if not new_value.isdigit():
                await update.message.reply_text("⚠️ Davomiylik faqat raqam bo'lishi kerak (daqiqada)!")
                return WAITING_INPUT
            movie.movie_duration = int(new_value)
        elif edit_field == 'edit_field_desc':
            movie.movie_description = new_value
        elif edit_field == 'edit_field_file':
            movie.file_id = new_value

        await movie.save()
        await update.message.reply_text("✅ Muvaffaqiyatli saqlandi!")

        # User so'rovi: Kinolar ro'yxatiga qaytish
        page = context.user_data.get('MOVIE_PAGE', 1)
        data = await get_movies_page(page)

        reply_markup = get_movies_keyboard(data['movies'], page, data['has_prev'], data['has_next'])

        await update.message.reply_text(
            f"🎬 <b>Kinolar ro'yxati (Sahifa: {page}):</b>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

        context.user_data['state'] = None
        return ConversationHandler.END

    except Exception as e:
        await error_notificator.notify(context, e, update)

        context.user_data['state'] = None
        return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Tahrirlash bekor qilindi.")

    context.user_data['state'] = None
    return ConversationHandler.END

edit_movie_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_movie, pattern=r"^edit_movie_\d+$")],
    states={
        # Restrict edit flow callbacks, otherwise this conversation can swallow unrelated inline buttons.
        SELECTING_ACTION: [CallbackQueryHandler(select_field_callback, pattern=EDIT_MENU_PATTERN)],
        WAITING_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_value)]
    },
    fallbacks=[CommandHandler('cancel', cancel_edit)],

)
