"""Tezkor kino qo'shish — faqat majburiy maydonlar so'raladi.

To'liq oqimdan (add_movie.py) farqi: janr, davlat, yil, sifat, til va
davomiylik so'ralmaydi. Ular keyinroq "✏️ Tahrirlash" orqali to'ldirilishi mumkin.
Oqim: kod → nom → tavsif → video → tasdiqlash.
"""
from html import escape

from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, ContextTypes, CommandHandler, filters

from utils import admin_required, error_notificator
from utils.admin_btns import get_admin_keyboard
from database import Movie
from admins.add_movie import validate_movie_code, cancel_command, start_from_conv, DEFAULT_LANGUAGE


QUICK_CODE, QUICK_NAME, QUICK_DESCRIPTION, QUICK_VIDEO, QUICK_SAVE = range(5)

MOVIE_NAME_MAX_LEN = 255


async def _cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oldingi bot savolini va foydalanuvchi javobini o'chiradi."""
    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass


async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    msg = await context.bot.send_message(
        update.effective_chat.id,
        text,
        parse_mode="HTML",
        direct=True,  # type: ignore
        **kwargs,
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id


@admin_required
async def quick_add_movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()

    await _ask(
        update, context,
        "⚡ <b>Tezkor kino qo'shish</b>\n\n"
        "Faqat asosiy ma'lumotlar so'raladi, til avtomatik «O'zbek tilida» bo'ladi. "
        "Janr, davlat, yil va sifatni "
        "keyinroq ✏️ Tahrirlash orqali qo'shishingiz mumkin.\n\n"
        "✍️ <b>Kino kodini kiriting:</b>",
        reply_markup=ReplyKeyboardRemove(),
    )
    return QUICK_CODE


async def quick_get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    movie_code = await validate_movie_code(update)
    if movie_code is None:
        return QUICK_CODE

    context.user_data['movie_code'] = movie_code

    await _cleanup(update, context)
    await _ask(update, context, "🎬 <b>Kino nomini kiriting:</b>")
    return QUICK_NAME


async def quick_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    movie_name = update.message.text.strip()
    if len(movie_name) > MOVIE_NAME_MAX_LEN:
        await update.message.reply_text(
            f"⚠️ <b>Nom juda uzun</b> (maksimal {MOVIE_NAME_MAX_LEN} belgi). Qisqaroq kiriting:",
            parse_mode="HTML",
        )
        return QUICK_NAME

    context.user_data['movie_name'] = movie_name

    await _cleanup(update, context)
    await _ask(
        update, context,
        "📝 <b>Kino haqida qisqacha ma'lumot kiriting:</b>\n\nBo'sh qoldirish uchun <code>.</code> yuboring.",
    )
    return QUICK_DESCRIPTION


async def quick_get_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    description = update.message.text.strip()
    context.user_data['movie_description'] = description if description != '.' else None

    await _cleanup(update, context)
    await _ask(update, context, "🎞 <b>Endi kino faylini yuboring:</b>")
    return QUICK_VIDEO


async def quick_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("⚠️ <b>Iltimos, video fayl yuboring.</b>", parse_mode="HTML")
        return QUICK_VIDEO

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    context.user_data['file_id'] = video.file_id

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data='movie:quick_confirm'),
        InlineKeyboardButton("❌ Bekor qilish", callback_data='movie:quick_reject'),
    ]])

    description = context.user_data.get('movie_description')
    description_text = escape(description) if description else "Ko'rsatilmagan"
    text = (
        f"⚡ <b>Kino ma'lumotlarini tekshiring</b>\n\n"
        f"🏷 <b>Nomi:</b> {escape(context.user_data['movie_name'])}\n"
        f"🔢 <b>Kodi:</b> {escape(context.user_data['movie_code'])}\n"
        f"🗣 <b>Tili:</b> {DEFAULT_LANGUAGE.value}\n"
        f"📝 <b>Kino haqida:</b> {description_text}\n\n"
        f"Tasdiqlaysizmi?"
    )

    msg = await context.bot.send_video(
        update.effective_chat.id,
        video.file_id,
        caption=text,
        reply_markup=keyboard,
        parse_mode="HTML",
        direct=True,  # type: ignore
    )
    if msg:
        context.user_data['last_msg'] = msg.message_id
    return QUICK_SAVE


async def quick_save_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        last_msg = context.user_data.get('last_msg')
        if last_msg:
            await context.bot.delete_message(update.effective_chat.id, last_msg)
    except Exception as e:
        await error_notificator.notify(context, e, update)

    chat_id = update.effective_chat.id

    if query.data == 'movie:quick_reject':
        await query.message.reply_text(
            "❌ <b>Jarayon bekor qilindi.</b>",
            reply_markup=get_admin_keyboard(chat_id),
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        movie = await Movie.create(
            movie_code=int(context.user_data['movie_code']),
            file_id=context.user_data['file_id'],
            movie_name=context.user_data['movie_name'],
            movie_description=context.user_data.get('movie_description'),
            movie_language=DEFAULT_LANGUAGE,
        )
    except Exception as e:
        await error_notificator.notify(context, e, update)
        await query.message.reply_text(
            "⚠️ <b>Kinoni saqlashda xatolik yuz berdi.</b> Qaytadan urinib ko'ring.",
            reply_markup=get_admin_keyboard(chat_id),
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    await query.message.reply_text(
        f"✅ <b>{escape(movie.movie_name)}</b> muvaffaqiyatli bazaga qo'shildi!\n\n"
        f"Qolgan ma'lumotlarni 🎬 Kinolar → kino → ✏️ Tahrirlash orqali to'ldirishingiz mumkin.",
        reply_markup=get_admin_keyboard(chat_id),
        parse_mode="HTML",
    )
    context.user_data.clear()
    return ConversationHandler.END


quick_add_movie_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(quick_add_movie_callback, pattern=r"^movie:quick_add$")],
    states={
        QUICK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_get_code)],
        QUICK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_get_name)],
        QUICK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, quick_get_description)],
        QUICK_VIDEO: [MessageHandler(~filters.COMMAND, quick_get_video)],
        QUICK_SAVE: [CallbackQueryHandler(quick_save_data, pattern=r"^movie:quick_(confirm|reject)$")],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_command),
        CommandHandler('start', start_from_conv),
    ],
    per_user=True,
    block=True,
)
