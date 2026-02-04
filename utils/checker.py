from telegram import Bot
from telegram.error import TelegramError


async def is_bot_admin(bot: Bot, chat_id: int) -> bool:
    try:
        bot_member = await bot.get_chat_member(
            chat_id=chat_id,
            user_id=bot.id
        )

        return bot_member.status in ("administrator", "creator")

    except TelegramError as e:
        print(f"Bot adminligini tekshirishda xato: {e}")
        return False
