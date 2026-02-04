from telegram import Bot
from telegram.error import TelegramError


async def is_bot_admin(bot: Bot, chat_id: int | str) -> bool:
    """Botning kanalda admin ekanligini tekshirish"""
    try:
        bot_member = await bot.get_chat_member(
            chat_id=chat_id,
            user_id=bot.id
        )

        return bot_member.status in ("administrator", "creator")

    except TelegramError as e:
        print(f"Bot adminligini tekshirishda xato: {e}")
        return False


async def is_user_subscribed(bot: Bot, user_id: int, chat_id: int | str) -> bool:
    """Foydalanuvchining kanalga a'zo ekanligini tekshirish"""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except TelegramError as e:
        print(f"Foydalanuvchi a'zoligini tekshirishda xato: {e}")
        return False


async def get_channel_info(bot: Bot, channel_input: str) -> dict | None:
    """
    Kanal username yoki ID bo'yicha ma'lumot olish.
    channel_input: @username, username, yoki -100xxxxxxxxxx formatida
    """
    try:
        # -100 bilan boshlanuvchi ID
        if channel_input.startswith('-100') or (channel_input.lstrip('-').isdigit()):
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
        print(f"Kanal ma'lumotini olishda xato: {e}")
        return None
