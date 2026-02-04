from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import Channels
from utils import error_notificator, admin_required


async def get_channel_btns():
    channels = await Channels.all()
    channel_btns = []

    if channels:
        btns = []
        for i, channel in enumerate(channels):
            btn = InlineKeyboardButton(text=f"📢 {channel.name}", callback_data=f"channel_{channel.channel_id}")
            btns.append(btn)
            if i % 2 == 1:
                channel_btns.append(btns)
                btns = []

        if btns:
            channel_btns.append(btns)

        channel_btns += [[InlineKeyboardButton('➕ Kanal qo\'shish', callback_data='channel_add')]]
        keyboard = InlineKeyboardMarkup(channel_btns)

    else:
        channel_btns += [[InlineKeyboardButton('➕ Kanal qo\'shish', callback_data='channel_add')]]
        keyboard = InlineKeyboardMarkup(channel_btns)
        i = 1

    return [keyboard, i]

@admin_required
async def get_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        channel_btns, i = await get_channel_btns()
        if i == 1:
            await update.message.reply_text("📭 Kanallar topilmadi.", reply_markup=channel_btns)
        else:
            await update.message.reply_text("📢 <b>Kanallar ro'yxati:</b>", reply_markup=channel_btns, parse_mode="HTML")
    except Exception as e:
        await error_notificator.notify(context, e, update)



