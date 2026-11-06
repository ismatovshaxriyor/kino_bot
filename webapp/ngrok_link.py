"""ngrok bergan ochiq HTTPS havolani botga avtomatik ulash.

ngrok (bepul tarifda) qayta ishga tushganda havola o'zgaradi. Bu modul har 15 soniyada ngrok API sini
so'raydi; havola o'zgargan bo'lsa:
  - adminlarning chat menyusidagi "📊 Server" tugmasini yangilaydi (set_chat_menu_button),
  - Redis'da `webapp:url` ni yangilaydi (bot /panel buyrug'i shuni o'qiydi),
  - havola yangi bo'lsa adminga tugma bilan xabar yuboradi (bir xil havola uchun qayta yubormaydi).
"""

import asyncio
import logging

import aiohttp
import redis.asyncio as aioredis
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo

from utils.settings import ADMIN_ID, BOT_TOKEN, MANAGER_ID, REDIS_URL
from utils.tg_request import make_request

logger = logging.getLogger(__name__)

URL_KEY = "webapp:url"            # joriy havola (TTL bilan: ngrok yoki panel to'xtasa o'zi yo'qoladi)
NOTIFIED_KEY = "webapp:notified"  # adminga oxirgi xabar qilingan havola
URL_TTL = 120
POLL_EVERY = 15
MENU_TEXT = "📊 Server"


async def discover_url(session: aiohttp.ClientSession, api_url: str) -> str | None:
    """ngrok agentining lokal API sidan https ochiq havolani oladi."""
    try:
        async with session.get(f"{api_url.rstrip('/')}/api/tunnels", timeout=aiohttp.ClientTimeout(total=3)) as resp:
            data = await resp.json()
    except Exception:
        return None
    for t in data.get("tunnels", []):
        url = t.get("public_url", "")
        if url.startswith("https://"):
            return url
    return None


async def apply_url(bot, r, url: str, chat_ids=(ADMIN_ID, MANAGER_ID)) -> None:
    for chat_id in dict.fromkeys(chat_ids):
        try:
            await bot.set_chat_menu_button(chat_id=chat_id, menu_button=MenuButtonWebApp(MENU_TEXT, WebAppInfo(url)))
        except Exception as e:
            logger.warning("Menyu tugmasini %s uchun o'rnatib bo'lmadi: %s", chat_id, e)

    if await r.get(NOTIFIED_KEY) == url:
        return
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text="📊 <b>Server paneli tayyor.</b>\nHavola yangilandi — tugmani bosing yoki chat menyusidagi «📊 Server» ni oching.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(MENU_TEXT, web_app=WebAppInfo(url))]]),
        )
        await r.set(NOTIFIED_KEY, url)
    except Exception as e:
        logger.warning("Admin ga havola xabarini yuborib bo'lmadi: %s", e)


async def run_publisher(session: aiohttp.ClientSession, api_url: str, *, bot=None, r=None, poll_every: float = POLL_EVERY) -> None:
    bot = bot or Bot(BOT_TOKEN, request=make_request())
    r = r or aioredis.from_url(REDIS_URL, decode_responses=True)
    current = None
    warned = False
    while True:
        try:
            url = await discover_url(session, api_url)
            if url is None:
                if not warned:
                    logger.warning("ngrok havolasi topilmadi (NGROK_AUTHTOKEN o'rnatilganmi?)")
                    warned = True
            else:
                warned = False
                if url != current:
                    logger.info("Panel havolasi: %s", url)
                    await apply_url(bot, r, url)
                    current = url
                await r.set(URL_KEY, url, ex=URL_TTL)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Havolani ulashda xato")
        await asyncio.sleep(poll_every)
