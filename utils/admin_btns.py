from telegram import KeyboardButton, ReplyKeyboardMarkup

from .settings import ADMIN_ID, MANAGER_ID


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

def get_admin_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """ADMIN_ID/MANAGER_ID uchun "Managerlar"/"Zaxira nusxa" qatorini ham qo'shib beradi.

    admin_btns ustidan doimiy ReplyKeyboardMarkup emas, shu funksiya orqali klaviatura
    olish kerak — admin panelga qaytaradigan har bir handlerda (nafaqat admin_handler).
    """
    keyboard_rows = [row[:] for row in admin_btns]
    if user_id in (ADMIN_ID, MANAGER_ID):
        keyboard_rows.insert(3, [KeyboardButton("👤 Managerlar"), KeyboardButton("💾 Zaxira nusxa")])

    return ReplyKeyboardMarkup(keyboard_rows, resize_keyboard=True, one_time_keyboard=False)


