import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Channels, ChannelSubscription
from admins import get_channel_btns


async def channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_sp = query.data.split('_')

    if data_sp[1] == 'add':
        await query.delete_message()
        context.user_data['state'] = "WAITING_CHANNEL_USERNAME"

        await update.effective_message.reply_text(
            "Kanal username yoki ID kiriting:\n\n"
            "📌 Misol:\n"
            "• @kanal_nomi\n"
            "• -100xxxxxxxxxx (kanal ID)"
        )

    elif data_sp[1] == 'delete':
        # channel_delete_-100xxx formatida keladi
        channel_id = int('_'.join(data_sp[2:]))

        confirm_btns = [
            [
                InlineKeyboardButton(text='✅ Tasdiqlash', callback_data=f'confirm_channel_delete_{channel_id}'),
                InlineKeyboardButton(text='❌ Bekor qilish', callback_data='reject_channel_delete')
            ]
        ]

        channel = await Channels.get_or_none(channel_id=channel_id)
        if channel:
            keyboard = InlineKeyboardMarkup(confirm_btns)
            username_text = f"@{channel.username}" if channel.username else "yo'q"
            await query.edit_message_text(
                f"📢 Kanal: {channel.name}\n"
                f"🆔 ID: {channel.channel_id}\n"
                f"👤 Username: {username_text}\n\n"
                "⚠️ O'chirishni tasdiqlang.",
                reply_markup=keyboard
            )
        else:
            keyboard, i = await get_channel_btns()
            await query.edit_message_text("Kanal topilmadi.", reply_markup=keyboard)

    elif data_sp[1] == 'back':
        keyboard, i = await get_channel_btns()

        if i == 1:
            await query.edit_message_text("Kanallar topilmadi.", reply_markup=keyboard)
        else:
            await query.edit_message_text('📢 Kanallar:', reply_markup=keyboard)

    else:
        # channel_{channel_id} formatida - kanal tanlash
        # channel_id manfiy bo'lishi mumkin: channel_-100xxx
        try:
            channel_id = int('_'.join(data_sp[1:]))
            channel = await Channels.get_or_none(channel_id=channel_id)

            if channel:
                btns = [
                    [
                        InlineKeyboardButton("🗑 O'chirish", callback_data=f"channel_delete_{channel_id}"),
                        InlineKeyboardButton("⬅️ Ortga qaytish", callback_data='channel_back')
                    ]
                ]
                keyboard = InlineKeyboardMarkup(btns)
                username_text = f"@{channel.username}" if channel.username else "yo'q"
                await query.edit_message_text(
                    f"📢 Kanal: {channel.name}\n"
                    f"🆔 ID: {channel.channel_id}\n"
                    f"👤 Username: {username_text}\n\n"
                    "Harakatni tanlang:",
                    reply_markup=keyboard
                )
            else:
                btn = [[InlineKeyboardButton("⬅️ Ortga qaytish", callback_data='channel_back')]]
                keyboard = InlineKeyboardMarkup(btn)
                await query.edit_message_text("Kanal allaqachon o'chirilgan.", reply_markup=keyboard)
        except ValueError:
            pass


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi a'zoligini qayta tekshirish callback'i"""
    from utils.checker import is_user_subscribed

    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    channels = await Channels.all()

    if not channels:
        await query.edit_message_text("✅ Hozircha majburiy kanallar yo'q.")
        return

    membership_results = await asyncio.gather(*(
        is_user_subscribed(
            context.bot,
            user_id,
            f"@{channel.username}" if channel.username else channel.channel_id,
        )
        for channel in channels
    ))
    not_subscribed = [
        channel for channel, is_member in zip(channels, membership_results) if not is_member
    ]

    if not_subscribed:
        btns = []
        for ch in not_subscribed:
            url = f"https://t.me/{ch.username}" if ch.username else f"https://t.me/c/{str(ch.channel_id)[4:]}"
            btns.append([InlineKeyboardButton(f"📢 {ch.name}", url=url)])

        btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription")])
        keyboard = InlineKeyboardMarkup(btns)

        await query.edit_message_text(
            "⚠️ Siz hali barcha kanallarga a'zo bo'lmadingiz!\n\n"
            "Quyidagi kanallarga a'zo bo'ling:",
            reply_markup=keyboard
        )
    else:
        # Har bir kanal uchun "bot orqali tasdiqlangan obunachi" hodisasini
        # belgilaymiz (statistika uchun) — get_or_create bo'lgani sabab
        # foydalanuvchi qayta tekshirsa ham qatorlar takrorlanmaydi.
        await asyncio.gather(*(
            ChannelSubscription.get_or_create(channel=channel, telegram_id=user_id)
            for channel in channels
        ))

        await query.edit_message_text(
            "✅ Ajoyib! Siz barcha kanallarga a'zo bo'ldingiz!\n\n"
            "Endi botdan foydalanishingiz mumkin. /start bosing."
        )
