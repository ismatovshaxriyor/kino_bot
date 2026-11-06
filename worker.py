import asyncio
from utils.settings import BOT_TOKEN
from utils import run_worker
from utils.shutdown_guard import hold_if_shutdown

if __name__ == "__main__":
    hold_if_shutdown("worker")
    asyncio.run(run_worker(BOT_TOKEN))
