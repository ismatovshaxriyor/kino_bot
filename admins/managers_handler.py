from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import User, USER_TYPE
from utils import error_notificator, admin_required


async def get_managers_btns():
    managers = await User.filter(user_type=USER_TYPE.ADMIN)
    manager_btns = []

    if managers:
        btns = []
        for i, manager in enumerate(managers):
            btn = InlineKeyboardButton(text=f"{manager.first_name} {manager.last_name if manager.last_name else None}", callback_data=f"manager_{manager.id}")
            btns.append(btn)
            if i % 2 == 1:
                manager_btns.append(btns)
                btns = []

        if btns:
            manager_btns.append(btns)

        manager_btns += [[InlineKeyboardButton('Manager qo\'shish', callback_data='manager_add')]]
        keyboard = InlineKeyboardMarkup(manager_btns)

    else:
        manager_btns += [[InlineKeyboardButton('Manager qo\'shish', callback_data='manager_add')]]
        keyboard = InlineKeyboardMarkup(manager_btns)
        i = 1

    return [keyboard, i]

@admin_required
async def get_managers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        manager_btns, i = await get_managers_btns()
        if i == 1:
            await update.message.reply_text("Managerlar topilmadi.", reply_markup=manager_btns)
        else:
            await update.message.reply_text("Managerlar:", reply_markup=manager_btns)
    except Exception as e:
        await error_notificator.notify(context, e, update)






