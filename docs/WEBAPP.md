# Admin paneli (Telegram Mini App)

Serverning to'liq holati real vaqtda grafiklarda: CPU (steal/iowait), RAM/swap, load, tarmoq, disk I/O, disk to'lganligi,
har bir konteyner CPU/xotirasi, Redis navbati/xotirasi, Postgres ulanishlari/TPS, bot statistikasi va AWS kredit.
Tarix: oxirgi 10 daqiqa (2 soniyalik qadam) va 24 soat (1 daqiqalik o'rtacha). Faqat `ADMIN_ID` va `MANAGER_ID` ochadi.

## Qanday ishlaydi

| Konteyner | Vazifasi |
|---|---|
| `my_bot_webapp` | `python -m webapp` — aiohttp + WebSocket, `127.0.0.1:8787`; metrikalar `/proc`, Docker, Postgres, Redis dan |
| `my_bot_ngrok` | `127.0.0.1:8787` ni internetga HTTPS bilan chiqaradi |
| `my_bot_dockerproxy` | Docker API'ga **faqat o'qish** (`GET /containers/*`); `docker.sock` to'g'ridan-to'g'ri panelga berilmaydi |

ngrok havolasi o'zgarganda `webapp/ngrok_link.py` (har 15 s) yangi havolani avtomatik:
1. adminlarning chat menyusidagi «📊 Server» tugmasiga o'rnatadi (`set_chat_menu_button`),
2. Redis'ga (`webapp:url`) yozadi — `/panel` buyrug'i shuni ishlatadi,
3. ADMIN_ID ga tugma bilan xabar yuboradi (bir xil havola uchun qayta yubormaydi).

## Ishga tushirish

```bash
bash scripts/set_ngrok_token.sh   # token so'raladi, serverga xavfsiz yoziladi va panel ishga tushadi
```

Token: https://dashboard.ngrok.com/get-started/your-authtoken. Deploy'dan keyin (`make deploy`) servislar o'zi ko'tariladi.
Botda `/panel` yoki chat menyusidagi «📊 Server» ni oching.

## Xavfsizlik

- Ma'lumot faqat WebSocket orqali va faqat Telegram `initData` imzosi (BOT_TOKEN bilan HMAC) to'g'ri, 6 soatdan eski bo'lmagan
  va foydalanuvchi `ADMIN_ID`/`MANAGER_ID` bo'lgandagina yuboriladi. Havolani bilgan begona faqat bo'sh sahifa ko'radi.
- IP bo'yicha 10 daqiqada 10 ta muvaffaqiyatsiz urinishdan keyin blok; bir vaqtda ko'pi bilan 5 ta ulanish.
- Panel `127.0.0.1` da tinglaydi; Docker API proxy ham `127.0.0.1:2375` da va faqat o'qiydi.

## Cheklovlar

- ngrok bepul tarifida brauzer birinchi ochilganda «Visit Site» sahifasini ko'rsatadi — bir marta bosing.
- Havola ngrok qayta ishga tushganda o'zgaradi (avtomatik yangilanadi). O'zgarmas bo'lishi uchun ngrok dashboard'dan
  bepul domen oling: `NGROK_EXTRA=--url=nomi.ngrok-free.app` (skript so'raydi).
- 24 soatlik tarix xotirada: panel qayta ishga tushsa tarix tozalanadi.
- Faqat ADMIN_ID ga cheklash uchun `webapp/server.py` dagi `ALLOWED_IDS` ni o'zgartiring.

## Muammolar

```bash
make logs                                   # barcha loglar
sudo docker logs my_bot_ngrok --tail 30      # token noto'g'ri bo'lsa shu yerda ko'rinadi
sudo docker logs my_bot_webapp --tail 30
```
