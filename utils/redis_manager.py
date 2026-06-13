import json
import asyncio
import logging
import re
import redis.asyncio as redis
from telegram import Bot
from telegram.error import BadRequest, RetryAfter, Forbidden
from .settings import ADMIN_ID, MANAGER_ID, REDIS_URL
try:
    from telegram.ext import ExtBot
except ImportError:
    ExtBot = None

logger = logging.getLogger(__name__)

QUEUE_NAME = "bot_queue"

# Telegram global limiti ~30 xabar/sek. Biroz pastroq tezlikda yuboramiz.
SEND_INTERVAL = 0.035
# Flood-limit (RetryAfter) bo'lganda eng ko'pi bilan shuncha soniya kutamiz.
MAX_RETRY_AFTER = 60
# Bitta xabar shuncha martadan ko'p qayta urinilsa — tashlab yuboriladi
# (navbat "zaharlangan" xabar tufayli bloklanib qolmasligi uchun).
MAX_QUEUE_RETRIES = 5

r = redis.from_url(REDIS_URL, decode_responses=True)

# Original metodlarni saqlab qolamiz
_original_send_message = Bot.send_message
_original_send_video = Bot.send_video
_original_edit_message_text = Bot.edit_message_text
_original_edit_message_caption = Bot.edit_message_caption
_original_edit_message_reply_markup = Bot.edit_message_reply_markup
_original_delete_message = Bot.delete_message

def clean_kwargs(kwargs):
    """Redisga yozishdan oldin argumentlarni tozalash"""
    cleaned = {}
    for k, v in kwargs.items():
        # DefaultValue obyektlarini o'tkazib yuborish
        if "DefaultValue" in str(type(v)):
            continue

        # Enum'larni qiymatiga o'tkazish
        if hasattr(v, "value"):
            cleaned[k] = v.value
            continue

        # Reply Markup ni dict ga o'tkazish
        if k == "reply_markup":
            if hasattr(v, "to_dict"):
                cleaned[k] = v.to_dict()
            elif isinstance(v, dict):
                cleaned[k] = v
            continue

        # Oddiy tiplarni qabul qilish
        if isinstance(v, (str, int, float, bool, list, dict, type(None))):
             cleaned[k] = v

    return cleaned

async def _push_to_redis(chat_id, method, content, **kwargs):
    # Argumentlarni tozalash
    cleaned_args = clean_kwargs(kwargs)

    payload = {
        "chat_id": chat_id,
        "method": method,
        "content": content,
        "args": cleaned_args
    }

    try:
        await r.rpush(QUEUE_NAME, json.dumps(payload))
    except Exception as e:
        logger.error("❌ Redis Push Error: %s", e)

# Patched methods
async def patched_send_message(self, chat_id, text, **kwargs):
    if kwargs.pop('direct', False):
        return await _original_send_message(self, chat_id, text, **kwargs)
    await _push_to_redis(chat_id, "send_message", text, **kwargs)

async def patched_send_video(self, chat_id, video, **kwargs):
    if kwargs.pop('direct', False):
        return await _original_send_video(self, chat_id, video, **kwargs)
    await _push_to_redis(chat_id, "send_video", video, **kwargs)

async def patched_edit_message_text(self, text, chat_id=None, message_id=None, inline_message_id=None, **kwargs):
    # Edit metodlarida content=text
    kwargs['message_id'] = message_id
    kwargs['inline_message_id'] = inline_message_id
    await _push_to_redis(chat_id, "edit_message_text", text, **kwargs)

async def patched_edit_message_caption(self, chat_id=None, message_id=None, inline_message_id=None, caption=None, **kwargs):
    kwargs['message_id'] = message_id
    kwargs['inline_message_id'] = inline_message_id
    await _push_to_redis(chat_id, "edit_message_caption", caption, **kwargs)

async def patched_edit_message_reply_markup(self, chat_id=None, message_id=None, inline_message_id=None, reply_markup=None, **kwargs):
    kwargs['message_id'] = message_id
    kwargs['inline_message_id'] = inline_message_id
    kwargs['reply_markup'] = reply_markup
    await _push_to_redis(chat_id, "edit_message_reply_markup", None, **kwargs)

