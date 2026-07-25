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
    """movie_name bo'yicha moslashuvchan (fuzzy) qidiruv uchun pg_trgm GIN index.

    `uz_normalize()` SQL funksiyasini yaratadi — u apostrof variantlarini
    (', ', ', ʻ, ʼ, `, ´, ʹ, ʺ) va registrni bir xillashtiradi, shuning uchun
    "po'lat", "po'lat" va "polat" endi bir xil so'z sifatida topiladi
    (foydalanuvchilar bu belgini turlicha yozgani sabab qidiruv ishlamay
    qolgan holatlarni tuzatadi — utils/search.py shu funksiyadan foydalanadi).

    Idempotent: indeks/extension/funksiya mavjud bo'lsa qayta yaratiladi
    yoki hech narsa qilinmaydi. Huquq yetishmasa (masalan, CREATE EXTENSION
    uchun) — faqat ogohlantiradi, ishni to'xtatmaydi.
    """
    conn = Tortoise.get_connection("default")

    # Uzbek apostrof/tirnoqcha variantlari: ' ' ' ʻ ʼ ` ´ ʹ ʺ
    apostrophe_chars = "'‘’ʻʼ`´ʹʺ"
    char_class = "[" + apostrophe_chars.replace("'", "''") + "]"

    try:
        await conn.execute_query("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

        await conn.execute_query(
            f"""
            CREATE OR REPLACE FUNCTION uz_normalize(input text) RETURNS text
            LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
                SELECT regexp_replace(lower(trim(input)), '{char_class}', '', 'g');
            $$;
            """
        )

        # Eski, normalize qilinmagan indeks endi ishlatilmaydi.
        await conn.execute_query('DROP INDEX IF EXISTS idx_movie_name_trgm;')
        await conn.execute_query(
            'CREATE INDEX IF NOT EXISTS idx_movie_name_normalized_trgm '
            'ON "movie" USING gin (uz_normalize(movie_name) gin_trgm_ops);'
        )
        logger.info("✅ pg_trgm qidiruv indeksi (normalize bilan) tayyor")
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
