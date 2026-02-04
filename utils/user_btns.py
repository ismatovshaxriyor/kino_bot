from telegram import KeyboardButton, ReplyKeyboardMarkup


user_btns = [
    [
        KeyboardButton("🔍 Nomi bo'yicha"),
        KeyboardButton("🎭 Janr bo'yicha"),
    ],
    [
        KeyboardButton("📅 Yil bo'yicha"),
        KeyboardButton("🤖 AI yordamchi")
    ],
]

user_keyboard = ReplyKeyboardMarkup(
    user_btns,
    resize_keyboard=True,
    one_time_keyboard=False
)



