from html import escape
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils import admin_required, get_user_keyboard
from utils.admin_btns import get_admin_keyboard
from utils.settings import ADMIN_ID, MANAGER_ID
from database import User
from .managers_handler import get_managers_btns

logger = logging.getLogger(__name__)


def extract_forward_chat(message):
    """Forward qilingan xabardan kanal yoki guruh (chat) obyektini ajratib oladi."""
    origin = getattr(message, "forward_origin", None)
    if not origin:
        return None
    if hasattr(origin, "chat") and origin.chat:
        return origin.chat
    if hasattr(origin, "sender_chat") and origin.sender_chat:
        return origin.sender_chat
    return None


async def _process_channel_addition(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    chat_title: str,
    chat_username: str | None,
    chat_type: str = "channel",
):
    """Kanal yoki guruhni tekshirish (mavjudligi, adminligi) va tasdiqlash tugmalarini yuborish."""
    from database import Channels
    from utils.checker import is_bot_admin

    existing = await Channels.get_or_none(channel_id=chat_id)
    if existing:
        await update.message.reply_text(
            f"⚠️ <b>\"{escape(chat_title)}\"</b> allaqachon kanallar ro'yxatida mavjud!",
            parse_mode="HTML",
        )
        return

    is_admin = await is_bot_admin(context.bot, chat_id)
    is_group = str(chat_type).lower() in ("group", "supergroup")
    chat_type_label = "guruhida" if is_group else "kanalida"
    chat_type_title = "Guruh" if is_group else "Kanal"

    if not is_admin:
        await update.message.reply_text(
            f"❌ Bot <b>\"{escape(chat_title)}\"</b> {chat_type_label} admin emas!\n\n"
            f"{chat_type_title}ni qo'shish uchun:\n"
            f"1. Botni o'sha {chat_type_label} qo'shing\n"
            f"2. Botga <b>administrator</b> huquqini bering\n"
            f"3. So'ngra qaytadan xabarni forward qiling yoki username/ID yuboring",
            parse_mode="HTML",
        )
        return

    context.user_data['channel_id'] = chat_id
    context.user_data['channel_username'] = chat_username
    context.user_data['channel_name'] = chat_title
    context.user_data['state'] = "WAITING_FOR_CONFIRM_CHANNEL"

    confirm_btns = [
        [
            InlineKeyboardButton(text='✅ Tasdiqlash', callback_data='confirm_channel_add'),
            InlineKeyboardButton(text='❌ Bekor qilish', callback_data='reject_channel_add'),
        ]
    ]
    confirm_keyboard = InlineKeyboardMarkup(confirm_btns)
    username_text = f"@{chat_username}" if chat_username else "mavjud emas (yopiq)"

    await update.message.reply_text(
        f"✅ Bot {chat_type_label} admin!\n\n"
        f"📢 <b>{chat_type_title}:</b> {escape(chat_title)}\n"
        f"🆔 <b>ID:</b> <code>{chat_id}</code>\n"
        f"👤 <b>Username:</b> {username_text}\n\n"
        f"Ushbu {chat_type_title.lower()}ni majburiy a'zolikka qo'shishni tasdiqlaysizmi?",
        reply_markup=confirm_keyboard,
        parse_mode="HTML",
    )


