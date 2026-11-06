"""Telegram Mini App `initData` imzosini tekshirish.

initData ni faqat Telegram o'zi BOT_TOKEN asosida imzolay oladi, shuning uchun to'g'ri imzo foydalanuvchi
aynan shu bot orqali ilovani ochganini isbotlaydi. Panelga faqat ruxsat etilgan ID lar kiradi.
Hujjat: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE = 6 * 3600       # initData shu muddatdan eski bo'lsa qabul qilinmaydi (ilovani qayta oching)
MAX_LEN = 4096


def _sign(pairs: dict, secret: bytes) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def validate_init_data(init_data: str, bot_token: str, *, max_age: int = MAX_AGE, now: float | None = None) -> dict | None:
    """Imzo, yangilik va tuzilish to'g'ri bo'lsa foydalanuvchi (dict), aks holda None."""
    if not init_data or not isinstance(init_data, str) or len(init_data) > MAX_LEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None

    received = pairs.pop("hash", None)
    if not received:
        return None

    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    # Telegram `signature` maydonini qo'shgan; imzo unsiz ham, u bilan ham hisoblanishi mumkin — ikkalasini qabul qilamiz
    candidates = [pairs]
    if "signature" in pairs:
        candidates.append({k: v for k, v in pairs.items() if k != "signature"})
    if not any(hmac.compare_digest(_sign(c, secret), received) for c in candidates):
        return None

    try:
        age = (now if now is not None else time.time()) - int(pairs["auth_date"])
        user = json.loads(pairs["user"])
    except (KeyError, ValueError):
        return None
    if age > max_age or age < -60:
        return None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    return user
