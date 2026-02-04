from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils import admin_required
from database import User
from .managers_handler import get_managers_btns

@admin_required
async def general_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')

    if state is None:
        return

    if state == 'WAITING_GENRE_NAME':
        genre = update.message.text
        context.user_data['new_genre'] = genre.capitalize()
        context.user_data['state'] = "WAITING_FOR_CONFIRM_GENRE"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_genre_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_genre_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi janr: {genre.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_COUNTRY_NAME":
        country = update.message.text
        context.user_data['new_country'] = country.capitalize()
        context.user_data['state'] = "WAITING_FOR_CONFIRM_COUNTRY"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_country_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_country_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi davlat: {country.capitalize()}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_MANAGER_ID":
        keyboard, i = await get_managers_btns()

        try:
            manager_id = int(update.message.text)
            context.user_data['new_manager'] = manager_id
        except:
            await update.message.reply_text("Noto'g'ri formatdagi id\n\nId faqat raqamlardan iborat bo'lishi kerak", reply_markup=keyboard)
            return

        new_manager = await User.get_or_none(telegram_id=manager_id)

        if new_manager is None:
            await update.message.reply_text("Bu Id da foydalanuvchi topilmadi\n\nIltimos botdan ro'yxatdan o'tgan foydalanuvchining Id sini yuboring.", reply_markup=keyboard)
            return

        context.user_data['state'] = "WAITING_FOR_CONFIRM_MANAGER"

        confirm_btns = [
            [
                InlineKeyboardButton(text='Tasdiqlash', callback_data='confirm_manager_add'),
                InlineKeyboardButton(text='Bekor qilish', callback_data='reject_manager_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(f"Yangi Manager: {new_manager.first_name} {new_manager.last_name if new_manager.last_name else None}. Tasdiqlaysizmi?", reply_markup=confirm_keyboard)

    elif state == "WAITING_CHANNEL_USERNAME":
        from utils.checker import is_bot_admin, get_channel_info
        from admins import get_channel_btns

        channel_input = update.message.text.strip()

        # Kanal ma'lumotlarini olish
        channel_info = await get_channel_info(context.bot, channel_input)

        if not channel_info:
            await update.message.reply_text(
                "❌ Kanal topilmadi!\n\n"
                "Iltimos to'g'ri username yoki ID kiriting:\n"
                "• @kanal_nomi\n"
                "• kanal_nomi\n"
                "• -100xxxxxxxxxx (kanal ID)"
            )
            return

        # Bot admin ekanligini tekshirish
        is_admin = await is_bot_admin(context.bot, channel_info['id'])

        if not is_admin:
            await update.message.reply_text(
                f"❌ Bot \"{channel_info['title']}\" kanalida admin emas!\n\n"
                "Kanal qo'shish uchun:\n"
                "1. Botni kanalga qo'shing\n"
                "2. Botga admin huquqini bering\n"
                "3. Qayta urinib ko'ring"
            )
            return

        # Ma'lumotlarni saqlash
        context.user_data['channel_id'] = channel_info['id']
        context.user_data['channel_username'] = channel_info['username']
        context.user_data['channel_name'] = channel_info['title']
        context.user_data['state'] = "WAITING_FOR_CONFIRM_CHANNEL"

        confirm_btns = [
            [
                InlineKeyboardButton(text='✅ Tasdiqlash', callback_data='confirm_channel_add'),
                InlineKeyboardButton(text='❌ Bekor qilish', callback_data='reject_channel_add')
            ]
        ]

        confirm_keyboard = InlineKeyboardMarkup(confirm_btns)

        await update.message.reply_text(
            f"✅ Bot kanalda admin!\n\n"
            f"📢 Kanal: {channel_info['title']}\n"
            f"🆔 ID: {channel_info['id']}\n"
            f"👤 Username: {'@' + channel_info['username'] if channel_info['username'] else 'mavjud emas'}\n\n"
            "Tasdiqlaysizmi?",
            reply_markup=confirm_keyboard
        )

    else:
        pass