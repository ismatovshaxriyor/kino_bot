from tortoise import Tortoise
from utils import DATABASE_URL

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
    print("✅ Database connected!")

async def post_init(application):
    await init_db()
