"""Telegram API uchun HTTP klient sozlamasi (bot va worker uchun umumiy).

httpx bo'sh ulanishni standart bo'yicha 5 soniyadan keyin yopadi. Server Telegramdan uzoq bo'lsa
(Sydney -> Amsterdam ~290 ms) har bir "sovuq" ulanish TCP+TLS tufayli ~0,87 s turadi, ulangan
holatda esa ~0,29 s. Shuning uchun ulanishni uzoqroq ushlab turamiz. Boshqa sozlamalar PTB standartida.
"""

import httpx
from telegram.request import HTTPXRequest

KEEPALIVE_EXPIRY = 120  # soniya
POOL_SIZE = 256         # PTB standarti bilan bir xil


def make_request() -> HTTPXRequest:
    limits = httpx.Limits(
        max_connections=POOL_SIZE,
        max_keepalive_connections=64,
        keepalive_expiry=KEEPALIVE_EXPIRY,
    )
    return HTTPXRequest(connection_pool_size=POOL_SIZE, httpx_kwargs={"limits": limits})