async def patched_delete_message(self, chat_id, message_id, **kwargs):
    kwargs['message_id'] = message_id
    await _push_to_redis(chat_id, "delete_message", None, **kwargs)


def apply_redis_patch():
    # Bot klassini patch qilamiz
    Bot.send_message = patched_send_message
    Bot.send_video = patched_send_video
    Bot.edit_message_text = patched_edit_message_text
    Bot.edit_message_caption = patched_edit_message_caption
    Bot.edit_message_reply_markup = patched_edit_message_reply_markup
    Bot.delete_message = patched_delete_message

    # ExtBot ni ham patch qilamiz (chunki Application shuni ishlatadi)
    if ExtBot:
        ExtBot.send_message = patched_send_message
        ExtBot.send_video = patched_send_video
        ExtBot.edit_message_text = patched_edit_message_text
        ExtBot.edit_message_caption = patched_edit_message_caption
        ExtBot.edit_message_reply_markup = patched_edit_message_reply_markup
        ExtBot.delete_message = patched_delete_message
        logger.info("✅ ExtBot Patch applied")

    logger.info("✅ Redis Patch (Full Coverage) muvaffaqiyatli qo'llanildi")


async def _notify_video_failure(bot, chat_id, content, args, error_msg):
    """Video yuborilmaganda foydalanuvchiga va adminlarga xabar berish."""
    user_text = (
        "😔 <b>Kechirasiz!</b>\n\n"
        "Bu kino hozirda texnik nosozlik tufayli ko'rsatilmayapti.\n"
        "Adminlar xabardor qilindi va tez orada tuzatiladi! 🔧"
    )
    try:
        fallback_args = {}
        if "reply_markup" in args:
            fallback_args["reply_markup"] = args["reply_markup"]
        await _original_send_message(bot, chat_id=chat_id, text=user_text, parse_mode="HTML", **fallback_args)
    except Exception:
        await _original_send_message(bot, chat_id=chat_id, text=user_text, parse_mode="HTML")

    # Caption'dan kino nomi va kodini olish
    file_id_short = str(content)[:50] + "..." if len(str(content)) > 50 else str(content)
    caption = args.get("caption", "")
    movie_name = "Nomalum"
    movie_code = "—"
    name_match = re.search(r"🎬\s*<b>(.+?)</b>", caption)
    if name_match:
        movie_name = name_match.group(1)
    code_match = re.search(r"Kod:.*?<code>(\d+)</code>", caption)
    if code_match:
        movie_code = code_match.group(1)

    admin_text = (
        f"🚨 <b>Video yuborishda xato!</b>\n\n"
        f"🎬 <b>Kino:</b> {movie_name}\n"
        f"📥 <b>Kod:</b> <code>{movie_code}</code>\n"
        f"❌ <b>Xato:</b> <code>{error_msg[:200]}</code>\n"
        f"👤 <b>Chat ID:</b> <code>{chat_id}</code>\n"
        f"🎬 <b>File ID:</b> <code>{file_id_short}</code>\n\n"
        f"⚠️ Kinoning videosini qayta yuklash kerak!"
    )
    for admin_id in (ADMIN_ID, MANAGER_ID):
        if admin_id:
            try:
                await _original_send_message(bot, chat_id=admin_id, text=admin_text, parse_mode="HTML")
            except Exception:
                pass


async def _handle_message(bot, msg):
    """Navbatdan olingan bitta xabarni Telegramga yuborish.

    RetryAfter (flood-limit) bu yerda ushlanmaydi — uni run_worker boshqaradi.
    """
    method = msg['method']
    chat_id = msg['chat_id']
    content = msg['content']
    args = msg['args']

    if method == "send_message":
        try:
            await _original_send_message(bot, chat_id=chat_id, text=content, **args)
        except BadRequest as e:
            if "parse entities" in str(e).lower():
                safe_args = dict(args)
                safe_args.pop("parse_mode", None)
                await _original_send_message(bot, chat_id=chat_id, text=content, **safe_args)
            else:
                raise
        logger.debug("✅ MSG: %s", chat_id)

    elif method == "send_video":
        try:
            await _original_send_video(bot, chat_id=chat_id, video=content, **args)
        except BadRequest as e:
            await _notify_video_failure(bot, chat_id, content, args, str(e))
        logger.debug("✅ VID: %s", chat_id)

    elif method == "edit_message_text":
        try:
            await _original_edit_message_text(bot, text=content, chat_id=chat_id, **args)
            logger.debug("✅ EDIT TXT: %s", chat_id)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                raise

    elif method == "edit_message_caption":
        try:
            await _original_edit_message_caption(bot, caption=content, chat_id=chat_id, **args)
            logger.debug("✅ EDIT CAP: %s", chat_id)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                raise

    elif method == "edit_message_reply_markup":
        try:
            await _original_edit_message_reply_markup(bot, chat_id=chat_id, **args)
            logger.debug("✅ EDIT MKP: %s", chat_id)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                raise

    elif method == "delete_message":
        try:
            await _original_delete_message(bot, chat_id=chat_id, **args)
            logger.debug("✅ DEL: %s", chat_id)
        except BadRequest:
            pass  # Eski xabarni o'chirib bo'lmasa — e'tiborsiz qoldirish


