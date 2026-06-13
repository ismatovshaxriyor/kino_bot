# 💾 Ma'lumotlar bazasini zaxiralash va tiklash (Backup & Restore)

Bu hujjat kino-botning PostgreSQL bazasini zaxiralash va tiklash bo'yicha to'liq qo'llanma.

---

## 1. Backup qanday ishlaydi

Backup `admins/backup_handler.py` modulida amalga oshiriladi. `create_backup()` quyidagi
tartibda harakat qiladi va **birinchi muvaffaqiyatli** usulni ishlatadi:

| # | Usul | Natija | Tiklash qulayligi |
|---|------|--------|-------------------|
| 1 | Host'dagi `pg_dump` | `*.sql.gz` | ✅ bitta buyruq |
| 2 | Docker konteyner ichidagi `pg_dump` (`DB_DOCKER_CONTAINER` o'rnatilgan bo'lsa) | `*.sql.gz` | ✅ bitta buyruq |
| 3 | JSON (zaxira usul, `pg_dump` topilmasa) | `*.json.gz` | ⚠️ skript + schema kerak |

> **Muhim:** Imkon qadar **SQL formatni** ishlating. JSON faqat *ma'lumotni* saqlaydi,
> jadval tuzilmasini (schema) emas — shuning uchun tiklash ko'proq qadam talab qiladi.

