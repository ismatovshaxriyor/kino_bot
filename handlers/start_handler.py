from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from database import User
from utils import error_notificator, user_keyboard
from utils.decorators import channel_subscription_required



@channel_subscription_required
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.effective_chat.first_name
    last_name = update.effective_chat.last_name
    username = update.effective_chat.username
    telegram_id = update.effective_chat.id

    # State ni tozalash
    context.user_data['state'] = None

    try:
        user, created = await User.get_or_create(telegram_id=telegram_id, defaults={
            'first_name': first_name,
            'last_name': last_name if last_name else None,
            'username': username if username else None
        })

        if created:
            welcome_msg = (
                f"🎬 <b>Kino Botga xush kelibsiz!</b>\n\n"
                f"👋 Salom, <b>{first_name}</b>!\n\n"
                "📺 Bu bot orqali siz:\n"
                "• Kinolarni qidirish\n"
                "• Janr bo'yicha tanlash\n"
                "• AI yordamidan foydalanish mumkin\n\n"
                "🎯 <b>Kino kodini yuboring</b> yoki quyidagi tugmalardan foydalaning:"
            )
            await update.message.reply_text(welcome_msg, reply_markup=user_keyboard, parse_mode="HTML")
        else:
            welcome_back_msg = (
                f"🎬 <b>Qaytganingizdan xursandmiz!</b>\n\n"
                f"👋 Salom, <b>{first_name}</b>!\n\n"
                "🎯 <b>Kino kodini yuboring</b> yoki quyidagi tugmalardan foydalaning:"
            )
            await update.message.reply_text(welcome_back_msg, reply_markup=user_keyboard, parse_mode="HTML")

    except Exception as e:
        await error_notificator.notify(context, e, update)




