# KinoBot — AWS EC2 ga joylash (to'liq Docker)

Bu qo'llanma botni AWS EC2 (Ubuntu) instance'ida **to'liq Docker Compose** orqali
ishga tushirishni boshidan oxirigacha ko'rsatadi.

## Arxitektura (4 ta konteyner)

```
docker compose --profile app
├─ redis    (my_bot_redis)      — xabarlar navbati (bot_queue)
├─ db       (my_bot_postgres)   — Postgres 15 ma'lumotlar bazasi
├─ bot      (my_bot_app)        — python main.py  (Telegram polling, update handling)
└─ worker   (my_bot_worker)     — python worker.py (navbatdan xabar yuborish)
```

**Muhim:** `bot` xabarlarni to'g'ridan-to'g'ri yubormaydi — ularni Redis navbatiga
qo'yadi, `worker` esa navbatdan olib Telegram'ga yuboradi. **Worker ishlamasa,
hech qanday xabar yetkazilmaydi.** Shu sababli ikkalasi ham doim ishlab turishi kerak
(`restart: always` buni ta'minlaydi).

Bot **polling** rejimida ishlaydi → tashqaridan kiruvchi port kerak emas, faqat
chiquvchi internet (Telegram + Gemini) kerak.

---

## 1. EC2 instance yaratish

AWS Console → EC2 → **Launch instance**:

| Sozlama        | Tavsiya etilgan qiymat                                   |
|----------------|----------------------------------------------------------|
| AMI            | **Ubuntu Server 24.04 LTS** (yoki 22.04 LTS), x86_64     |
| Instance type  | **t3.small** (2 GB RAM) — `t3.micro` (1 GB) ham bo'ladi, lekin swap shart |
| Key pair       | Yangi yarating yoki mavjudini tanlang (`.pem` faylni saqlang) |
| Storage        | **20 GB gp3** (video metadata + DB + image'lar uchun yetarli) |

**Security Group (xavfsizlik guruhi):**

| Yo'nalish | Tur  | Port | Manba                          |
|-----------|------|------|--------------------------------|
| Inbound   | SSH  | 22   | **Faqat sizning IP** (`My IP`) |
| Outbound  | All  | All  | `0.0.0.0/0` (default)          |

> Botga kiruvchi port (HTTP/HTTPS) **kerak emas** — polling ishlatiladi.
> Postgres/Redis portlari ham tashqariga ochilmaydi (compose ularni faqat
> `127.0.0.1` ga bog'laydi).

---

## 2. Serverga ulanish

```bash
chmod 400 ~/Downloads/your-key.pem
ssh -i ~/Downloads/your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

---

## 3. Kerakli paketlarni o'rnatish

To'liq Docker yondashuvida **host'ga faqat 3 narsa** kerak: **Docker Engine**,
**Docker Compose plugin** va **git**. Qolgan hamma narsa (Python 3.12, barcha
`requirements.txt` kutubxonalari, `postgresql-client-15`, `tzdata`) konteyner image
ichida — `Dockerfile` avtomatik o'rnatadi, qo'lda hech narsa qilmaysiz.

```bash
# --- Yordamchi paketlar ---
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git

# --- Docker'ning rasmiy GPG kaliti ---
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# --- Docker apt repozitoriysi ---
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# --- Docker Engine + Compose plugin ---
sudo apt-get update
sudo apt-get install -y \
    docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

# --- "ubuntu" foydalanuvchisini docker guruhiga qo'shish (sudo'siz docker) ---
sudo usermod -aG docker $USER

# --- Docker'ni boot'da avtomatik yoqish ---
sudo systemctl enable --now docker
```

Guruh o'zgarishi kuchga kirishi uchun **sessiyadan chiqib qayta kiring** (`exit`
keyin yana `ssh ...`), yoki `newgrp docker`. Tekshirish:

```bash
docker --version
docker compose version
docker run --rm hello-world   # sudo'siz ishlasa — tayyor
```

> **Host paketlari ro'yxati (qisqacha):** `docker-ce`, `docker-ce-cli`,
> `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`, `git`
> (+ `ca-certificates`, `curl`, `gnupg`).
> *Ixtiyoriy:* `postgresql-client-15` — faqat host'dan to'g'ridan-to'g'ri `psql`
> ishlatmoqchi bo'lsangiz; backup/restore konteyner ichida ishlagani uchun
> shart emas.

---

## 4. Swap qo'shish (kichik instance uchun tavsiya)

`t3.micro` (1 GB) yoki `t3.small` (2 GB) da xotira yetishmay bot OOM bilan
o'lishi mumkin. 2 GB swap qo'shing:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # swap ko'rinishini tekshiring
```

---

## 5. Loyihani serverga olib kelish

**Variant A — git (tavsiya):**

```bash
cd ~
git clone <REPO_URL> kino_bot
cd kino_bot
```

**Variant B — lokal kompyuterdan scp (git remote bo'lmasa):**

```bash
# Lokal mashinangizda ishga tushiring (loyiha papkasidan):
rsync -avz --exclude '.venv' --exclude '.git' --exclude '__pycache__' \
  -e "ssh -i ~/Downloads/your-key.pem" \
  ./ ubuntu@<EC2_PUBLIC_IP>:~/kino_bot/
```

> **Eslatma:** `migrations/` papkasi `.gitignore`'da, shuning uchun yangi
> clone'da bo'lmaydi — bu normal. 7-bosqichda `aerich init-db` jadvallarni
> noldan yaratadi. (Tavsiya: kelajakda `migrations/` ni git'ga qo'shsangiz,
> productionda faqat `aerich upgrade` kifoya qiladi — pastdagi izohga qarang.)

---

## 6. `.env` faylni tayyorlash

```bash
cp .env.example .env
nano .env     # qiymatlarni to'ldiring, keyin Ctrl+O, Enter, Ctrl+X
```

To'ldirilishi shart:
- `BOT_TOKEN`, `ADMIN_ID`, `MANAGER_ID`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD` (**productionda kuchli parol!**), `DB_PORT`
- `GEMINI_API_KEY` (AI yordamchi kerak bo'lsa)

`DB_HOST` va `REDIS_URL` ni o'zgartirish shart emas — compose konteyner ichida
ularni `db` va `redis://redis` ga avtomatik o'rnatadi.

---

## 7. Birinchi marta ishga tushirish

```bash
cd ~/kino_bot

# 1) Image'ni yig'ish
docker compose --profile app build

# 2) Infratuzilmani ko'tarish (Postgres + Redis)
docker compose up -d redis db

# 3) Ma'lumotlar bazasi sxemasi — IKKI yo'ldan BIRINI tanlang:

#    (a) YANGI bo'sh baza — jadvallarni noldan yaratish:
docker compose run --rm bot aerich init-db

#    (b) MAVJUD backupdan tiklash (schema + data) — init-db O'RNIGA:
#        SQL backup (.sql.gz) — schema bilan birga keladi:
docker compose cp kino_backup_YYYYMMDD_HHMMSS.sql.gz bot:/tmp/backup.sql.gz
docker compose run --rm bot python scripts/restore_backup.py /tmp/backup.sql.gz
#        JSON backup uchun avval `aerich init-db`, keyin `... restore_backup.py file.json.gz --yes`

# 4) Bot + worker'ni ishga tushirish
docker compose --profile app up -d

# 5) Holatni tekshirish
docker compose --profile app ps
```

Yoki `Makefile` bilan qisqaroq:

```bash
make build
make up-infra
make init-db        # yoki backupdan tiklash
make up
make ps
```

---

## 8. Tekshirish

```bash
# Jonli loglar (Ctrl+C bilan chiqasiz — bot to'xtamaydi)
docker compose --profile app logs -f bot worker
```

Loglarda quyidagilarni ko'rishingiz kerak:
- `✅ Redis Patch ... muvaffaqiyatli qo'llanildi`
- `✅ Database connected!`
- `✅ pg_trgm qidiruv indeksi tayyor`
- `✅ Zaxira JobQueue rejalashtirildi (har 6 soat...)`
- worker: `🚀 Worker ishga tushdi (Full Mode)...`

Endi Telegram'da botga `/start` yuboring — javob kelsa, hammasi ishlayapti. ✅

---

## 9. Kundalik boshqaruv

| Vazifa                         | Buyruq                                              |
|--------------------------------|-----------------------------------------------------|
| Loglar (jonli)                 | `docker compose --profile app logs -f bot worker`   |
| Holat                          | `docker compose --profile app ps`                   |
| Qayta ishga tushirish          | `docker compose --profile app restart bot worker`   |
| To'xtatish                     | `docker compose --profile app stop`                 |
| Yana ishga tushirish           | `docker compose --profile app start`                |
| To'liq o'chirish (data saqlanadi) | `docker compose --profile app down`              |

> Yuqoridagilar `make logs`, `make ps`, `make restart`, `make stop`, `make start`,
> `make down` bilan ham bajariladi.

### Yangilanish (kod o'zgargach qayta deploy)

```bash
cd ~/kino_bot
git pull --ff-only
docker compose --profile app up -d --build     # yoki: make deploy
```

Agar **model (database)** o'zgargan bo'lsa, migratsiyani qo'llang:

```bash
docker compose run --rm bot aerich migrate --name "ozgarish_nomi"   # make migrate m=...
docker compose run --rm bot aerich upgrade                          # make upgrade
```

> `migrations/` `.gitignore`'da bo'lgani uchun migratsiyalar **serverda**
> generatsiya qilinadi va host'dagi `./migrations` papkasida (volume) saqlanadi.
> **Tavsiya:** `migrations/` ni git'ga qo'shing — shunda migratsiyalarni bir marta
> (dev'da) yaratib commit qilasiz, productionda esa faqat `aerich upgrade` ishlatasiz.

---

## 10. Zaxira nusxa (backup) va tiklash

### Avtomatik

- Bot **har 6 soatda** (00:00/06:00/12:00/18:00 Toshkent vaqti) `ADMIN_ID` ga
  Telegram orqali `.sql.gz` zaxira yuboradi (JobQueue).
- Admin panelda **💾 Zaxira nusxa** tugmasi — qo'lda zaxira (faqat admin/manager).

pg_dump `bot` konteyneri ichida (`postgresql-client-15`) `db` xizmatiga tarmoq
orqali ulanadi — to'liq SQL zaxira ishlaydi, qo'shimcha sozlash shart emas.

### Qo'lda host'ga backup

```bash
make backup
# -> backups/kino_YYYYMMDD_HHMMSS.sql.gz
```

yoki to'g'ridan-to'g'ri:

```bash
mkdir -p ~/backups
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip > ~/backups/kino_$(date +%F_%H%M).sql.gz
```

> Telegram orqali yuboriladigan zaxira 50 MB bilan cheklangan; oshsa, bot faylni
> server `/tmp` ga saqlab, yo'lini xabar qiladi.

### Tiklash

```bash
# SQL (.sql.gz) — eng oson, schema bilan keladi:
docker compose cp BACKUP.sql.gz bot:/tmp/restore.sql.gz
docker compose run --rm bot python scripts/restore_backup.py /tmp/restore.sql.gz

# JSON (.json.gz) — avval schema kerak (aerich init-db), keyin:
docker compose cp BACKUP.json.gz bot:/tmp/restore.json.gz
docker compose run --rm bot python scripts/restore_backup.py /tmp/restore.json.gz --yes
```

Batafsil: `docs/BACKUP_RESTORE.md`.

---

## 11. Reboot'dan keyin avtomatik ishga tushish

`restart: always` + `systemctl enable docker` tufayli server qayta yuklansa,
barcha konteynerlar (shu jumladan bot va worker) avtomatik ko'tariladi. Tekshirish:

```bash
sudo reboot
# qayta ulaning, so'ng:
docker compose --profile app ps     # hammasi "Up" bo'lishi kerak
```

---

## 12. Xavfsizlik eslatmalari

- **`.env` ni hech qachon git'ga qo'shmang** (allaqachon `.gitignore`'da).
- Productionda **kuchli `DB_PASSWORD`** ishlating.
- Security Group'da SSH (22) ni faqat o'z IP'ingizga oching.
- Agar `BOT_TOKEN` yoki `GEMINI_API_KEY` biror joyda oshkor bo'lgan bo'lsa,
  ularni yangilang: token uchun **@BotFather** → `/revoke`, Gemini uchun
  Google AI Studio'da yangi kalit.

---

## 13. Muammolarni bartaraf etish

| Belgi | Sabab / Yechim |
|-------|----------------|
| Bot javob bermayapti, lekin loglar toza | `worker` o'chgan bo'lishi mumkin. `docker compose --profile app ps` — worker "Up" emasmi? Worker'siz xabar yetkazilmaydi. `make logs` bilan tekshiring. |
| `Conflict: terminated by other getUpdates request` | Bot ikki joyda bir vaqtda polling qilyapti (masalan host'da ham `python main.py` ochiq). Faqat **bitta** instance qoldiring. |
| `permission denied ... docker daemon` | `sudo usermod -aG docker $USER` qildingizmi? Sessiyadan chiqib qayta kiring. |
| `pg_dump: server version mismatch` | Image'dagi client (15) va server (postgres:15) mos. Agar Postgres versiyasini o'zgartirsangiz, `Dockerfile`'dagi `postgresql-client-15` ni ham mos yangilang. |
| Bot vaqti-vaqti bilan o'ladi (OOM) | Swap qo'shing (4-bosqich) yoki kattaroq instance (`t3.small`+). `docker stats` bilan xotirani kuzating. |
| `aerich init-db` xato beradi: relation already exists | Baza bo'sh emas. Mavjud bazada `init-db` o'rniga `aerich upgrade` ishlating yoki backupdan tiklang. |
| Image build'da `postgresql-client-15` topilmadi | Base image o'zgargan bo'lishi mumkin. `Dockerfile`'da `postgresql-client-15` o'rniga `postgresql-client` (bookworm'da = 15) sinab ko'ring. |

### Foydali tekshiruv buyruqlari

```bash
docker compose --profile app ps          # konteynerlar holati
docker stats --no-stream                 # CPU / xotira
docker compose --profile app logs --tail=200 bot
docker compose exec db psql -U "$DB_USER" -d "$DB_NAME" -c '\dt'   # jadvallar
docker compose exec redis redis-cli LLEN bot_queue                 # navbat uzunligi
```
