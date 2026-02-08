from telegram import Update
from telegram.ext import ContextTypes

from database import Genre, Countries, User
from admins import get_country_btns, get_genre_btns, get_managers_btns
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
                    context.user_data.pop('state')
                    await Genre.create(name=new_genre)
                    keyboard, i = await get_genre_btns()
                    await query.edit_message_text("✅ Yangi janr muvaffaqiyatli qo'shildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_genre_btns()
                context.user_data.pop('new_genre')
                context.user_data.pop('state', None)
                await query.edit_message_text('❌ Janr qo\'shish bekor qilindi', reply_markup=keyboard)

        elif data_sp[2] == 'delete':
            if data_sp[0] == 'confirm':
                try:
                    genre_id = data_sp[3]
                    genre = await Genre.get(genre_id=genre_id)
                    await genre.delete()
                    keyboard, i = await get_genre_btns()
                    await query.edit_message_text("✅ Janr muvaffaqiyatli o'chirildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_genre_btns()
                await query.edit_message_text("❌ Janrni o'chirish bekor qilindi.", reply_markup=keyboard)

        elif data_sp[2] == 'edit':
            if data_sp[0] == 'confirm':
                try:
                    genre_id = int(data_sp[3])
                    new_name = context.user_data.pop('edit_genre_name', None)
                    context.user_data.pop('edit_genre_id', None)
                    context.user_data.pop('state', None)

                    keyboard, i = await get_genre_btns()
                    if not new_name:
                        await query.edit_message_text("⚠️ Yangi janr nomi topilmadi.", reply_markup=keyboard)
                        return

                    exists = await Genre.get_or_none(name=new_name)
                    if exists and exists.genre_id != genre_id:
                        await query.edit_message_text("⚠️ Bu janr nomi allaqachon mavjud.", reply_markup=keyboard)
                        return

                    genre = await Genre.get_or_none(genre_id=genre_id)
                    if not genre:
                        await query.edit_message_text("⚠️ Janr topilmadi.", reply_markup=keyboard)
                        return

                    genre.name = new_name
                    await genre.save()
                    await query.edit_message_text("✅ Janr muvaffaqiyatli yangilandi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_genre_btns()
                context.user_data.pop('edit_genre_name', None)
                context.user_data.pop('edit_genre_id', None)
                context.user_data.pop('state', None)
                await query.edit_message_text("❌ Janrni tahrirlash bekor qilindi.", reply_markup=keyboard)


    elif data_sp[1] == 'country':
        if data_sp[2] == 'add':
            if data_sp[0] == 'confirm':
                try:
                    new_country = context.user_data.pop('new_country')
                    context.user_data.pop('state')

                    country = await Countries.get_or_none(name=new_country)
                    if country is not None:
                        keyboard, i = await get_country_btns()
                        await query.edit_message_text("⚠️ Bu davlat allaqachon mavjud", reply_markup=keyboard)
                    else:
                        await Countries.create(name=new_country)
                        keyboard, i = await get_country_btns()
                        await query.edit_message_text("✅ Yangi davlat muvaffaqiyatli qo'shildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_country_btns()
                context.user_data.pop('new_country')
                context.user_data.pop('state', None)
                await query.edit_message_text('❌ Davlat qo\'shish bekor qilindi', reply_markup=keyboard)

        elif data_sp[2] == 'delete':
            if data_sp[0] == 'confirm':
                try:
                    country_id = data_sp[3]
                    country = await Countries.get(country_id=country_id)
                    await country.delete()
                    keyboard, i = await get_country_btns()
                    await query.edit_message_text("✅ Davlat muvaffaqiyatli o'chirildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_country_btns()
                await query.edit_message_text("❌ Davlatni o'chirish bekor qilindi.", reply_markup=keyboard)

        elif data_sp[2] == 'edit':
            if data_sp[0] == 'confirm':
                try:
                    country_id = int(data_sp[3])
                    new_name = context.user_data.pop('edit_country_name', None)
                    context.user_data.pop('edit_country_id', None)
                    context.user_data.pop('state', None)

                    keyboard, i = await get_country_btns()
                    if not new_name:
                        await query.edit_message_text("⚠️ Yangi davlat nomi topilmadi.", reply_markup=keyboard)
                        return

                    exists = await Countries.get_or_none(name=new_name)
                    if exists and exists.country_id != country_id:
                        await query.edit_message_text("⚠️ Bu davlat nomi allaqachon mavjud.", reply_markup=keyboard)
                        return

                    country = await Countries.get_or_none(country_id=country_id)
                    if not country:
                        await query.edit_message_text("⚠️ Davlat topilmadi.", reply_markup=keyboard)
                        return

                    country.name = new_name
                    await country.save()
                    await query.edit_message_text("✅ Davlat muvaffaqiyatli yangilandi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_country_btns()
                context.user_data.pop('edit_country_name', None)
                context.user_data.pop('edit_country_id', None)
                context.user_data.pop('state', None)
                await query.edit_message_text("❌ Davlatni tahrirlash bekor qilindi.", reply_markup=keyboard)

    elif data_sp[1] == 'manager':
        if data_sp[2] == 'add':
            if data_sp[0] == 'confirm':
                try:
                    new_manager = context.user_data.pop('new_manager')
                    context.user_data.pop('state')

                    user = await User.get(telegram_id=new_manager)
                    if user.user_type == 'admin':
                        keyboard, i = await get_managers_btns()
                        await query.edit_message_text("⚠️ Bu foydalanuvchi allaqachon manager qilingan.", reply_markup=keyboard)
                    else:
                        await user.update_from_dict({"user_type": "admin"})
                        await user.save()
                        keyboard, i = await get_managers_btns()
                        await query.edit_message_text("✅ Yangi manager muvaffaqiyatli qo'shildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_managers_btns()
                context.user_data.pop('new_manager')
                context.user_data.pop('state')
                await query.edit_message_text('❌ Manager qo\'shish bekor qilindi', reply_markup=keyboard)

        elif data_sp[2] == 'delete':
            if data_sp[0] == 'confirm':
                try:
                    manager_id = data_sp[3]
                    user = await User.get(id=manager_id)
                    await user.update_from_dict(data={"user_type": 'user'})
                    await user.save()
                    keyboard, i = await get_managers_btns()
                    await query.edit_message_text("✅ Manager muvaffaqiyatli o'chirildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_managers_btns()
                await query.edit_message_text("❌ Managerni o'chirish bekor qilindi.", reply_markup=keyboard)

    elif data_sp[1] == 'channel':
        from admins import get_channel_btns
        from database import Channels

        if data_sp[2] == 'add':
            if data_sp[0] == 'confirm':
                try:
                    channel_id = context.user_data.pop('channel_id')
                    channel_name = context.user_data.pop('channel_name')
                    channel_username = context.user_data.pop('channel_username', None)
                    context.user_data.pop('state')

                    existing_channel = await Channels.get_or_none(channel_id=channel_id)
                    if existing_channel is not None:
                        keyboard, i = await get_channel_btns()
                        await query.edit_message_text("Bu kanal allaqachon mavjud.", reply_markup=keyboard)
                    else:
                        await Channels.create(
                            channel_id=channel_id,
                            name=channel_name,
                            username=channel_username if channel_username else ""
                        )
                        keyboard, i = await get_channel_btns()
                        await query.edit_message_text("✅ Yangi kanal qo'shildi!", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_channel_btns()
                context.user_data.pop('channel_id', None)
                context.user_data.pop('channel_name', None)
                context.user_data.pop('channel_username', None)
                context.user_data.pop('state', None)
                await query.edit_message_text("❌ Kanal qo'shish bekor qilindi.", reply_markup=keyboard)

        elif data_sp[2] == 'delete':
            if data_sp[0] == 'confirm':
                try:
                    channel_id = int(data_sp[3])
                    channel = await Channels.get_or_none(channel_id=channel_id)
                    if channel:
                        await channel.delete()
                        keyboard, i = await get_channel_btns()
                        await query.edit_message_text("✅ Kanal o'chirildi!", reply_markup=keyboard)
                    else:
                        keyboard, i = await get_channel_btns()
                        await query.edit_message_text("Kanal topilmadi.", reply_markup=keyboard)
                except Exception as e:
                    await error_notificator.notify(context, e, update)
            else:
                keyboard, i = await get_channel_btns()
                await query.edit_message_text("❌ Kanalni o'chirish bekor qilindi.", reply_markup=keyboard)
