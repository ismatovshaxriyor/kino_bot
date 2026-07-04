# syntax=docker/dockerfile:1
#
# KinoBot image — ham bot (main.py), ham worker (worker.py) shu image'dan ishlaydi.
# Buyruq docker-compose.yml'da har bir xizmat uchun alohida beriladi.

FROM python:3.12-slim-bookworm

# Tizim paketlari:
#  - postgresql-client-15: admins/backup_handler.py "pg_dump" ni chaqiradi.
#    Versiya server (postgres:15-alpine) bilan AYNAN mos bo'lishi shart —
#    Debian bookworm'da `postgresql-client-15` aynan 15-versiya.
#  - tzdata: main.py JobQueue uchun ZoneInfo("Asia/Tashkent") ishlatadi
#    (zaxira nusxa 00:00/06:00/12:00/18:00 Toshkent vaqtida ketishi uchun).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client-15 \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tashkent

WORKDIR /app

# Avval faqat requirements — Docker layer cache uchun (kod o'zgarsa,
# kutubxonalar qayta o'rnatilmaydi).
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Standart buyruq — bot. "worker" xizmati buni docker-compose.yml'da
# `command: python worker.py` bilan override qiladi.
CMD ["python", "main.py"]
