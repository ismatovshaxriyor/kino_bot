import os
from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Muhim sozlama (.env) topilmaganda yoki noto'g'ri bo'lganda chiqariladi."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise ConfigError(
            f"Majburiy muhit o'zgaruvchisi topilmadi: {name}. "
            f".env faylga {name}=... qatorini qo'shing."
        )
    return value


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} butun son bo'lishi kerak, lekin qiymat: {raw!r}")


# Sahifalash
PAGE_SIZE = 40            # admin kino ro'yxati
MOVIES_PER_PAGE = 15      # user / inline ro'yxatlar

# Telegram
BOT_TOKEN = _require("BOT_TOKEN")
ADMIN_ID = _require_int("ADMIN_ID")
MANAGER_ID = _require_int("MANAGER_ID")
INLINE_THUMB_URL = os.environ.get("INLINE_THUMB_URL", "https://i.postimg.cc/FsnbDKnM/IMG-0989.png")

# Gemini AI
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Redis (worker navbati)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost")

# Ma'lumotlar bazasi
DB_NAME = _require("DB_NAME")
DB_USER = _require("DB_USER")
DB_PASSWORD = _require("DB_PASSWORD")
DB_HOST = _require("DB_HOST")
DB_PORT = _require("DB_PORT")

# Zaxira nusxa (backup) sozlamalari
# pg_dump topilmasa SQL o'rniga JSON olinadi. Quyidagilar SQL backupni
# kafolatlash uchun: aniq pg_dump yo'li yoki docker konteyner nomi.
PG_DUMP_PATH = os.environ.get("PG_DUMP_PATH")  # masalan: /usr/bin/pg_dump
DB_DOCKER_CONTAINER = os.environ.get("DB_DOCKER_CONTAINER")  # masalan: my_bot_postgres


DATABASE_URL = f"psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
