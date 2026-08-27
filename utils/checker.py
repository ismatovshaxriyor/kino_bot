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
    """Foydalanuvchining kanalga a'zo ekanligini yoki so'rov yuborganligini tekshirish.

    Kanal yopiq (faqat tasdiqlash so'rovi orqali qo'shiladigan) bo'lsa,
    admin hali so'rovni tasdiqlamagan bo'lsa ham — foydalanuvchi o'sha
    so'rovni yuborgan bo'lsa, bu ham a'zolik sifatida hisoblanadi (bot
    tomonidan "chat_join_request" hodisasi kelganda yozib qo'yilgan bo'ladi,
    handlers/join_request_handler.py'ga qarang).
    """
    chat_id = channel.channel_id or (f"@{channel.username}" if channel.username else None)

    if chat_id:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ("member", "administrator", "creator", "restricted"):
                return True
            if member.status == "kicked":
                return False
        except TelegramError as e:
            logger.warning("Foydalanuvchi a'zoligini tekshirishda xato (%s): %s", chat_id, e)

    from database import ChannelJoinRequest
    return await ChannelJoinRequest.filter(channel_id=channel.channel_id, telegram_id=user_id).exists()


async def ensure_channel_invite_link(bot: Bot, channel_id: int | str) -> str | None:
    """Yopiq kanal yoki guruh uchun ishlaydigan taklif havolasini (invite link) oladi yoki yaratadi."""
    try:
        chat = await bot.get_chat(chat_id=channel_id)
        # 1. Agar chatda birlamchi invite_link allaqachon mavjud bo'lsa
        if getattr(chat, "invite_link", None):
            return chat.invite_link

        # 2. Agar so'rov orqali qo'shilish yoqilgan bo'lsa, creates_join_request=True qilamiz
        creates_request = bool(getattr(chat, "join_by_request", False))
        try:
            link_obj = await bot.create_chat_invite_link(
                chat_id=channel_id,
                creates_join_request=creates_request,
                name="KinoBot",
            )
            if link_obj and getattr(link_obj, "invite_link", None):
                return link_obj.invite_link
        except Exception as e:
            logger.warning("create_chat_invite_link xatosi (%s): %s", channel_id, e)

        # 3. Zaxira sifatida export_chat_invite_link sinab ko'riladi
        try:
            exported = await bot.export_chat_invite_link(chat_id=channel_id)
            if exported:
                return exported
        except Exception as e:
            logger.warning("export_chat_invite_link xatosi (%s): %s", channel_id, e)

        return None
    except Exception as e:
        logger.warning("ensure_channel_invite_link chat xatosi (%s): %s", channel_id, e)
        return None


async def get_channel_url(bot: Bot, channel) -> str:
    """Har qanday kanal/guruh uchun foydalanuvchi bosganda ishlaydigan URL qaytaradi.

    - Agar bazada invite_link saqlangan bo'lsa -> o'shani qaytaradi.
    - Agar ochiq kanal bo'lsa (@username bor) -> https://t.me/username
    - Agar yopiq kanal bo'lsa (username yo'q) -> Telegram API orqali invite_link yaratadi,
      bazada saqlaydi va qaytaradi.
    """
    # 1. Bazada saqlangan taklif havolasi bo'lsa
    stored_link = getattr(channel, "invite_link", None)
    if stored_link and stored_link.startswith("http"):
        return stored_link

    # 2. Username mavjud bo'lsa
    username = (channel.username or "").lstrip("@").strip()
    if username:
        return f"https://t.me/{username}"

    # 3. Yopiq kanal/guruh uchun Telegram API orqali yangi havola olamiz
    new_link = await ensure_channel_invite_link(bot, channel.channel_id)
    if new_link:
        try:
            channel.invite_link = new_link
            await channel.save(update_fields=["invite_link"])
        except Exception as e:
            logger.warning("Kanal invite_link'ni bazaga saqlashda xato: %s", e)
        return new_link

    # 4. Oxirgi chora (fallback)
    if username:
        return f"https://t.me/{username}"
    return f"https://t.me/c/{str(channel.channel_id).replace('-100', '')}"


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
            "username": chat.username,
            "type": str(getattr(chat, "type", "channel")),
        }
    except TelegramError as e:
        logger.warning("Kanal ma'lumotini olishda xato: %s", e)
        return None
