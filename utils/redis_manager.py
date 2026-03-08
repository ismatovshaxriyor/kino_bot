import json
import asyncio
import redis.asyncio as redis
from telegram import Bot
from telegram.error import BadRequest
from .settings import ADMIN_ID, MANAGER_ID
try:
    from telegram.ext import ExtBot
except ImportError:
    ExtBot = None

REDIS_URL = "redis://localhost"
QUEUE_NAME = "bot_queue"

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
        print(f"❌ Redis Push Error: {e}")

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
        print("✅ ExtBot Patch applied")

    print("✅ Redis Patch (Full Coverage) muvaffaqiyatli qo'llanildi")

async def run_worker(bot_token: str):
    bot = Bot(token=bot_token)
    print("🚀 Worker ishga tushdi (Full Mode)...")

    msg = None
    while True:
        try:
            data = await r.blpop(QUEUE_NAME, timeout=1)

            if data:
                msg = json.loads(data[1])

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
                    print(f"✅ MSG: {chat_id}")

                elif method == "send_video":
                    try:
                        await _original_send_video(bot, chat_id=chat_id, video=content, **args)
                    except BadRequest as e:
                        error_msg = str(e)
                        # Foydalanuvchiga do'stona xabar yuborish
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

                        # Barcha adminlarga xato sababini yuborish
                        file_id_short = str(content)[:50] + "..." if len(str(content)) > 50 else str(content)
                        admin_text = (
                            f"🚨 <b>Video yuborishda xato!</b>\n\n"
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
                    print(f"✅ VID: {chat_id}")

                elif method == "edit_message_text":
                    try:
                        await _original_edit_message_text(bot, text=content, chat_id=chat_id, **args)
                        print(f"✅ EDIT TXT: {chat_id}")
                    except BadRequest as e:
                        if "message is not modified" in str(e).lower():
                            pass
                        else:
                            raise

                elif method == "edit_message_caption":
                    try:
                        await _original_edit_message_caption(bot, caption=content, chat_id=chat_id, **args)
                        print(f"✅ EDIT CAP: {chat_id}")
                    except BadRequest as e:
                        if "message is not modified" in str(e).lower():
                            pass
                        else:
                            raise

                elif method == "edit_message_reply_markup":
                    try:
                        await _original_edit_message_reply_markup(bot, chat_id=chat_id, **args)
                        print(f"✅ EDIT MKP: {chat_id}")
                    except BadRequest as e:
                        if "message is not modified" in str(e).lower():
                            pass
                        else:
                            raise

                elif method == "delete_message":
                    try:
                        await _original_delete_message(bot, chat_id=chat_id, **args)
                        print(f"✅ DEL: {chat_id}")
                    except BadRequest:
                        pass  # Eski xabarni o'chirib bo'lmasa — e'tiborsiz qoldirish

        except Exception as e:
            if msg:
                method = msg.get("method")
                content = str(msg.get("content", ""))[:80]
                chat_id = msg.get("chat_id")
                error_text = f"❌ Worker Xatoligi: {e} | method={method} chat_id={chat_id} content={content}"
                print(error_text)
            else:
                error_text = f"❌ Worker Xatoligi: {e}"
                print(error_text)

            # Adminga xabar yuborish
            try:
                await _original_send_message(
                    bot,
                    chat_id=ADMIN_ID,
                    text=f"🚨 <b>Worker Xatoligi:</b>\n\n<code>{str(e)[:500]}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

            await asyncio.sleep(0.1)
