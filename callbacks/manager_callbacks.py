from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import User
from admins import get_managers_btns


async def manager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_sp = query.data.split('_')

    if data_sp[1] == 'add':
        await query.delete_message()
        context.user_data['state'] = "WAITING_MANAGER_ID"

        await update.effective_message.reply_text("Yangi managerning Idsini kiriting:")

    elif data_sp[1].isdigit():
        manager_id = data_sp[1]
        manager = await User.get(id=manager_id)

        btns = [
            [
                InlineKeyboardButton("O'chirish", callback_data=f"manager_delete_{manager_id}"),
                InlineKeyboardButton("Ortga qaytish", callback_data='manager_back')
            ]
        ]
        keyboard = InlineKeyboardMarkup(btns)

        await query.edit_message_text(f"Manager: {manager.first_name}\n\nharakatni tanlang:", reply_markup=keyboard)

    elif data_sp[1] == 'delete':
        manager_id = data_sp[2]

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data=f'confirm_manager_delete_{manager_id}'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_manager_delete')
            ]
        ]

        manager = await User.get(id=manager_id)
        keyboard = InlineKeyboardMarkup(confirm_btns)
        await query.edit_message_text(f"Manager: {manager.first_name}\n\nO'chirishni tasdiqlang.", reply_markup=keyboard)

    elif data_sp[1] == 'back':
        keyboard, i = await get_managers_btns()

        if i == 1:
            await query.edit_message_text("Managerlar topilmadi.", reply_markup=keyboard)
        else:
            await query.edit_message_text('Managerlar:', reply_markup=keyboard)



