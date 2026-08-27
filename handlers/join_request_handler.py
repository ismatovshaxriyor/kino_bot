from telegram import Update
from telegram.ext import ContextTypes

from database import Channels, ChannelJoinRequest, ChannelSubscription


async def channel_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yopiq kanal/guruhga qo'shilish so'rovi kelganda ishga tushadi.

    Agar so'rov bizning majburiy kanallardan biriga bo'lsa, uni yozib
    qo'yamiz — shu orqali admin hali tasdiqlamagan bo'lsa ham, foydalanuvchi
    obuna tekshiruvidan (@channel_subscription_required, check_subscription_callback)
    o'tib, botdan foydalana oladi.
    """
    request = update.chat_join_request
    if not request:
        return
    channel = await Channels.get_or_none(channel_id=request.chat.id)
    if channel:
        await ChannelJoinRequest.get_or_create(channel=channel, telegram_id=request.from_user.id)


async def channel_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi kanalni tark etganda (left) yoki chiqarilganda (kicked) yozuvlarni tozalash."""
    chat_member = update.chat_member
    if not chat_member or not chat_member.new_chat_member:
        return

    channel = await Channels.get_or_none(channel_id=chat_member.chat.id)
    if not channel:
        return

    user = chat_member.new_chat_member.user
    if not user:
        return

    if chat_member.new_chat_member.status in ("left", "kicked"):
        await ChannelJoinRequest.filter(channel=channel, telegram_id=user.id).delete()
        await ChannelSubscription.filter(channel=channel, telegram_id=user.id).delete()
