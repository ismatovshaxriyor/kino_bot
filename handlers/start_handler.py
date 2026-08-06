from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from database import User
from utils import error_notificator, get_user_keyboard
from utils.decorators import channel_subscription_required


START_IMAGE_PATH = Path(__file__).resolve().parent.parent / "IMG_7403.PNG"


def _start_caption(first_name: str, created: bool) -> str:
    if created:
        return (
            "👋 <b>Xush kelibsiz!</b>\n\n"
            f"Assalomu alaykum, <b>{first_name}</b>.\n"
            "🔎 Kino izlash uchun pastdagi tugmadan foydalaning.\n"
            "🎯 Yoki kino kodini chatga yuboring."
        )
    return (
        "👋 <b>Qaytganingizdan xursandmiz!</b>\n\n"
        f"Salom, <b>{first_name}</b>.\n"
        "🔎 Kino izlash uchun pastdagi tugmadan foydalaning.\n"
        "🎯 Yoki kino kodini chatga yuboring."
    )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Referal kodini (agar bo'lsa) obuna tekshiruvidan oldin saqlab qo'yamiz.

    Kanalga a'zo bo'lmagan foydalanuvchi "ref_<id>" payloadi bilan birinchi
    marta /start bossa, @channel_subscription_required uni bloklaydi va
    asosiy funksiya (_start_handler_impl) ishga tushmaydi — payload
    yo'qoladi. A'zo bo'lib qaytadan /start bosganda esa payload endi yo'q
    (Telegram uni faqat bitta chaqiriqda beradi). Shu sabab kodni
    user_data'ga saqlab, keyingi (argumentsiz) /start'da ham ishlata olamiz.
    """
    if context.args and context.args[0].startswith("ref_"):
        context.user_data['pending_ref'] = context.args[0]

    return await _start_handler_impl(update, context)


@channel_subscription_required
async def _start_handler_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.effective_chat.first_name
    last_name = update.effective_chat.last_name
    username = update.effective_chat.username
    telegram_id = update.effective_chat.id

    pending_ref = context.user_data.get('pending_ref')

    # Barcha statelarni to'liq tozalash
    context.user_data.clear()

    try:
        referrer = None
        ref_code = (context.args[0] if context.args and context.args[0].startswith("ref_") else None) or pending_ref
        if ref_code:
            ref_id_raw = ref_code[len("ref_"):]
            if ref_id_raw.isdecimal() and int(ref_id_raw) != telegram_id:
                referrer = await User.get_or_none(telegram_id=int(ref_id_raw))

        defaults = {
            'first_name': first_name,
            'last_name': last_name if last_name else None,
            'username': username if username else None,
        }
        if referrer:
            defaults['referred_by'] = referrer

        user, created = await User.get_or_create(telegram_id=telegram_id, defaults=defaults)

        if context.args and context.args[0].isdecimal():
            from handlers.inline_query_handler import inline_movie_command_handler
            return await inline_movie_command_handler(update, context)

        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Kino izlash", switch_inline_query_current_chat="")]
        ])
        caption = _start_caption(first_name, created)
        welcome_message = None

        try:
            if START_IMAGE_PATH.exists():
                with START_IMAGE_PATH.open("rb") as img:
                    welcome_message = await update.message.reply_photo(
                        photo=img,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=inline_keyboard,
                    )
            else:
                raise FileNotFoundError("IMG_7403.PNG topilmadi")
        except (BadRequest, OSError):
            # Fallback: old text welcome if image cannot be sent.
            welcome_message = await update.message.reply_text(caption, parse_mode="HTML")

        if welcome_message:
            try:
                await context.bot.pin_chat_message(
                    chat_id=update.effective_chat.id,
                    message_id=welcome_message.message_id,
                    disable_notification=True,
                )
            except (BadRequest, Forbidden):
                # Private chats or missing pin permissions.
                pass

        await update.message.reply_text("👇 Menyu:", reply_markup=await get_user_keyboard(telegram_id))

    except Exception as e:
        await error_notificator.notify(context, e, update)


