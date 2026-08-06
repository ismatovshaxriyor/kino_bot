from telegram import KeyboardButton, ReplyKeyboardMarkup

from .settings import ADMIN_ID, MANAGER_ID


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

async def get_user_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Oddiy foydalanuvchi klaviaturasi — admin/manager bo'lsa "🔐 Admin panel" tugmasi bilan.

    DB'dan foydalanuvchi turini tekshiradi, shu sabab admin panel/qidiruvdan
    "ortga" qaytaradigan har bir joyda (get_admin_keyboard bilan bir xil
    pattern) shu funksiya ishlatilishi kerak.
    """
    from database import User

    is_admin = user_id in (ADMIN_ID, MANAGER_ID)
    if not is_admin:
        user = await User.get_or_none(telegram_id=user_id)
        is_admin = bool(user and user.user_type == "admin")

    keyboard_rows = [row[:] for row in user_btns]
    if is_admin:
        keyboard_rows.append([KeyboardButton("🔐 Admin panel")])

    return ReplyKeyboardMarkup(keyboard_rows, resize_keyboard=True, one_time_keyboard=False)

