# Bir serverda ikkinchi bot (boshqa token)

Ikkinchi bot **alohida papkada**, o'z `.env`, o'z Postgres va o'z Redis'i bilan ishlaydi. Katalog (kinolar) bazasi
birinchi botnikidan butunlay alohida: Telegram `file_id` lar faqat o'sha bot uchun ishlaydi, shuning uchun bazani
ulashib bo'lmaydi. Panel (`webapp`, `ngrok`, `dockerproxy`) faqat birinchi nusxada qoladi.

## 1. Papka va kod

```bash
cd /root && git clone <repo-url> kino_bot2 && cd kino_bot2
```

Compose loyiha nomi papka nomidan olinadi (`kino_bot2`), shuning uchun tarmoq va volume'lar birinchi botnikidan ajralgan.

## 2. `.env`

`.env.example` dan nusxa olib to'ldiring (`umask 077`, keyin `chmod 600 .env`) va **qo'shimcha** quyidagilarni yozing:

```env
BOT_TOKEN=<ikkinchi bot tokeni>
ADMIN_ID=<admin>
MANAGER_ID=<manager>
DB_NAME=kinobot
DB_USER=kinobot
DB_PASSWORD=<kuchli parol>

# --- bir serverda ikkinchi nusxa uchun ---
INSTANCE=kino2                  # konteyner nomlari: kino2_app, kino2_worker, kino2_postgres, kino2_redis
BOT_IMAGE=kino_bot2:latest      # birinchi botning image'ini qayta yozib yubormaslik uchun
DB_PORT=5434                    # host'dagi port (127.0.0.1) — band bo'lmasin: `ss -ltn`
REDIS_HOST_PORT=6380
SERVER_MONITOR=0                # ikkinchi nusxada server monitori kerak emas
START_IMAGE=assets/kino_bot2.jpg   # /start rasmi (default: IMG_7403.PNG)
INLINE_THUMB_URL=https://raw.githubusercontent.com/ismatovshaxriyor/kino_bot/main/assets/kino_bot2.jpg   # inline rasm
```

## 3. Ishga tushirish

`bot` va `worker` yetarli (db/redis o'zi ko'tariladi). Panel xizmatlari ikkinchi nusxada **kerak emas**:

```bash
docker compose --profile app up -d --build bot worker
docker compose run --rm bot aerich init-db     # YANGI bo'sh bazada, faqat 1-marta
```

Yoki: `make deploy SERVICES="bot worker"` (yangilashda). Birinchi `up` dan keyin `init-db` ni bajarib, `bot`/`worker` ni
`docker compose restart bot worker` bilan qayta ishga tushiring.

## Eslatmalar

- Bir xil tokenni ikki joyda ishga tushirmang — `Conflict` xatosi chiqadi.
- RAM: bir nusxa ~250–300 MB (bot + worker + Postgres + Redis).
- Backup: `make backup` shu papkadagi bazani oladi; 6 soatlik avtomatik zaxira shu botning `ADMIN_ID` siga boradi.
