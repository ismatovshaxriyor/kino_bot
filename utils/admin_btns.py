from telegram import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup


admin_btns = [
    [
        KeyboardButton("🎬 Kinolar"),
    ],
    [
        KeyboardButton("📢 Janrlar"),
        KeyboardButton("🌏 Davlatlar")
    ],
    [
        KeyboardButton("👤 Managerlar"),
        KeyboardButton("📢 Kanallar")
    ],
    [
        KeyboardButton("📊 Statistika"),
        KeyboardButton("🔙 Orqaga")
    ]
]

admin_keyboard = ReplyKeyboardMarkup(
    admin_btns,
    resize_keyboard=True,
    one_time_keyboard=False
)