Fayl nomi: `kino_backup_YYYYMMDD_HHMMSS.sql.gz` yoki `.json.gz`
(gzip bilan siqilgan, vaqtinchalik papkada yaratiladi va yuborilgach o'chiriladi).

### Backup qayerga boradi?

- **"💾 Zaxira nusxa" tugmasi** (admin paneldagi) — faqat bosh admin va manager
  (`ADMIN_ID`, `MANAGER_ID`) ko'radi va bosa oladi. Backup **ikkalasiga** yuboriladi.
- **Avtomatik backup** — **har 6 soatda** (00:00, 06:00, 12:00, 18:00 — Asia/Tashkent)
  JobQueue orqali faqat **bosh adminga** (`ADMIN_ID`) yuboriladi.

Fayl Telegramga **hujjat** (`send_document`) sifatida to'g'ridan-to'g'ri yuboriladi
(Redis navbatiga tushmaydi, ya'ni worker'ga bog'liq emas).

> Telegram bot hujjati uchun chegara — **50 MB**. Bazada faqat metama'lumot saqlanadi
> (videolar `file_id` ko'rinishida, fayl emas), shuning uchun backup hajmi juda kichik.
> Agar 50 MB dan oshsa — fayl serverda saqlanib qoladi va admin ogohlantiriladi.

---

## 2. SQL backup'ni yoqish (TAVSIYA ETILADI)

Agar backup **JSON** kelayotgan bo'lsa, demak bot ishlayotgan host'da `pg_dump` yo'q.
SQL formatni yoqishning ikki yo'li bor:

### A variant — Docker orqali (eng oson)

Postgres `my_bot_postgres` konteynerida ishlagani uchun, `.env` ga shuni qo'shing:

```env
DB_DOCKER_CONTAINER=my_bot_postgres
```

Botni qayta ishga tushiring. Endi backup konteyner ichidagi `pg_dump` orqali olinadi —
versiya serverga aynan mos keladi.

> Shart: bot ishlayotgan host'da `docker` buyrug'i mavjud va unga kirish huquqi bo'lishi kerak.

### B variant — host'ga pg_dump o'rnatish

```bash
# Debian/Ubuntu
sudo apt update && sudo apt install -y postgresql-client

# yoki aniq versiya (server postgres:15 bo'lsa)
sudo apt install -y postgresql-client-15
```

Agar `pg_dump` nostandart joyda bo'lsa, `.env` ga to'liq yo'lni ko'rsating:

```env
PG_DUMP_PATH=/usr/bin/pg_dump
```

> `pg_dump` versiyasi server versiyasidan **teng yoki yangi** bo'lishi kerak
> (yangi `pg_dump` eski serverni muammosiz zaxiralaydi).

---

## 3. SQL backup'ni tiklash

SQL fayl o'z ichida ham tuzilma (schema), ham ma'lumotni saqlaydi —
**bo'sh bazaga** bitta buyruq bilan tiklanadi.

### Restore skripti bilan (eng oson)

```bash
python scripts/restore_backup.py kino_backup_YYYYMMDD_HHMMSS.sql.gz
```

Skript `psql` ni avtomatik topadi (host yoki `DB_DOCKER_CONTAINER` orqali) va
DB ulanish ma'lumotlarini `.env` dan oladi.

### Qo'lda

```bash
# host'da psql bo'lsa
gunzip -c kino_backup_YYYYMMDD_HHMMSS.sql.gz | \
  psql -h <DB_HOST> -p <DB_PORT> -U <DB_USER> -d <DB_NAME>

# docker orqali
gunzip -c kino_backup_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i my_bot_postgres psql -U <DB_USER> -d <DB_NAME>
```

> Tiklashdan oldin baza **bo'sh** bo'lishi yaxshi. Mavjud bazaga tiklasangiz,
> jadvallar allaqachon bor degan xatolar chiqishi mumkin.

---

## 4. JSON backup'ni tiklash

JSON faqat ma'lumotni saqlaydi — shuning uchun **avval jadval tuzilmasi yaratilishi** kerak.

```bash
# 1) Bo'sh bazada jadvallarni yarating (migratsiyalarni qo'llang)
aerich upgrade

# 2) Ma'lumotni tiklang (--yes mavjud ma'lumotlarni TRUNCATE qiladi!)
python scripts/restore_backup.py kino_backup_YYYYMMDD_HHMMSS.json.gz --yes
```

Skript nima qiladi:
1. Barcha jadval qatorlarini o'qiydi (`_meta` dan tashqari).
2. FK/triggerlarni vaqtincha o'chiradi (`SET session_replication_role = replica`).
3. Jadvallarni `TRUNCATE ... RESTART IDENTITY CASCADE` qiladi.
4. Har bir jadvalga qatorlarni `INSERT` qiladi (JSONB qiymatlar to'g'ri o'raladi).
5. Auto-increment ketma-ketliklarni (sequence) eng katta `id` ga tiklaydi
   (`setval(GREATEST(MAX, 1))` — `channel_id` kabi manfiy qiymatlar uchun himoyalangan).

> `--yes` bermasangiz, skript faqat backup haqida ma'lumot ko'rsatadi va **hech narsa o'zgartirmaydi**
> (xavfsizlik uchun).

---

## 5. Restore skripti — qisqacha

`scripts/restore_backup.py` — mustaqil vosita. DB ma'lumotlarini `.env` dan oladi.

```bash
# SQL
python scripts/restore_backup.py <fayl>.sql.gz

# JSON (tasdiqlash bilan)
python scripts/restore_backup.py <fayl>.json.gz --yes
```

Qo'llab-quvvatlanadigan formatlar: `.sql.gz`, `.sql`, `.json.gz`, `.json`.

---

## 6. Tegishli `.env` o'zgaruvchilari

| O'zgaruvchi | Majburiy? | Vazifasi |
|-------------|-----------|----------|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | ✅ ha | Bazaga ulanish |
| `DB_DOCKER_CONTAINER` | ✷ ixtiyoriy | Backupni konteyner ichidagi `pg_dump` orqali olish (masalan `my_bot_postgres`) |
| `PG_DUMP_PATH` | ✷ ixtiyoriy | `pg_dump` ning aniq yo'li (masalan `/usr/bin/pg_dump`) |

---

## 7. Tez tekshiruv (checklist)

- [ ] Backup **SQL** formatda kelyaptimi? (Agar JSON bo'lsa — 2-bo'limga qarang)
- [ ] `.env` da `DB_DOCKER_CONTAINER=my_bot_postgres` bormi?
- [ ] Avtomatik backup keladimi? (har 6 soatda: 00:00/06:00/12:00/18:00, Asia/Tashkent)
- [ ] `requirements.txt` o'rnatilganmi? (`APScheduler` — JobQueue uchun shart)
- [ ] Bot **va** worker ishlab turibdimi?

---

## 8. Eslatmalar

- Backup'lar **shaxsiy** — barcha foydalanuvchi ma'lumotini o'z ichiga oladi.
  Faqat bosh admin/manager oladi; fayllarni xavfsiz saqlang.
- Eng ishonchli kombinatsiya: **SQL backup** + uni alohida joyga (masalan tashqi disk yoki
  bulutga) muntazam ko'chirib turish.
- Ikkala tiklash yo'li ham (SQL va JSON) jonli sxema ustida sinab ko'rilgan —
  qator sonlari va ketma-ketliklar mos kelishi tasdiqlangan.
