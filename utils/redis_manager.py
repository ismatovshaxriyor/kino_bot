import json
import asyncio
import redis.asyncio as redis
from telegram import Message, Bot

REDIS_URL = "redis://localhost"
QUEUE_NAME = "bot_queue"

r = redis.from_url(REDIS_URL, decode_responses=True)

async def _push_to_redis(chat_id, method, content, **kwargs):
    if "reply_markup" in kwargs:
        markup = kwargs["reply_markup"]
        if hasattr(markup, "to_dict"):
            kwargs["reply_markup"] = markup.to_dict()

    payload = {
        "chat_id": chat_id,
        "method": method,
        "content": content,
        "args": kwargs
    }

    await r.rpush(QUEUE_NAME, json.dumps(payload))


async def patched_reply_text(self, text, **kwargs):
    await _push_to_redis(self.chat_id, "send_message", text, **kwargs)

async def patched_reply_video(self, video, **kwargs):
    await _push_to_redis(self.chat_id, "send_video", video, **kwargs)


def apply_redis_patch():
    Message.reply_text = patched_reply_text
    Message.reply_video = patched_reply_video
    print("✅ Redis Patch muvaffaqiyatli qo'llanildi")


async def run_worker(bot_token: str):
    bot = Bot(token=bot_token)
    print("🚀 Worker ishga tushdi, navbat kuzatilmoqda...")

    while True:
        try:
            data = await r.blpop(QUEUE_NAME, timeout=1)

            if data:
                msg = json.loads(data[1])

                method = msg['method']
                chat_id = msg['chat_id']
                content = msg['content']
                args = msg['args']

                if method == "send_message":
                    print(f"message send: {chat_id}")
                    await bot.send_message(chat_id=chat_id, text=content, **args)

                elif method == "send_video":
                    await bot.send_video(chat_id=chat_id, video=content, **args)

        except Exception as e:
            print(f"❌ Worker Xatoligi: {e}")
            await asyncio.sleep(0.1)