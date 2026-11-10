"""Yakuniy to'xtatish rejimi (/shutdown) — boshqa serverga o'tishni osonlashtirish uchun.

Kredit tugab borayotganda admin buyruq beradi; bot:
  1) oxirgi zaxira nusxani olib ADMIN_ID ga yuboradi,
  2) .env faylini ham yuboradi,
  3) faqat ikkalasi yetib borgach qulf yozib, botni butunlay to'xtatadi.

Xavfsizlik:
  - hech qachon o'zi ishga tushmaydi — faqat ADMIN_ID ning /shutdown + bir martalik kod bilan tasdig'i;
  - faqat kredit rostdan kam bo'lsa ruxsat beriladi;
  - biror qadam xato bersa to'xtatish bekor qilinadi va bot ishlashda davom etadi.
"""

import asyncio
import hmac
import logging
import os
import secrets
import time
from datetime import datetime
from html import escape
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from admins.backup_handler import send_backup
from services.server_monitor import credit_is_low, fetch_aws_status, format_aws
from utils.settings import ADMIN_ID, AWS_MONITOR_ENABLED, SHUTDOWN_ENV_PATH
from utils.shutdown_guard import engage_lock, lock_exists

logger = logging.getLogger(__name__)

CONFIRM_TTL = 120                 # tasdiq kodi amal qilish muddati (soniya)
CONFIRM_PATTERN = r"(?i)^\s*TASDIQLAYMAN\s+[0-9A-F]{6}\s*$"
HARD_EXIT_AFTER = 30              # graceful to'xtamasa, shundan keyin majburan chiqish (soniya)

_pending: dict[int, tuple[str, float]] = {}   # user_id -> (kod, amal qilish muddati)
_shutting_down = False


async def _say(bot, chat_id: int, text: str) -> None:
    # direct=True: Redis/worker yiqilgan bo'lsa ham yetib boradi
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", direct=True)


async def maintenance_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """To'xtatish jarayonida adminga tegishli bo'lmagan update'larni o'tkazmaslik — zaxira haqiqatan oxirgi bo'lishi uchun."""
    if _shutting_down:
        user = update.effective_user
        if not user or user.id != ADMIN_ID:
            raise ApplicationHandlerStop


async def shutdown_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/shutdown — shartlarni tekshirib, tasdiq kodi berish (faqat ADMIN_ID)."""
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        return
    bot = context.bot

    if lock_exists():
        await _say(bot, user.id, "🛑 Bot allaqachon to'xtatilgan (qulf fayli bor).")
        return
    code = secrets.token_hex(3).upper()
    _pending[user.id] = (code, time.monotonic() + CONFIRM_TTL)
    await _say(bot, user.id, (
        "🛑 <b>YAKUNIY TO'XTATISH</b>\n\n"
        "Tasdiqlansa:\n"
        "1️⃣ oxirgi bazaning zaxira nusxasi sizga yuboriladi,\n"
        "2️⃣ <b>.env fayli</b> (BOT_TOKEN, parollar, kalitlar) yuboriladi,\n"
        "3️⃣ ikkalasi yetib borgach bot <b>butunlay to'xtatiladi</b> va qayta ishga tushmaydi.\n\n"
        f"Tasdiqlash uchun {CONFIRM_TTL // 60} daqiqa ichida aynan shuni yuboring:\n"
        f"<code>TASDIQLAYMAN {code}</code>\n\n"
        "Bekor qilish uchun hech narsa yubormang."
    ))


async def shutdown_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`TASDIQLAYMAN <KOD>` — kodni tekshirib, yakuniy to'xtatishni bajarish (bir martalik)."""
    await _confirm(update, context)
    raise ApplicationHandlerStop  # bu matn boshqa handlerlarga o'tmasin


async def _confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bot = context.bot
    entry = _pending.pop(user.id, None)  # har qanday urinish kodni "yoqadi": xato kiritsangiz qaytadan /shutdown

    if entry is None:
        await _say(bot, user.id, "❌ Tasdiq so'rovi yo'q yoki muddati o'tgan. Avval /shutdown yuboring.")
        return
    code, expires = entry
    typed = update.message.text.split()[1].upper()
    if time.monotonic() > expires:
        await _say(bot, user.id, "❌ Kodning muddati o'tdi. /shutdown ni qaytadan yuboring.")
        return
    if not hmac.compare_digest(typed, code):
        await _say(bot, user.id, "❌ Kod noto'g'ri, so'rov bekor qilindi. /shutdown ni qaytadan yuboring.")
        return

    await run_final_shutdown(context, user.id)


async def run_final_shutdown(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    global _shutting_down
    bot = context.bot
    _shutting_down = True
    try:
        env_path = Path(SHUTDOWN_ENV_PATH)
        if not env_path.is_file():
            raise RuntimeError(f".env fayli topilmadi ({env_path}) — docker-compose.yml da ./.env ulanmagan")

        await _say(bot, chat_id, "⏳ Yakuniy zaxira olinmoqda, bot yangi so'rovlarni qabul qilmayapti...")
        sent, filename = await send_backup(bot, [ADMIN_ID], reason="Yakuniy zaxira (to'xtatishdan oldin)")
        if sent != 1:
            raise RuntimeError("zaxirani yuborib bo'lmadi (hajmi 50 MB dan oshgan yoki Telegram xatosi)")

        with env_path.open("rb") as f:
            await bot.send_document(
                chat_id=ADMIN_ID, document=f, filename="kino_bot.env",
                caption="🔐 <b>.env nusxasi</b> — maxfiy! Yangi serverga o'tgach xabarni o'chiring, tokenlarni yangilang.",
                parse_mode="HTML",
            )
        engage_lock(f"{datetime.now():%Y-%m-%d %H:%M:%S} /shutdown, zaxira: {filename}")
    except Exception as e:
        _shutting_down = False
        logger.exception("Yakuniy to'xtatish bekor qilindi: %s", e)
        await _say(bot, chat_id, f"❌ <b>To'xtatish bekor qilindi — bot ishlashda davom etadi.</b>\n<code>{escape(str(e)[:300])}</code>")
        return

    await _say(bot, chat_id, (
        "🛑 <b>Bot to'xtatildi.</b> Zaxira va .env yuqorida.\n\n"
        "<b>Yangi serverga o'tish:</b>\n"
        "1. Docker, git o'rnating; loyihani oling; .env ni joylang (docs/DEPLOY_EC2.md)\n"
        "2. <code>docker compose up -d redis db</code>\n"
        "3. Zaxirani tiklang (docs/BACKUP_RESTORE.md), so'ng <code>docker compose --profile app up -d</code>\n\n"
        "⚠️ Bir token — bitta polling: yangi botni eski server to'xtaganiga ishonch hosil qilgach yoqing.\n"
        "⚠️ Ko'chgach BOT_TOKEN, DB_PASSWORD va AWS kalitlarini yangilang.\n\n"
        "Eski serverda qayta yoqish: <code>rm state/shutdown.lock</code> va <code>docker compose --profile app restart bot worker</code>"
    ))
    # Odatiy yo'l: polling to'xtaydi, jarayon chiqadi. Qayta ishga tushsa ham qulf ushlab turadi.
    asyncio.get_running_loop().call_later(HARD_EXIT_AFTER, os._exit, 0)
    context.application.stop_running()