async def _notify_admin(bot, text: str):
    try:
        await _original_send_message(
            bot,
            chat_id=ADMIN_ID,
            text=f"🚨 <b>Worker Xatoligi:</b>\n\n<code>{text[:500]}</code>",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _requeue(bot, msg: dict, *, reason: str) -> None:
    """Xabarni cheklangan urinishlar bilan navbat boshiga qaytarish.

    MAX_QUEUE_RETRIES dan oshsa — tashlab yuboriladi va adminga xabar beriladi
    (bitta yaroqsiz xabar butun navbatni bloklamasligi uchun).
    """
    retries = int(msg.get("_retries", 0)) + 1
    msg["_retries"] = retries

    if retries > MAX_QUEUE_RETRIES:
        logger.error(
            "❌ Xabar %s urinishdan keyin tashlandi | sabab=%s method=%s chat_id=%s",
            retries, reason, msg.get("method"), msg.get("chat_id"),
        )
        await _notify_admin(
            bot,
            f"Xabar yetkazilmadi ({retries} urinish): {reason} | "
            f"method={msg.get('method')} chat_id={msg.get('chat_id')}",
        )
        return

    try:
        await r.lpush(QUEUE_NAME, json.dumps(msg))
    except Exception as push_err:
        logger.error("❌ Xabarni qayta navbatga qo'yib bo'lmadi: %s", push_err)


async def run_worker(bot_token: str):
    bot = Bot(token=bot_token)
    logger.info("🚀 Worker ishga tushdi (Full Mode)...")

    while True:
        try:
            data = await r.blpop(QUEUE_NAME, timeout=1)
            if not data:
                continue
        except Exception as e:
            # Redis darajasidagi xato (ulanish uzilishi va h.k.)
            logger.error("❌ Redis blpop xatosi: %s", e)
            await asyncio.sleep(0.5)
            continue

        try:
            msg = json.loads(data[1])
        except (ValueError, TypeError) as e:
            logger.error("❌ Buzilgan xabar tashlab yuborildi: %s", e)
            continue

        try:
            await _handle_message(bot, msg)
        except RetryAfter as e:
            # Telegram flood-limit: kutib, xabarni qayta navbatga qaytaramiz.
            wait = min(int(getattr(e, "retry_after", 1)) + 1, MAX_RETRY_AFTER)
            logger.warning("⚠️ Flood limit, %ss kutilmoqda (chat_id=%s)", wait, msg.get("chat_id"))
            await asyncio.sleep(wait)
            await _requeue(bot, msg, reason="flood-limit")
            continue
        except Forbidden:
            # Foydalanuvchi botni bloklagan — qayta urinishdan ma'no yo'q
            logger.info("⛔ Foydalanuvchi bloklagan, xabar tashlandi (chat_id=%s)", msg.get("chat_id"))
            continue
        except Exception as e:
            # Kutilmagan xato — xabar yo'qolmasligi uchun cheklangan qayta urinish
            logger.error(
                "❌ Xabarni yuborishda xato: %s | method=%s chat_id=%s",
                e, msg.get("method"), msg.get("chat_id"),
            )
            await _requeue(bot, msg, reason=str(e))
            continue

        # Telegram limitidan oshmaslik uchun yuborishlar orasida pauza
        await asyncio.sleep(SEND_INTERVAL)
