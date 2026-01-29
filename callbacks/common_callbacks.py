from os import name
from telegram import Update
from telegram.ext import ContextTypes

from database import Genre, Countries
from admins import get_country_btns, get_genre_btns
from utils import error_notificator


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data_sp = query.data.split("_")
    await query.answer()

    if data_sp[1] == 'genre':
        if data_sp[2] == 'add':
            if data_sp[0] == 'confirm':
                try:
                    new_genre = context.user_data.pop('new_genre')
                    context.user_data.pop('add_genre_state')
                    await Genre.create(name=new_genre)
                    keyboard, i = await get_genre_btns()
                    await query.edit_message_text("Yangi janr qo'shildi", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_genre_btns()
                context.user_data.pop('new_genre')
                context.user_data.pop('add_genre_state')
                await query.edit_message_text('Janr qo\'shish bekor qilindi', reply_markup=keyboard)

        elif data_sp[2] == 'delete':
            if data_sp[0] == 'confirm':
                try:
                    genre_id = data_sp[3]
                    genre = await Genre.get(genre_id=genre_id)
                    await genre.delete()
                    keyboard, i = await get_genre_btns()
                    await query.edit_message_text("Janr o'chirildi", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_genre_btns()
                await query.edit_message_text("Janrni o'chirish bekor qilindi.", reply_markup=keyboard)


    elif data_sp[1] == 'country':
        if data_sp[2] == 'add':
            if data_sp[0] == 'confirm':
                try:
                    new_country = context.user_data.pop('new_country')
                    context.user_data.pop('add_country_state')

                    country = await Countries.get_or_none(name=new_country)
                    if country is not None:
                        keyboard, i = await get_country_btns()
                        await query.edit_message_text("Bu davlat allaqachon mavjud", reply_markup=keyboard)
                    else:
                        await Countries.create(name=new_country)
                        keyboard, i = await get_country_btns()
                        await query.edit_message_text("Yangi davlat qo'shildi", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_country_btns()
                context.user_data.pop('new_country')
                context.user_data.pop('add_country_state')
                await query.edit_message_text('Davlat qo\'shish bekor qilindi', reply_markup=keyboard)

        elif data_sp[2] == 'delete':
            if data_sp[0] == 'confirm':
                try:
                    country_id = data_sp[3]
                    country = await Countries.get(country_id=country_id)
                    await country.delete()
                    keyboard, i = await get_country_btns()
                    await query.edit_message_text("Davlat o'chirildi", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_country_btns()
                await query.edit_message_text("Davlatni o'chirish bekor qilindi.", reply_markup=keyboard)




