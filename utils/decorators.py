from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from utils import MANAGER_ID
from database import User


def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes, *args, **kwargs):
        if update:
            user_id = update.effective_user.id
            user = await User.get(telegram_id=user_id)
            if (user and user.user_type == 'admin') or user_id == MANAGER_ID:
                return await func(update, context, *args, **kwargs)
        return None
    return wrapper
