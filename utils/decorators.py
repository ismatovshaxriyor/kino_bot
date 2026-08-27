import asyncio
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
            text = "⛔ Sizda bu amalni bajarish uchun ruxsat yo'q."
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            elif update.message:
                await update.message.reply_text(text)
            return None

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

        # Admin yoki managerlar majburiy a'zolik tekshiruvidan ozod
        from database import User
        from database.user_model import USER_TYPE
        user = await User.get_or_none(telegram_id=user_id)
        if user_id in (ADMIN_ID, MANAGER_ID) or (user and user.user_type == USER_TYPE.ADMIN):
            return await func(update, context, *args, **kwargs)

        # Har bir kanal uchun Telegram API so'rovi tarmoq orqali ketadi —
        # ketma-ket (sequential) tekshirish kanallar soni ortgani sayin har
        # bir foydalanuvchi amalini chiziqli sekinlashtiradi. Parallel
        # yuborib, eng sekin so'rov vaqtigacha kutamiz (N marta emas, 1 marta).
        membership_results = await asyncio.gather(*(
            is_user_subscribed(context.bot, user_id, channel)
            for channel in channels
        ))
        not_subscribed = [
            channel for channel, is_member in zip(channels, membership_results) if not is_member
        ]

        if not_subscribed:
            # A'zo bo'lmagan kanallar ro'yxatini ko'rsatish
            from utils.checker import get_channel_url
            channel_urls = await asyncio.gather(*(
                get_channel_url(context.bot, ch)
                for ch in not_subscribed
            ))
            btns = []
            for ch, url in zip(not_subscribed, channel_urls):
                btns.append([InlineKeyboardButton(f"📢 {ch.name}", url=url)])

            btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription")])
            keyboard = InlineKeyboardMarkup(btns)

            await update.message.reply_text(
                "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n\n"
                "<i>(Agar kanal yoki guruh yopiq bo'lsa, unga qo'shilish so'rovi yuboring)</i>\n\n"
                "A'zo bo'lgach yoki so'rov yuborgach, pastdagi <b>\"✅ Tekshirish\"</b> tugmasini bosing.",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return None

        return await func(update, context, *args, **kwargs)
    return wrapper


def user_registered_required(func):
    """
    Foydalanuvchi bazada mavjudligini tekshiradi.
    Mavjud bo'lmasa /start bosishni so'raydi.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from database import User

        user_id = update.effective_user.id
        user = await User.get_or_none(telegram_id=user_id)
        if user is not None:
            return await func(update, context, *args, **kwargs)

        text = "⚠️ Siz hali ro'yxatdan o'tmagansiz.\n\nIltimos avval /start buyrug'ini bosing."
        if update.callback_query:
            await update.callback_query.answer("Avval /start bosing", show_alert=True)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        elif update.message:
            await update.message.reply_text(text)
        return None

    return wrapper
