import logging

from tortoise import Tortoise
from utils import DATABASE_URL

from telegram import BotCommand

logger = logging.getLogger(__name__)

TORTOISE_ORM = {
    "connections": {
        "default": DATABASE_URL
    },
    "apps": {
        "models": {
            "models": ["database", "aerich.models"],
            "default_connection": "default",
        }
    }
}

async def init_db():
    await Tortoise.init(config=TORTOISE_ORM)
    logger.info("✅ Database connected!")


async def ensure_search_index():
    """movie_name bo'yicha ILIKE qidiruvini tezlashtirish uchun pg_trgm GIN index.

    Idempotent: indeks/extension mavjud bo'lsa hech narsa qilmaydi. Huquq
    yetishmasa (masalan, CREATE EXTENSION uchun) — faqat ogohlantiradi, ishni to'xtatmaydi.
    """
    conn = Tortoise.get_connection("default")
    try:
        await conn.execute_query("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        await conn.execute_query(
            'CREATE INDEX IF NOT EXISTS idx_movie_name_trgm '
            'ON "movie" USING gin (movie_name gin_trgm_ops);'
        )
        logger.info("✅ pg_trgm qidiruv indeksi tayyor")
    except Exception as e:
        logger.warning("⚠️ pg_trgm indeksini yaratib bo'lmadi (huquq yetishmasligi mumkin): %s", e)


async def post_init(application):
    await init_db()
    await ensure_search_index()

    # Bot komandalarini sozlash
    commands = [
        BotCommand("start", "🚀 Botni ishga tushirish"),
        BotCommand("history", "📜 Ko'rilganlar tarixi"),
        BotCommand("top", "🏆 Top reyting"),
    ]
    await application.bot.set_my_commands(commands)
