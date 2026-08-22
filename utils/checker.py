import logging

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


async def is_bot_admin(bot: Bot, chat_id: int | str) -> bool:
    """Botning kanalda admin ekanligini tekshirish"""
    try:
        bot_member = await bot.get_chat_member(
            chat_id=chat_id,
            user_id=bot.id
        )

        return bot_member.status in ("administrator", "creator")

    except TelegramError as e:
        logger.warning("Bot adminligini tekshirishda xato: %s", e)
        return False


async def is_user_subscribed(bot: Bot, user_id: int, channel) -> bool:
    """Foydalanuvchining kanalga a'zo ekanligini tekshirish.

    Kanal yopiq (faqat tasdiqlash so'rovi orqali qo'shiladigan) bo'lsa,
    admin hali so'rovni tasdiqlamagan bo'lsa ham — foydalanuvchi o'sha
    so'rovni yuborgan bo'lsa, bu ham a'zolik sifatida hisoblanadi (bot
    tomonidan "chat_join_request" hodisasi kelganda yozib qo'yilgan bo'ladi,
    handlers/join_request_handler.py'ga qarang).
    """
    chat_id = f"@{channel.username}" if channel.username else channel.channel_id

    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ("member", "administrator", "creator", "restricted"):
            return True
    except TelegramError as e:
        logger.warning("Foydalanuvchi a'zoligini tekshirishda xato: %s", e)

    from database import ChannelJoinRequest
    return await ChannelJoinRequest.filter(channel_id=channel.channel_id, telegram_id=user_id).exists()


async def get_join_by_request_status(bot: Bot, chat_id: int | str) -> bool | None:
    """Kanal/guruh yopiqmi (faqat tasdiqlash so'rovi orqali qo'shiladimi) — tekshirish.

    True/False — holat aniq. None — aniqlab bo'lmadi (masalan bot o'sha
    kanal/guruhda administrator emas yoki undan chiqarilgan).
    """
    try:
        chat = await bot.get_chat(chat_id=chat_id)
        return bool(chat.join_by_request)
    except TelegramError as e:
        logger.warning("Kanal/guruh yopiqligini tekshirishda xato: %s", e)
        return None


async def get_channel_info(bot: Bot, channel_input: str) -> dict | None:
    """
    Kanal username yoki ID bo'yicha ma'lumot olish.
    channel_input: @username, username, yoki -100xxxxxxxxxx formatida
    """
    try:
        # -100 bilan boshlanuvchi ID
        if channel_input.startswith('-100') or (channel_input.lstrip('-').isdecimal()):
            chat_id = int(channel_input)
        else:
            # Username formatida
            if not channel_input.startswith('@'):
                channel_input = f"@{channel_input}"
            chat_id = channel_input

        chat = await bot.get_chat(chat_id=chat_id)
        return {
            "id": chat.id,
            "title": chat.title,
            "username": chat.username
        }
    except TelegramError as e:
        logger.warning("Kanal ma'lumotini olishda xato: %s", e)
        return None