async def cancel_state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel — ConversationHandler'siz oddiy "state" kutish oqimlarini bekor qiladi.

    add_movie/edit_movie/broadcast — o'zining ConversationHandler + /cancel
    fallback'iga ega, shuning uchun bu yerga umuman yetib kelmaydi (ular
    ro'yxatda oldinroq turadi va faol suhbatni o'zi ushlab qoladi). Lekin
    genre/country/manager/kanal/referral-lookup kabi oddiy `context.user_data
    ['state']`ga tayanadigan oqimlarda /cancel ishlamas edi — shu handler
    ularning barchasi uchun bitta umumiy chiqish yo'lini beradi.
    """
    if not context.user_data.get('state'):
        return

    context.user_data['state'] = None
    user_id = update.effective_user.id

    user = await User.get_or_none(telegram_id=user_id)
    is_admin = (user and user.user_type == 'admin') or user_id in (ADMIN_ID, MANAGER_ID)
    keyboard = get_admin_keyboard(user_id) if is_admin else await get_user_keyboard(user_id)

    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=keyboard)


@admin_required
async def general_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    state = context.user_data.get('state')

    if state is None:
        return

    if state != "WAITING_CHANNEL_USERNAME" and not update.message.text:
        return

    if state == 'WAITING_GENRE_NAME':
        genre = update.message.text
        context.user_data['new_genre'] = genre.capitalize()
        context.user_data['state'] = "WAITING_FOR_CONFIRM_GENRE"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_genre_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_genre_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi janr: {genre.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_COUNTRY_NAME":
        country = update.message.text
        context.user_data['new_country'] = country.capitalize()
        context.user_data['state'] = "WAITING_FOR_CONFIRM_COUNTRY"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_country_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_country_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi davlat: {country.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_GENRE_EDIT_NAME":
        new_name = update.message.text.strip().capitalize()
        if not new_name:
            await update.message.reply_text("Noto'g'ri nom. Qaytadan yuboring.")
            return

        genre_id = context.user_data.get("edit_genre_id")
        if not genre_id:
            context.user_data.pop("state", None)
            await update.message.reply_text("Jarayon topilmadi, qayta urinib ko'ring.")
            return

        context.user_data["edit_genre_name"] = new_name
        context.user_data["state"] = "WAITING_FOR_CONFIRM_GENRE_EDIT"

        confirm_keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(text='Tasdiqlash', callback_data=f'confirm_genre_edit_{genre_id}'),
                InlineKeyboardButton(text='Bekor qilish', callback_data=f'reject_genre_edit_{genre_id}')
            ]]
        )
        await update.message.reply_text(
            f"Janrni yangilash: {new_name}. Tasdiqlaysizmi?",
            reply_markup=confirm_keyboard
        )

    elif state == "WAITING_COUNTRY_EDIT_NAME":
        new_name = update.message.text.strip().capitalize()
        if not new_name:
            await update.message.reply_text("Noto'g'ri nom. Qaytadan yuboring.")
            return

        country_id = context.user_data.get("edit_country_id")
        if not country_id:
            context.user_data.pop("state", None)
            await update.message.reply_text("Jarayon topilmadi, qayta urinib ko'ring.")
            return

        context.user_data["edit_country_name"] = new_name
        context.user_data["state"] = "WAITING_FOR_CONFIRM_COUNTRY_EDIT"

        confirm_keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(text='Tasdiqlash', callback_data=f'confirm_country_edit_{country_id}'),
                InlineKeyboardButton(text='Bekor qilish', callback_data=f'reject_country_edit_{country_id}')
            ]]
        )
        await update.message.reply_text(
            f"Davlatni yangilash: {new_name}. Tasdiqlaysizmi?",
            reply_markup=confirm_keyboard
        )

    elif state == "WAITING_MANAGER_ID":
        keyboard, i = await get_managers_btns()

        try:
            manager_id = int(update.message.text)
            context.user_data['new_manager'] = manager_id
        except (ValueError, TypeError):
            await update.message.reply_text("Noto'g'ri formatdagi id\n\nId faqat raqamlardan iborat bo'lishi kerak", reply_markup=keyboard)
            return

        new_manager = await User.get_or_none(telegram_id=manager_id)

        if new_manager is None:
            await update.message.reply_text("Bu Id da foydalanuvchi topilmadi\n\nIltimos botdan ro'yxatdan o'tgan foydalanuvchining Id sini yuboring.", reply_markup=keyboard)
            return

        context.user_data['state'] = "WAITING_FOR_CONFIRM_MANAGER"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_manager_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_manager_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi Manager: {new_manager.first_name} {new_manager.last_name if new_manager.last_name else None}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_CHANNEL_USERNAME":
        from utils.checker import get_channel_info

        # 1. Forward qilingan xabar orqali kanal yoki guruhni avtomatik aniqlash
        if update.message.forward_origin:
            target_chat = extract_forward_chat(update.message)
            if not target_chat:
                await update.message.reply_text(
                    "⚠️ <b>Bu xabar shaxsiy foydalanuvchidan uzatilgan!</b>\n\n"
                    "Iltimos, aynan <b>kanal yoki guruhdan</b> xabar forward (uzatish) qiling "
                    "yoki username/ID sini yuboring.",
                    parse_mode="HTML",
                )
                return

            chat_id = target_chat.id
            chat_title = getattr(target_chat, "title", None) or "Noma'lum"
            chat_username = getattr(target_chat, "username", None)
            chat_type = getattr(target_chat, "type", "channel")

            try:
                fresh_chat = await context.bot.get_chat(chat_id)
                chat_title = fresh_chat.title or chat_title
                chat_username = fresh_chat.username or chat_username
                chat_type = fresh_chat.type or chat_type
            except Exception as e:
                logger.warning("get_chat error for %s: %s", chat_id, e)

            await _process_channel_addition(
                update, context, chat_id, chat_title, chat_username, chat_type
            )

        # 2. Qo'lda matn (username yoki ID) kiritilganda
        elif update.message.text:
            channel_input = update.message.text.strip()
            channel_info = await get_channel_info(context.bot, channel_input)

            if not channel_info:
                await update.message.reply_text(
                    "❌ <b>Kanal yoki guruh topilmadi!</b>\n\n"
                    "Iltimos, to'g'ri username yoki ID kiriting, yoki kanaldan biror xabarni forward qiling:\n"
                    "• Kanaldan xabarni forward qilish <i>(eng osoni)</i>\n"
                    "• <code>@kanal_nomi</code>\n"
                    "• <code>-100xxxxxxxxxx</code> (kanal/guruh ID)",
                    parse_mode="HTML",
                )
                return

            await _process_channel_addition(
                update,
                context,
                channel_info['id'],
                channel_info['title'],
                channel_info['username'],
                channel_info.get('type', 'channel'),
            )
        else:
            await update.message.reply_text(
                "⚠️ Iltimos, kanal/guruhdan xabarni forward qiling yoki username/ID sini yuboring."
            )
            return

    elif state == "WAITING_REFERRAL_LOOKUP_ID":
        raw = update.message.text.strip()
        context.user_data['state'] = None

        if raw.startswith("@"):
            target = await User.get_or_none(username=raw[1:])
        elif raw.isdecimal():
            target = await User.get_or_none(telegram_id=int(raw))
        else:
            target = await User.get_or_none(username=raw)

        back_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Referallarga qaytish", callback_data="stats_referral")]]
        )

        if not target:
            await update.message.reply_text(
                "❌ Bunday foydalanuvchi topilmadi.\n\n"
                "Telegram ID (masalan <code>123456789</code>) yoki @username to'g'ri ekanligini tekshiring.",
                reply_markup=back_keyboard,
                parse_mode="HTML",
            )
            return

        referred_count = await User.filter(referred_by=target).count()
        name = f"@{target.username}" if target.username else (target.first_name or str(target.telegram_id))

        await update.message.reply_text(
            f"👤 <b>{name}</b> (<code>{target.telegram_id}</code>)\n\n"
            f"👥 Taklif qilgan do'stlari: <b>{referred_count} kishi</b>",
            reply_markup=back_keyboard,
            parse_mode="HTML",
        )

    else:
        pass
