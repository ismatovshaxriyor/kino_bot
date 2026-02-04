from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import MANAGER_ID, ADMIN_ID

class PermissionDenied(Exception):
    pass


def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from database import User
        user_id = update.effective_user.id
        user = await User.get_or_none(telegram_id=user_id)

        if not ((user and user.user_type == 'admin') or user_id in (ADMIN_ID, MANAGER_ID)):
            raise PermissionDenied()

        return await func(update, context, *args, **kwargs)
    return wrapper


def channel_subscription_required(func):
    """
    Foydalanuvchining barcha kanallarga a'zo ekanligini tekshiruvchi decorator.
    Agar a'zo bo'lmasa, kanallar ro'yxatini ko'rsatadi.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from database import Channels
        from utils.checker import is_user_subscribed

        user_id = update.effective_user.id
        channels = await Channels.all()

        if not channels:
            # Kanallar yo'q bo'lsa, tekshiruvsiz o'tkazish
            return await func(update, context, *args, **kwargs)

        not_subscribed = []
        for channel in channels:
            # Username yoki ID orqali tekshirish
            chat_id = f"@{channel.username}" if channel.username else channel.channel_id
            is_member = await is_user_subscribed(context.bot, user_id, chat_id)
            if not is_member:
                not_subscribed.append(channel)

        if not_subscribed:
            # A'zo bo'lmagan kanallar ro'yxatini ko'rsatish
            btns = []
            for ch in not_subscribed:
                url = f"https://t.me/{ch.username}" if ch.username else f"https://t.me/c/{str(ch.channel_id)[4:]}"
                btns.append([InlineKeyboardButton(f"📢 {ch.name}", url=url)])

            btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription")])
            keyboard = InlineKeyboardMarkup(btns)

            await update.message.reply_text(
                "⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:\n\n"
                "A'zo bo'lgandan so'ng \"✅ Tekshirish\" tugmasini bosing.",
                reply_markup=keyboard
            )
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper
