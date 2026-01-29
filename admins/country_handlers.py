from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import Countries
from utils import error_notificator, admin_required


async def get_country_btns():
    countries = await Countries.all()
    country_btns = []

    if countries:
        btns = []
        for i, country in enumerate(countries):
            btn = InlineKeyboardButton(text=f"{country.name}", callback_data=f"country_{country.country_id}")
            btns.append(btn)
            if i % 2 == 1:
                country_btns.append(btns)
                btns = []

        if btns:
            country_btns.append(btns)

        country_btns += [[InlineKeyboardButton('Davlat qo\'shish', callback_data='country_add')]]
        keyboard = InlineKeyboardMarkup(country_btns)

    else:
        country_btns += [[InlineKeyboardButton('Davlat qo\'shish', callback_data='country_add')]]
        keyboard = InlineKeyboardMarkup(country_btns)
        i = 1

    return [keyboard, i]

@admin_required
async def get_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        country_btns, i = await get_country_btns()
        if i == 1:
            await update.message.reply_text("Davlat topilmadi.", reply_markup=country_btns)
        else:
            await update.message.reply_text("Davlatlar:", reply_markup=country_btns)
    except Exception as e:
        await error_notificator.notify(context, e, update)






