"""Testlar uchun umumiy sozlama: settings.py import paytida majburiy env'larni tekshiradi."""
import os
import sys
from pathlib import Path

for key, value in {
    "BOT_TOKEN": "123:TEST", "ADMIN_ID": "111", "MANAGER_ID": "222",
    "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x", "DB_HOST": "x", "DB_PORT": "5432",
    "GEMINI_API_KEY": "test-key",
}.items():
    os.environ.setdefault(key, value)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
