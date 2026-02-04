from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Countries
from admins import get_country_btns


async def country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_sp = query.data.split('_')

    if data_sp[1] == 'add':
        await query.delete_message()
        context.user_data['state'] = "WAITING_COUNTRY_NAME"

        await update.effective_message.reply_text("✍️ Yangi davlat nomini kiriting:")

    elif data_sp[1].isdigit():
        country_id = data_sp[1]
        country = await Countries.get_or_none(country_id=country_id)

        if country:
            btns = [
                [
                    InlineKeyboardButton("🗑 O'chirish", callback_data=f"country_delete_{country_id}"),
                    InlineKeyboardButton("⬅️ Ortga", callback_data='country_back')
                ]
            ]
            keyboard = InlineKeyboardMarkup(btns)

            await query.edit_message_text(f"🌍 <b>Davlat:</b> {country.name}\n\n👇 Harakatni tanlang:", reply_markup=keyboard, parse_mode="HTML")
        else:
            btn = [[InlineKeyboardButton("⬅️ Ortga", callback_data='country_back')]]
            keyboard = InlineKeyboardMarkup(btn)

            await query.edit_message_text("⚠️ Davlat allaqachon o'chirilgan.", reply_markup=keyboard)

    elif data_sp[1] == 'delete':
        country_id = data_sp[2]

        confirm_btns = [
            [
                InlineKeyboardButton(text='✅ Tasdiqlash', callback_data=f'confirm_country_delete_{country_id}'),
                InlineKeyboardButton(text='❌ Bekor qilish', callback_data='reject_country_delete')
            ]
        ]

        country = await Countries.get(country_id=country_id)
        keyboard = InlineKeyboardMarkup(confirm_btns)
        await query.edit_message_text(f"⚠️ <b>Davlat:</b> {country.name}\n\n🗑 O'chirishni tasdiqlaysizmi?", reply_markup=keyboard, parse_mode="HTML")

    elif data_sp[1] == 'back':
        keyboard, i = await get_country_btns()

        if i == 1:
            await query.edit_message_text("📭 Davlatlar topilmadi.", reply_markup=keyboard)
        else:
            await query.edit_message_text('🌍 <b>Davlatlar ro\'yxati:</b>', reply_markup=keyboard, parse_mode="HTML")



