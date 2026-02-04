import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from services import MovieAIAssistant

# .env faylni yuklash
load_dotenv()

# ========================
# SOZLAMALAR (.env dan)
# ========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Tekshirish
if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    raise ValueError(
        "❌ XATOLIK: .env faylda TELEGRAM_BOT_TOKEN va GEMINI_API_KEY ni to'ldiring!\n"
        ".env.example faylga qarang."
    )

# AI Assistant ni yaratish
ai_assistant = MovieAIAssistant(api_key=GEMINI_API_KEY)

print("✅ AI Assistant tayyor!")


# ========================
# COMMAND HANDLERS
# ========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start komandasi - Botni boshlash
    """
    user_name = update.effective_user.first_name
    welcome_message = f"""
👋 Salom {user_name}!

🎬 **Kino AI Assistant**ga xush kelibsiz!

Men sizga quyidagi yordam bera olaman:

🎯 Kino/Serial tavsiya qilish
🎯 Janr bo'yicha kinolar topish
🎯 Kino haqida to'liq ma'lumot
🎯 O'xshash kinolar taklif qilish

📝 **Qanday foydalanish:**
Shunchaki menga yozing yoki komandalardan foydalaning:

/movie Inception - Kino haqida ma'lumot
/genre comedy - Janr bo'yicha kinolar
/help - To'liq yordam

Yoki oddiy yozing:
"Qo'rqinchli kino tavsiya qil"
"2024 yilgi eng yaxshi filmlar"

Boshlaylik! 🍿
"""
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /help komandasi - Yordam
    """
    help_text = """
📚 **YORDAM - Kino AI Assistant**

🎬 **Komandalar:**

/start - Botni qayta boshlash
/help - Bu yordam xabari
/movie [kino_nomi] - Kino haqida ma'lumot
/genre [janr] - Janr bo'yicha tavsiyalar

📝 **Misol komandalar:**
/movie Interstellar
/movie The Godfather
/genre action
/genre comedy

💬 **Oddiy savol berish:**
Shunchaki yozing:

"Qo'rqinchli kino tavsiya qil"
"Leonardo DiCaprio kinolari"
"Marvel filmlari ro'yxati"
"2024 yilgi eng yaxshi filmlar"
"Romantik komediya kerak"

🌍 **Tillar:**
Men o'zbek, rus va ingliz tillarida ishlayman!

❓ **Savollaringiz bormi?**
Shunchaki savol bering, men javob beraman! 🎭
"""
    await update.message.reply_text(help_text)


async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /movie [kino_nomi] - Ma'lum bir kino haqida ma'lumot
    """
    if not context.args:
        await update.message.reply_text(
            "❌ Kino nomini kiriting!\n\n"
            "**Misol:**\n"
            "/movie Inception\n"
            "/movie The Shawshank Redemption\n"
            "/movie Oppenheimer"
        )
        return

    movie_name = " ".join(context.args)

    # "Kutilmoqda" xabari
    waiting_msg = await update.message.reply_text(
        f"🔍 '{movie_name}' haqida ma'lumot qidiryapman...\n"
        "Iltimos kuting ⏳"
    )

    try:
        # AI dan javob olish
        response = ai_assistant.search_movie_info(movie_name)

        # Javobni yuborish
        await waiting_msg.edit_text(response)

    except Exception as e:
        await waiting_msg.edit_text(
            f"❌ Xatolik yuz berdi: {str(e)}\n"
            "Iltimos qaytadan urinib ko'ring."
        )


async def genre_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /genre [janr] - Janr bo'yicha tavsiyalar
    """
    if not context.args:
        await update.message.reply_text(
            "❌ Janr nomini kiriting!\n\n"
            "**Misol:**\n"
            "/genre action\n"
            "/genre comedy\n"
            "/genre sci-fi\n\n"
            "**Mavjud janrlar:**\n"
            "action, comedy, drama, horror, sci-fi, romance, "
            "thriller, anime, documentary, fantasy, adventure"
        )
        return

    genre = " ".join(context.args)

    # "Kutilmoqda" xabari
    waiting_msg = await update.message.reply_text(
        f"🎬 '{genre}' janridagi eng yaxshi kinolarni qidiryapman...\n"
        "Biroz kuting ⏳"
    )

    try:
        # AI dan javob olish
        response = ai_assistant.get_recommendations_by_genre(genre, count=5)

        # Javobni yuborish
        await waiting_msg.edit_text(response)

    except Exception as e:
        await waiting_msg.edit_text(
            f"❌ Xatolik yuz berdi: {str(e)}\n"
            "Iltimos qaytadan urinib ko'ring."
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Oddiy xabarlarni qayta ishlash - AI bilan suhbat
    """
    user_message = update.message.text

    # "Yozmoqda..." animatsiyasini ko'rsatish
    await update.message.chat.send_action(action="typing")

    try:
        # AI dan javob olish
        response = ai_assistant.get_movie_recommendation(user_message)

        # Javobni yuborish
        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(
            f"❌ Javob berishda xatolik yuz berdi: {str(e)}\n\n"
            "Iltimos qaytadan yozing yoki /help ni ko'ring."
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xatolarni qayta ishlash
    """
    print(f"❌ Update {update} xatolikka sabab bo'ldi: {context.error}")


# ========================
# BOTNI ISHGA TUSHIRISH
# ========================

def main():
    """
    Botni ishga tushirish asosiy funksiya
    """
    print("=" * 50)
    print("🎬 KINO AI ASSISTANT BOT")
    print("=" * 50)
    print("📡 Bot ishga tushmoqda...")

    # Application yaratish
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlerlarni qo'shish
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("movie", movie_command))
    app.add_handler(CommandHandler("genre", genre_command))

    # Oddiy xabarlar uchun handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Xatolar uchun handler
    app.add_error_handler(error_handler)

    # Botni ishga tushirish
    print("✅ Bot muvaffaqiyatli ishga tushdi!")
    print("📱 Telegram da botingizni toping va foydalanishni boshlang!")
    print("🛑 Botni to'xtatish uchun Ctrl+C ni bosing")
    print("=" * 50)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Bot to'xtatildi.")
    except Exception as e:
        print(f"\n\n❌ XATOLIK: {e}")