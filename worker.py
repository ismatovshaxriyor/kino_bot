import asyncio
from utils.settings import BOT_TOKEN
from utils import run_worker

if __name__ == "__main__":
    asyncio.run(run_worker(BOT_TOKEN))