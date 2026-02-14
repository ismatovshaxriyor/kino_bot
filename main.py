from admins import get_channels
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, MessageHandler, filters
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
    bot.add_handler(CommandHandler("kino", inline_movie_command_handler))
    bot.add_handler(CommandHandler("admin", admin_handler))
    bot.add_handler(CommandHandler("history", history_handler))
    bot.add_handler(CommandHandler("top", top_handler))
    bot.add_handler(InlineQueryHandler(inline_query_handler))

    bot.add_handler(add_movie_conf_handler)
    bot.add_handler(edit_movie_handler)

    # Admin handlers
    # Admin handlers - Only Private
    private_filter = filters.ChatType.PRIVATE

    bot.add_handler(MessageHandler(filters.Regex(r"📢 Janrlar") & private_filter, get_genres))
    bot.add_handler(MessageHandler(filters.Regex(r"🌏 Davlatlar") & private_filter, get_countries))
    bot.add_handler(MessageHandler(filters.Regex(r"👤 Managerlar") & private_filter, get_managers))
    bot.add_handler(MessageHandler(filters.Regex(r"🎬 Kinolar") & private_filter, get_movies))
    bot.add_handler(MessageHandler(filters.Regex(r"📢 Kanallar") & private_filter, get_channels))
    bot.add_handler(MessageHandler(filters.Regex(r"📊 Statistika") & private_filter, statistics_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"🔙 Ortga") & private_filter, admin_back_handler))

    # User handlers - Only Private
    bot.add_handler(MessageHandler(filters.Regex(r"🔍 Nomi bo'yicha") & private_filter, search_by_name_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"🎭 Janr bo'yicha") & private_filter, search_by_genre_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"📅 Yil bo'yicha") & private_filter, search_by_year_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"🏆 Top kinolar") & private_filter, top_handler))
    bot.add_handler(MessageHandler(filters.Regex(r"🤖 AI yordamchi") & private_filter, ai_assistant_handler))

    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & private_filter, message_handler))

    # Callbacks
    bot.add_handler(CallbackQueryHandler(movie_callback, pattern=r"^movie_"))
    bot.add_handler(CallbackQueryHandler(genre_callback, pattern=r"^genre_"))
    bot.add_handler(CallbackQueryHandler(country_callback, pattern=r"^country_"))
    bot.add_handler(CallbackQueryHandler(manager_callback, pattern=r"^manager_"))
    bot.add_handler(CallbackQueryHandler(channel_callback, pattern=r"^channel_"))
    bot.add_handler(CallbackQueryHandler(statistics_callback, pattern=r"^stats_"))
    bot.add_handler(CallbackQueryHandler(user_callback, pattern=r"^(ugenre_|uyear_|upage_|umovie_|uwatch_|user_back|noop|rate_movie_|set_rating_|cancel_rating_|uhistory_page_|utop_page_|utop_filter_)"))
    bot.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_subscription$"))
    bot.add_handler(CallbackQueryHandler(confirm_callback, pattern=r"^(confirm_|reject)"))

    bot.add_error_handler(error_handler)

    bot.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
