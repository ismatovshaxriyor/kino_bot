from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from utils import MANAGER_ID, ADMIN_ID
from database import User

class PermissionDenied(Exception):
    pass

def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        user = await User.get_or_none(telegram_id=user_id)

        if not ((user and user.user_type == 'admin') or user_id in (ADMIN_ID, MANAGER_ID)):
            raise PermissionDenied()

        return await func(update, context, *args, **kwargs)
    return wrapper

