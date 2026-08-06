from telegram import KeyboardButton, ReplyKeyboardMarkup


user_btns = [
    [
        KeyboardButton("🎭 Janr bo'yicha"),
        KeyboardButton("📅 Yil bo'yicha"),
    ],
    [
        KeyboardButton("🏆 Top kinolar"),
        KeyboardButton("🤖 AI yordamchi")
    ],
    [
        KeyboardButton("🤝 Do'stlarni taklif qilish"),
    ],
]

user_keyboard = ReplyKeyboardMarkup(
    user_btns,
    resize_keyboard=True,
    one_time_keyboard=False
)

