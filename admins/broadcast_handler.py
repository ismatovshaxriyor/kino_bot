import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    ConversationHandler, MessageHandler, CallbackQueryHandler,
    CommandHandler, ContextTypes, filters,
)

from database import User
from utils import admin_required, ADMIN_ID
from utils.admin_btns import admin_keyboard

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


async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasdiqlash — barcha userlarga yuborish"""
    query = update.callback_query
    await query.answer()

    msg_id = context.user_data.get('broadcast_msg_id')
    from_chat_id = context.user_data.get('broadcast_chat_id')

    if not msg_id or not from_chat_id:
        await query.edit_message_text("❌ Xato: xabar topilmadi.")
        return ConversationHandler.END

    users = await User.all()
    total = len(users)
    sent = 0
    blocked = 0

    # Status xabari
    status_msg = await query.edit_message_text(
        f"📤 <b>Yuborilmoqda...</b>\n\n"
        f"📊 0/{total} | ✅ 0 | ❌ 0",
        parse_mode="HTML",
    )

    for i, user in enumerate(users):
        try:
            await context.bot.copy_message(
                chat_id=user.telegram_id,
                from_chat_id=from_chat_id,
                message_id=msg_id,
            )
            sent += 1
        except Forbidden:
            blocked += 1
        except BadRequest:
            blocked += 1
        except Exception:
            blocked += 1

        # Progress: har 50 ta userda yangilash
        if (i + 1) % 50 == 0 or (i + 1) == total:
            try:
                await status_msg.edit_text(
                    f"📤 <b>Yuborilmoqda...</b>\n\n"
                    f"📊 {i + 1}/{total} | ✅ {sent} | ❌ {blocked}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        # Telegram rate limit dan himoya
        await asyncio.sleep(0.05)

    # Yakuniy natija
    try:
        await status_msg.edit_text(
            f"✅ <b>Yuborish yakunlandi!</b>\n\n"
            f"📊 Jami: {total}\n"
            f"✅ Yuborildi: {sent}\n"
            f"❌ Blok/xato: {blocked}",
            parse_mode="HTML",
        )
    except Exception:
        pass

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
            reply_markup=admin_keyboard,
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
