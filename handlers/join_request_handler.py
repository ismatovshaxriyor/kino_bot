from telegram import Update
from telegram.ext import ContextTypes

from database import Channels, ChannelJoinRequest


async def channel_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yopiq kanal/guruhga qo'shilish so'rovi kelganda ishga tushadi.

    Agar so'rov bizning majburiy kanallardan biriga bo'lsa, uni yozib
    qo'yamiz — shu orqali admin hali tasdiqlamagan bo'lsa ham, foydalanuvchi
    obuna tekshiruvidan (@channel_subscription_required, check_subscription_callback)
    o'tib, botdan foydalana oladi.
    """
    request = update.chat_join_request
    channel = await Channels.get_or_none(channel_id=request.chat.id)
    if channel:
        await ChannelJoinRequest.get_or_create(channel=channel, telegram_id=request.from_user.id)
