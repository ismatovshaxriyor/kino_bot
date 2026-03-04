from telegram import KeyboardButton, ReplyKeyboardMarkup


admin_btns = [
    [
        KeyboardButton("🎬 Kinolar"),
    ],
    [
        KeyboardButton("📢 Janrlar"),
        KeyboardButton("🌏 Davlatlar")
    ],
    [
        KeyboardButton("📢 Kanallar"),
        KeyboardButton("📊 Statistika")
    ],
    [
        KeyboardButton("📣 Xabar yuborish"),
        KeyboardButton("🔍 Tekshirish"),
    ],
    [
        KeyboardButton("🔙 Ortga")
    ]
]

admin_keyboard = ReplyKeyboardMarkup(
    admin_btns,
    resize_keyboard=True,
    one_time_keyboard=False
)


