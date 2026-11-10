import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest, RetryAfter
from telegram.ext import (
    ConversationHandler, MessageHandler, CallbackQueryHandler,
    CommandHandler, ContextTypes, filters,
)

from database import User
from utils import admin_required, ADMIN_ID
from utils.admin_btns import get_admin_keyboard
from utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

WAITING_BROADCAST, CONFIRM_BROADCAST = range(2)


@admin_required
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin 'Xabar yuborish' tugmasini bosganda"""
    await update.message.reply_text(
        "📣 <b>Ommaviy xabar yuborish</b>\n\n"
        "Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring.\n"
        "Matn, rasm, video, audio, stiker — har qanday turdagi xabar qabul qilinadi.\n\n"
        "❌ Bekor qilish: /cancel",
        parse_mode="HTML",
    )
    return WAITING_BROADCAST


async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminning xabarini qabul qilish va preview ko'rsatish"""
    context.user_data['broadcast_msg_id'] = update.message.message_id
    context.user_data['broadcast_chat_id'] = update.message.chat_id

    # Foydalanuvchilar sonini olish
    total_users = await User.all().count()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data="broadcast_confirm"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data="broadcast_cancel"),
        ]
    ])

    await update.message.reply_text(
        f"📣 <b>Xabar tayyor!</b>\n\n"
        f"👥 Jami: <b>{total_users}</b> ta foydalanuvchiga yuboriladi.\n\n"
        f"☝️ Yuqoridagi xabar barcha foydalanuvchilarga yuboriladi.\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return CONFIRM_BROADCAST


# Parallel yuborish sozlamalari. Telegram umumiy limiti ~30 xabar/s — undan pastroq tezlikda yuboramiz.
BROADCAST_CONCURRENCY = 20   # bir vaqtda uchib yurgan so'rovlar soni (har biri ~100-150 ms kutadi)
BROADCAST_RATE = 20          # xabar/soniya; worker (~15/s) bilan birga Telegram ~30/s limitiga yaqin
PROGRESS_EVERY = 50

# Fon vazifaga kuchli havola (aks holda chiqindi yig'uvchi uni o'rtasida o'chirishi mumkin)
_background_tasks: set = set()
_broadcast_running = False


async def _broadcast_worker(bot, from_chat_id: int, msg_id: int, status_chat_id: int, status_msg_id: int):
    """Background task: barcha userlarga parallel (limitlangan tezlikda) xabar yuborish"""
    global _broadcast_running
    try:
        # Faqat ID'larni yuklaymiz (butun User obyektlari emas) — xotira tejaladi
        user_ids = await User.all().values_list("telegram_id", flat=True)
        total = len(user_ids)
        stats = {"sent": 0, "blocked": 0, "done": 0}
        limiter = RateLimiter(BROADCAST_RATE)
        loop = asyncio.get_running_loop()
        pause = {"until": 0.0}  # flood-limit: hamma yuboruvchilar uchun umumiy pauza
        started = loop.time()
        logger.info("📤 Broadcast boshlandi: %s ta foydalanuvchi", total)

        async def send_one(telegram_id: int):
            for _ in range(3):
                delay = pause["until"] - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                await limiter.wait()
                try:
                    await bot.copy_message(
                        chat_id=telegram_id,
                        from_chat_id=from_chat_id,
                        message_id=msg_id,
                    )
                    stats["sent"] += 1
                    return
                except RetryAfter as e:
                    wait = int(getattr(e, "retry_after", 1)) + 1
                    pause["until"] = max(pause["until"], loop.time() + wait)
                    logger.warning("⚠️ Broadcast: flood-limit, %ss kutilmoqda", wait)
                except (Forbidden, BadRequest):
                    stats["blocked"] += 1
                    return
                except Exception as e:
                    logger.warning("Broadcast: %s ga yuborilmadi: %s", telegram_id, e)
                    stats["blocked"] += 1
                    return
            stats["blocked"] += 1  # 3 urinishda ham flood-limit

        async def report_progress():
            stats["done"] += 1
            done = stats["done"]
            if done % PROGRESS_EVERY != 0 and done != total:
                return
            logger.info("📤 Broadcast: %s/%s | yuborildi=%s xato=%s", done, total, stats["sent"], stats["blocked"])
            try:
                await bot.edit_message_text(
                    chat_id=status_chat_id,
                    message_id=status_msg_id,
                    text=(
                        f"📤 <b>Yuborilmoqda...</b>\n\n"
                        f"📊 {done}/{total} | ✅ {stats['sent']} | ❌ {stats['blocked']}"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        users_iter = iter(user_ids)  # umumiy iterator: asyncio'da har runner keyingisini oladi

        async def runner():
            for telegram_id in users_iter:
                await send_one(telegram_id)
                await report_progress()

        await asyncio.gather(*(runner() for _ in range(BROADCAST_CONCURRENCY)))

        elapsed = int(loop.time() - started)
        logger.info(
            "✅ Broadcast tugadi: jami=%s yuborildi=%s xato=%s (%s soniya)",
            total, stats["sent"], stats["blocked"], elapsed,
        )
        try:
            await bot.edit_message_text(
                chat_id=status_chat_id,
                message_id=status_msg_id,
                text=(
                    f"✅ <b>Yuborish yakunlandi!</b>\n\n"
                    f"📊 Jami: {total}\n"
                    f"✅ Yuborildi: {stats['sent']}\n"
                    f"❌ Blok/xato: {stats['blocked']}\n"
                    f"⏱ Vaqt: {elapsed // 60} daq {elapsed % 60} son"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except asyncio.CancelledError:
        logger.warning("⚠️ Broadcast bekor qilindi (bot to'xtayaptimi?)")
        raise
    except Exception:
        logger.exception("❌ Broadcast xato bilan to'xtadi")
        try:
            await bot.edit_message_text(
                chat_id=status_chat_id,
                message_id=status_msg_id,
                text="❌ Xabar yuborish kutilmagan xato bilan to'xtadi. Loglarni ko'ring.",
            )
        except Exception:
            pass
    finally:
        _broadcast_running = False


async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasdiqlash — background task orqali barcha userlarga yuborish"""
    global _broadcast_running
    query = update.callback_query
    await query.answer()

    msg_id = context.user_data.get('broadcast_msg_id')
    from_chat_id = context.user_data.get('broadcast_chat_id')

    if not msg_id or not from_chat_id:
        await query.edit_message_text("❌ Xato: xabar topilmadi.")
        return ConversationHandler.END

    if _broadcast_running:
        await query.edit_message_text("⏳ Oldingi xabar hali yuborilmoqda. Tugashini kuting.")
        return ConversationHandler.END

    total = await User.all().count()

    # Status xabari — query.message dan chat_id va message_id olamiz
    status_chat_id = query.message.chat_id
    status_msg_id = query.message.message_id

    await query.edit_message_text(
        f"📤 <b>Yuborilmoqda...</b>\n\n"
        f"📊 0/{total} | ✅ 0 | ❌ 0",
        parse_mode="HTML",
    )

    # Background task ishga tushirish — bot qotib qolmaydi
    _broadcast_running = True
    task = asyncio.create_task(
        _broadcast_worker(
            bot=context.bot,
            from_chat_id=from_chat_id,
            msg_id=msg_id,
            status_chat_id=status_chat_id,
            status_msg_id=status_msg_id,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bekor qilish (callback yoki /cancel)"""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "❌ <b>Xabar yuborish bekor qilindi.</b>",
            parse_mode="HTML",
        )
    elif update.message:
        await update.message.reply_text(
            "❌ <b>Xabar yuborish bekor qilindi.</b>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(update.effective_chat.id),
        )

    context.user_data.pop('broadcast_msg_id', None)
    context.user_data.pop('broadcast_chat_id', None)
    return ConversationHandler.END


broadcast_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(r"📣 Xabar yuborish") & filters.ChatType.PRIVATE, start_broadcast),
    ],
    states={
        WAITING_BROADCAST: [
            MessageHandler(~filters.COMMAND, receive_broadcast),
        ],
        CONFIRM_BROADCAST: [
            CallbackQueryHandler(confirm_broadcast, pattern=r"^broadcast_confirm$"),
            CallbackQueryHandler(cancel_broadcast, pattern=r"^broadcast_cancel$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_broadcast),
    ],
)
