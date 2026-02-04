from admins import get_channels
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update

from handlers import *
from callbacks import *
from admins import *
from database import post_init
from utils import BOT_TOKEN, apply_redis_patch


apply_redis_patch()

def main():
    bot = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    bot.add_handler(CommandHandler('start', start_handler))
    bot.add_handler(CommandHandler("admin", admin_handler))

    bot.add_handler(add_movie_conf_handler)

    # Admin handlers
    bot.add_handler(MessageHandler(filters.Regex(r"📢 Janrlar"), get_genres))
    bot.add_handler(MessageHandler(filters.Regex(r"🌏 Davlatlar"), get_countries))
    bot.add_handler(MessageHandler(filters.Regex(r"👤 Managerlar"), get_managers))
    bot.add_handler(MessageHandler(filters.Regex(r"🎬 Kinolar"), get_movies))
    bot.add_handler(MessageHandler(filters.Regex(r"📢 Kanallar"), get_channels))

    # User handlers
    bot.add_handler(MessageHandler(filters.Regex(r"🔍 Nomi bo'yicha"), search_by_name_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"🎭 Janr bo'yicha"), search_by_genre_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"📅 Yil bo'yicha"), search_by_year_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"🤖 AI yordamchi"), ai_assistant_handler))

    bot.add_handler(MessageHandler(filters.TEXT, message_handler))
    bot.add_handler(MessageHandler(filters.TEXT, general_message_handler))

    # Callbacks
    bot.add_handler(CallbackQueryHandler(movie_callback, pattern=r"^movie_"))
    bot.add_handler(CallbackQueryHandler(genre_callback, pattern=r"^genre_"))
    bot.add_handler(CallbackQueryHandler(country_callback, pattern=r"^country_"))
    bot.add_handler(CallbackQueryHandler(manager_callback, pattern=r"^manager_"))
    bot.add_handler(CallbackQueryHandler(channel_callback, pattern=r"^channel_"))
    bot.add_handler(CallbackQueryHandler(user_callback, pattern=r"^(ugenre_|uyear_|upage_|umovie_|user_back|noop)"))
    bot.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_subscription$"))
    bot.add_handler(CallbackQueryHandler(confirm_callback, pattern=r"^(confirm_|reject)"))

    bot.add_error_handler(error_handler)

    bot.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()