"""Yakuniy to'xtatish qulfi (services/shutdown_mode.py).

Qulf fayli bor ekan, bot va worker ishga tushmaydi — konteyner qayta ishga tushsa ham
(`restart: always`, server reboot) Telegram'ga ulanmaydi. Shu bilan eski serverdagi bot
yangi serverdagi bot bilan bir token ustida to'qnashmaydi.

Qayta yoqish:  rm state/shutdown.lock && docker compose --profile app restart bot worker
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# docker-compose.yml da ./state papkasi /state ga ulangan
LOCK_PATH = Path(os.environ.get("SHUTDOWN_LOCK_PATH", "/state/shutdown.lock"))


def lock_exists() -> bool:
    return LOCK_PATH.exists()


def engage_lock(reason: str) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOCK_PATH.with_suffix(".tmp")
    tmp.write_text(f"{reason}\n")
    tmp.replace(LOCK_PATH)  # atomik: yarim yozilgan qulf bo'lmaydi


def hold_if_shutdown(name: str) -> None:
    """Qulf bor bo'lsa jarayonni ishga tushirmasdan kutib turish (CPU sarflamaydi)."""
    if not lock_exists():
        return
    logger.warning("🛑 %s ishga tushmadi: %s mavjud (yakuniy to'xtatish rejimi). Qayta yoqish: qulf faylini o'chirib, restart qiling.", name, LOCK_PATH)
    while True:
        time.sleep(3600)
