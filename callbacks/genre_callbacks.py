from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Genre
from admins import get_genre_btns


async def genre_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_sp = query.data.split('_')

    if data_sp[1] == 'add':
        await query.delete_message()
        context.user_data['state'] = "WAITING_GENRE_NAME"

        await update.effective_message.reply_text("✍️ Yangi janr nomini kiriting:")

    elif data_sp[1].isdecimal():
        genre_id = data_sp[1]
        genre = await Genre.get_or_none(genre_id=genre_id)


        if genre:
            btns = [
                [
                    InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"genre_edit_{genre_id}"),
                    InlineKeyboardButton("🗑 O'chirish", callback_data=f"genre_delete_{genre_id}"),
                ],
                [
                    InlineKeyboardButton("⬅️ Ortga", callback_data='genre_back')
                ]
            ]
            keyboard = InlineKeyboardMarkup(btns)
            await query.edit_message_text(f"🎭 <b>Janr:</b> {genre.name}\n\n👇 Harakatni tanlang:", reply_markup=keyboard, parse_mode="HTML")
        else:
            btn = [[InlineKeyboardButton("⬅️ Ortga", callback_data='genre_back')]]
            keyboard = InlineKeyboardMarkup(btn)
            await query.edit_message_text("⚠️ Janr allaqachon o'chirilgan.", reply_markup=keyboard)

    elif data_sp[1] == 'delete':
        genre_id = data_sp[2]

        confirm_btns = [
            [
                InlineKeyboardButton(text='✅ Tasdiqlash', callback_data=f'confirm_genre_delete_{genre_id}'),
                InlineKeyboardButton(text='❌ Bekor qilish', callback_data='reject_genre_delete')
            ]
        ]

        genre = await Genre.get(genre_id=genre_id)
        keyboard = InlineKeyboardMarkup(confirm_btns)
        await query.edit_message_text(f"⚠️ <b>Janr:</b> {genre.name}\n\n🗑 O'chirishni tasdiqlaysizmi?", reply_markup=keyboard, parse_mode="HTML")

    elif data_sp[1] == 'back':
        keyboard, i = await get_genre_btns()

        if i == 1:
            await query.edit_message_text("📭 Janrlar topilmadi.", reply_markup=keyboard)
        else:
            await query.edit_message_text('🎭 <b>Janrlar ro\'yxati:</b>', reply_markup=keyboard, parse_mode="HTML")


    elif data_sp[1] == "edit":
        genre_id = data_sp[2]
        genre = await Genre.get_or_none(genre_id=genre_id)
        if not genre:
            btn = [[InlineKeyboardButton("⬅️ Ortga", callback_data='genre_back')]]
            await query.edit_message_text("⚠️ Janr topilmadi.", reply_markup=InlineKeyboardMarkup(btn))
            return

        context.user_data["state"] = "WAITING_GENRE_EDIT_NAME"
        context.user_data["edit_genre_id"] = int(genre_id)

        await query.edit_message_text(
            f"✍️ <b>Janrni tahrirlash</b>\n\n"
            f"Joriy nom: <b>{genre.name}</b>\n"
            "Yangi nomni yuboring:",
            parse_mode="HTML",
        )
