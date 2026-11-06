"""Majburiy a'zolik tekshiruvini tezlashtiruvchi keshlar.

- A'zolik (Redis): har bir amalda har kanal uchun Telegram `get_chat_member` so'rovi ketmasligi uchun
  faqat "a'zo" natijasi SUB_TTL soniyaga saqlanadi. "A'zo emas" natijasi keshlanmaydi — foydalanuvchi
  kanalga qo'shilgach darhol o'tadi. Foydalanuvchi kanaldan chiqsa, chat_member handler keshni o'chiradi.
- Kanallar ro'yxati (xotirada): kanallar faqat shu jarayonda o'zgaradi, Tortoise signal'lari keshni tozalaydi.

Redis ishlamasa ikkalasi ham jim o'tib ketadi: tekshiruv avvalgidek Telegram/DB orqali bajariladi.
"""

import logging
import time

from tortoise.signals import post_delete, post_save

from .redis_manager import r

logger = logging.getLogger(__name__)

SUB_TTL = 600        # a'zolik natijasi saqlanish muddati, soniya
CHANNELS_TTL = 60    # kanallar ro'yxati saqlanish muddati, soniya

_channels = None
_channels_until = 0.0


def _sub_key(user_id: int, channel_id: int) -> str:
    return f"sub:{user_id}:{channel_id}"


async def is_member_cached(user_id: int, channel_id: int) -> bool:
    try:
        return bool(await r.exists(_sub_key(user_id, channel_id)))
    except Exception as e:
        logger.warning("Redis a'zolik keshini o'qib bo'lmadi: %s", e)
        return False


async def remember_member(user_id: int, channel_id: int) -> None:
    try:
        await r.set(_sub_key(user_id, channel_id), "1", ex=SUB_TTL)
    except Exception as e:
        logger.warning("Redis a'zolik keshiga yozib bo'lmadi: %s", e)


async def forget_member(user_id: int, channel_id: int) -> None:
    try:
        await r.delete(_sub_key(user_id, channel_id))
    except Exception as e:
        logger.warning("Redis a'zolik keshini o'chirib bo'lmadi: %s", e)


async def get_channels():
    """Majburiy kanallar ro'yxati (CHANNELS_TTL soniya xotirada saqlanadi)."""
    global _channels, _channels_until
    now = time.monotonic()
    if _channels is not None and now < _channels_until:
        return _channels

    from database import Channels
    _channels = await Channels.all()
    _channels_until = now + CHANNELS_TTL
    return _channels


def invalidate_channels() -> None:
    global _channels
    _channels = None


def register_channel_cache_signals() -> None:
    """Kanal qo'shilsa/o'zgarsa/o'chirilsa ro'yxat keshi darhol tozalanadi (main.py ishga tushishida chaqiriladi)."""
    from database import Channels

    @post_save(Channels)
    async def _on_saved(sender, instance, created, using_db, update_fields):
        invalidate_channels()

    @post_delete(Channels)
    async def _on_deleted(sender, instance, using_db):
        invalidate_channels()
