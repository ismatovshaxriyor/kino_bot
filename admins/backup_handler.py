"""Ma'lumotlar bazasidan zaxira nusxa olish, adminlarga yuborish va tiklash.

Backup:
- Asosiy yo'l: ``pg_dump`` (toza SQL, gzip bilan siqilgan) — to'liq qayta tiklanadi.
- Zaxira yo'l: ``pg_dump`` topilmasa, barcha jadvallarni Tortoise/raw SQL orqali
  JSON formatda eksport qilish (gzip bilan).

Restore (tiklash):
- SQL (.sql.gz / .sql) — ``psql`` yoki ``docker exec psql`` orqali tiklanadi.
- JSON (.json.gz / .json) — Tortoise ORM raw SQL orqali jadvalga INSERT qilinadi.

Fayl Telegramga ``send_document`` orqali to'g'ridan-to'g'ri yuboriladi
(bu metod Redis navbatiga tushmaydi, shu sababli worker'ga bog'liq emas).
"""
import asyncio
import gzip
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from utils.settings import (
    ADMIN_ID,
    MANAGER_ID,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_HOST,
    DB_PORT,
    PG_DUMP_PATH,
    DB_DOCKER_CONTAINER,
)

logger = logging.getLogger(__name__)

# Telegram bot orqali yuborilishi mumkin bo'lgan hujjat hajmi chegarasi
TELEGRAM_DOC_LIMIT = 50 * 1024 * 1024  # 50 MB

# pg_dump ko'pincha PATH da bo'lmaydi (masalan, macOS libpq keg-only,
# yoki host'da postgresql-client o'rnatilmagan) — bir nechta joyni tekshiramiz.
_PG_DUMP_CANDIDATES = (
    "/opt/homebrew/opt/libpq/bin/pg_dump",
    "/usr/local/opt/libpq/bin/pg_dump",
    "/usr/bin/pg_dump",
    "/usr/local/bin/pg_dump",
    "/usr/lib/postgresql/17/bin/pg_dump",
    "/usr/lib/postgresql/16/bin/pg_dump",
    "/usr/lib/postgresql/15/bin/pg_dump",
)


def _find_pg_dump() -> str | None:
    # 1) .env dagi aniq yo'l
    if PG_DUMP_PATH and os.path.exists(PG_DUMP_PATH):
        return PG_DUMP_PATH
    # 2) PATH
    found = shutil.which("pg_dump")
    if found:
        return found
    # 3) Keng tarqalgan joylar
    for candidate in _PG_DUMP_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


async def _run_pg_dump(cmd: list, env: dict | None, out_path: Path) -> Path | None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("pg_dump xato (kod %s): %s", proc.returncode, stderr.decode(errors="replace")[:500])
        return None
    if not stdout.strip():
        logger.error("pg_dump bo'sh natija qaytardi")
        return None
    # Siqishni alohida threadda (bloklamaslik uchun)
    await asyncio.to_thread(_gzip_bytes, stdout, out_path)
    return out_path


async def _pg_dump_backup(out_path: Path) -> Path | None:
    """Host'dagi pg_dump orqali SQL zaxira. Topilmasa None."""
    pg_dump = _find_pg_dump()
    if not pg_dump:
        return None

    env = dict(os.environ)
    if DB_PASSWORD:
        env["PGPASSWORD"] = DB_PASSWORD

    cmd = [
        pg_dump,
        "-h", str(DB_HOST),
        "-p", str(DB_PORT),
        "-U", str(DB_USER),
        "-d", str(DB_NAME),
        "--no-owner",
        "--no-privileges",
    ]
    return await _run_pg_dump(cmd, env, out_path)


async def _pg_dump_via_docker(out_path: Path) -> Path | None:
    """pg_dump'ni postgres konteyneri ichida ishlatish (DB_DOCKER_CONTAINER o'rnatilgan bo'lsa).

    Konteyner ichidagi pg_dump versiyasi server bilan aynan mos keladi — eng ishonchli yo'l.
    """
    if not DB_DOCKER_CONTAINER:
        return None
    docker = shutil.which("docker")
    if not docker:
        logger.info("docker topilmadi, docker-exec pg_dump o'tkazib yuborildi")
        return None

    cmd = [docker, "exec"]
    if DB_PASSWORD:
        cmd += ["-e", f"PGPASSWORD={DB_PASSWORD}"]
    cmd += [
        DB_DOCKER_CONTAINER,
        "pg_dump",
        "-U", str(DB_USER),
        "-d", str(DB_NAME),
        "--no-owner",
        "--no-privileges",
    ]
    return await _run_pg_dump(cmd, None, out_path)


def _gzip_bytes(data: bytes, out_path: Path) -> None:
    with gzip.open(out_path, "wb") as f:
        f.write(data)


async def _json_backup(out_path: Path) -> Path:
    """Barcha public jadvallarni JSON ko'rinishida eksport qilish (gzip)."""
    from tortoise import Tortoise

    conn = Tortoise.get_connection("default")
    tables = await conn.execute_query_dict(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
    )

    dump: dict = {
        "_meta": {
            "generated_at": datetime.now().isoformat(),
            "database": DB_NAME,
            "format": "json",
        }
    }
    for row in tables:
        name = row["tablename"]
        try:
            rows = await conn.execute_query_dict(f'SELECT * FROM "{name}";')
            dump[name] = rows
        except Exception as e:
            logger.warning("Jadval eksportida xato (%s): %s", name, e)
            dump[name] = {"error": str(e)}

    await asyncio.to_thread(_write_json_gz, dump, out_path)
    return out_path


def _write_json_gz(dump: dict, out_path: Path) -> None:
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, default=str)


async def create_backup() -> tuple[Path, str]:
    """Zaxira fayl yaratish. (path, format_label) qaytaradi.

    Avval pg_dump (.sql.gz), bo'lmasa JSON (.json.gz).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = Path(gettempdir())
    sql_path = tmp / f"kino_backup_{ts}.sql.gz"

    # 1) Host'dagi pg_dump
    try:
        if await _pg_dump_backup(sql_path) is not None:
            return sql_path, "SQL (pg_dump)"
    except Exception as e:
        logger.error("pg_dump (host) zaxirasida xato: %s", e)

    # 2) Docker konteyner ichidagi pg_dump
    try:
        if await _pg_dump_via_docker(sql_path) is not None:
            return sql_path, "SQL (pg_dump, docker)"
    except Exception as e:
        logger.error("pg_dump (docker) zaxirasida xato: %s", e)

    # 3) Zaxira usul — JSON (pg_dump topilmadi)
    logger.warning("pg_dump topilmadi — JSON zaxiraga o'tildi. SQL backup uchun "
                   "PG_DUMP_PATH yoki DB_DOCKER_CONTAINER ni sozlang.")
    json_path = tmp / f"kino_backup_{ts}.json.gz"
    await _json_backup(json_path)
    return json_path, "JSON (zaxira usul)"


async def send_backup(bot, chat_ids, *, reason: str = "Qo'lda") -> tuple[int, str]:
    """Zaxira yaratib, berilgan chat_id'larga hujjat sifatida yuborish.

    (yuborilganlar_soni, fayl_nomi) qaytaradi.
    """
    path, fmt_label = await create_backup()
    size_bytes = path.stat().st_size
    size_mb = size_bytes / 1024 / 1024

    caption = (
        "💾 <b>Ma'lumotlar bazasi zaxira nusxasi</b>\n\n"
        f"📦 Format: {fmt_label}\n"
        f"📁 Hajmi: {size_mb:.2f} MB\n"
        f"🕒 {datetime.now():%Y-%m-%d %H:%M}\n"
        f"🔖 Sabab: {reason}"
    )

    sent = 0
    try:
        if size_bytes > TELEGRAM_DOC_LIMIT:
            warn = (
                "⚠️ <b>Zaxira hajmi 50 MB dan oshdi</b> — Telegram orqali yuborib bo'lmaydi.\n"
                f"📁 Hajmi: {size_mb:.2f} MB\n"
                f"📂 Fayl serverda saqlandi: <code>{path}</code>"
            )
            for cid in chat_ids:
                try:
                    await bot.send_message(chat_id=cid, text=warn, parse_mode="HTML")
                except TelegramError as e:
                    logger.error("Zaxira ogohlantirishini %s ga yuborib bo'lmadi: %s", cid, e)
            return 0, path.name

        for cid in chat_ids:
            try:
                with path.open("rb") as f:
                    await bot.send_document(
                        chat_id=cid,
                        document=f,
                        filename=path.name,
                        caption=caption,
                        parse_mode="HTML",
                    )
                sent += 1
            except TelegramError as e:
                logger.error("Zaxirani %s ga yuborib bo'lmadi: %s", cid, e)
        return sent, path.name
    finally:
        # 50 MB dan oshgan holatda faylni saqlab qolamiz, aks holda o'chiramiz
        if size_bytes <= TELEGRAM_DOC_LIMIT:
            try:
                path.unlink()
            except OSError:
                pass



# Jadval nomlari uchun xavfsizlik tekshiruvi (SQL injection dan himoya)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Qabul qilinadigan backup fayl formatlari
_ALLOWED_EXTENSIONS = (".sql.gz", ".json.gz", ".sql", ".json")


async def backup_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💾 Zaxira nusxa tugmasi — menyu ko'rsatish (backup olish / tiklash)."""
    user_id = update.effective_user.id
    if user_id not in (ADMIN_ID, MANAGER_ID):
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Backup olish", callback_data="backup_download")],
        [InlineKeyboardButton("📥 Backup tiklash", callback_data="backup_restore_start")],
    ])

    await update.message.reply_text(
        "💾 <b>Zaxira nusxa boshqaruvi</b>\n\n"
        "Kerakli amalni tanlang:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def backup_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📤 Backup olish — inline tugma callback."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in (ADMIN_ID, MANAGER_ID):
        return

    chat_id = query.message.chat_id

    await query.edit_message_text(
        "⏳ <b>Zaxira nusxa tayyorlanmoqda...</b>\nBu bir necha soniya olishi mumkin.",
        parse_mode="HTML",
    )

    try:
        sent, filename = await send_backup(
            context.bot, [ADMIN_ID, MANAGER_ID], reason="Qo'lda (admin)"
        )
        if sent == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Zaxira tayyorlandi, lekin yuborishda muammo bo'ldi. Loglarni tekshiring.",
                parse_mode="HTML",
                direct=True,
            )
    except Exception as e:
        logger.exception("Qo'lda zaxira nusxasida xato: %s", e)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ <b>Zaxira nusxa olishda xato:</b>\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
            direct=True,
        )


# ======================= RESTORE (TIKLASH) =======================


def _find_psql() -> str | None:
    """psql binary yo'lini topish."""
    found = shutil.which("psql")
    if found:
        return found
    for candidate in (
        "/opt/homebrew/opt/libpq/bin/psql",
        "/usr/local/opt/libpq/bin/psql",
        "/usr/bin/psql",
        "/usr/local/bin/psql",
        "/usr/lib/postgresql/17/bin/psql",
        "/usr/lib/postgresql/16/bin/psql",
        "/usr/lib/postgresql/15/bin/psql",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


async def _restore_from_sql(file_path: Path) -> tuple[bool, str]:
    """SQL (.sql.gz / .sql) backupni psql orqali tiklash."""
    # Faylni o'qish (gzip bo'lsa ochish)
    if file_path.suffix == ".gz":
        data = await asyncio.to_thread(lambda: gzip.open(file_path, "rb").read())
    else:
        data = await asyncio.to_thread(file_path.read_bytes)

    if not data.strip():
        return False, "SQL fayl bo'sh"

    # 1) Host'dagi psql
    psql = _find_psql()
    if psql:
        env = dict(os.environ)
        if DB_PASSWORD:
            env["PGPASSWORD"] = DB_PASSWORD
        cmd = [psql, "-h", str(DB_HOST), "-p", str(DB_PORT),
               "-U", str(DB_USER), "-d", str(DB_NAME), "-v", "ON_ERROR_STOP=0"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate(input=data)
        if proc.returncode == 0:
            return True, "SQL backup psql orqali muvaffaqiyatli tiklandi"
        else:
            err_msg = stderr.decode(errors="replace")[:500]
            # ON_ERROR_STOP=0 shuning uchun ba'zi xatolar bo'lishi mumkin, lekin data tiklangan
            logger.warning("psql restore ogohlantirishlari: %s", err_msg)
            return True, f"SQL backup tiklandi (ba'zi ogohlantirishlar bor)"

    # 2) Docker konteyner ichidagi psql
    docker = shutil.which("docker")
    if DB_DOCKER_CONTAINER and docker:
        cmd = [docker, "exec", "-i"]
        if DB_PASSWORD:
            cmd += ["-e", f"PGPASSWORD={DB_PASSWORD}"]
        cmd += [DB_DOCKER_CONTAINER, "psql", "-U", str(DB_USER), "-d", str(DB_NAME)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=data)
        if proc.returncode == 0:
            return True, "SQL backup docker psql orqali muvaffaqiyatli tiklandi"
        else:
            err_msg = stderr.decode(errors="replace")[:500]
            logger.warning("docker psql restore ogohlantirishlari: %s", err_msg)
            return True, f"SQL backup tiklandi (ba'zi ogohlantirishlar bor)"

    return False, "psql topilmadi (host'da ham, docker'da ham). SQL backupni tiklab bo'lmadi."


async def _restore_from_json(file_path: Path) -> tuple[bool, str]:
    """JSON (.json.gz / .json) backupni Tortoise ORM raw SQL orqali tiklash."""
    from tortoise import Tortoise

    # Faylni o'qish
    if file_path.suffix == ".gz":
        raw = await asyncio.to_thread(lambda: gzip.open(file_path, "rt", encoding="utf-8").read())
    else:
        raw = await asyncio.to_thread(lambda: file_path.read_text(encoding="utf-8"))

    try:
        dump = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"JSON formatida xato: {e}"

    tables = [t for t in dump.keys() if t != "_meta"]

    # Jadval nomlarini tekshirish (SQL injection himoyasi)
    for t in tables:
        if not _IDENT_RE.match(t):
            return False, f"Shubhali jadval nomi: {t!r} — tiklash to'xtatildi"

    total_rows = sum(len(dump[t]) for t in tables if isinstance(dump[t], list))

    conn = Tortoise.get_connection("default")

    try:
        # FK/triggerlarni vaqtincha o'chiramiz — istalgan tartibda insert qilish uchun
        await conn.execute_query("SET session_replication_role = replica;")

        # Barcha jadvallarni tozalash
        if tables:
            quoted = ", ".join(f'"{t}"' for t in tables)
            await conn.execute_query(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE;")

        restored_rows = 0
        for t in tables:
            rows = dump[t]
            if not isinstance(rows, list) or not rows:
                continue

            cols = list(rows[0].keys())
            # Ustun nomlarini tekshirish
            for c in cols:
                if not _IDENT_RE.match(c):
                    raise ValueError(f"Shubhali ustun nomi: {t}.{c!r}")

            collist = ", ".join(f'"{c}"' for c in cols)

            for row in rows:
                placeholders = ", ".join(["%s"] * len(cols))
                sql = f'INSERT INTO "{t}" ({collist}) VALUES ({placeholders})'
                values = []
                for c in cols:
                    v = row.get(c)
                    # dict/list → JSON string (JSONB ustunlar uchun)
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v, ensure_ascii=False, default=str)
                    values.append(v)
                await conn.execute_query(sql, values)
                restored_rows += 1

        # Auto-increment ketma-ketliklarni (sequence) eng katta qiymatga tiklash
        for t in tables:
            rows = dump[t]
            if not isinstance(rows, list) or not rows:
                continue
            for c in rows[0].keys():
                seq_rows = await conn.execute_query_dict(
                    "SELECT pg_get_serial_sequence(%s, %s) AS seq", [t, c]
                )
                seq = seq_rows[0]["seq"] if seq_rows else None
                if seq:
                    await conn.execute_query(
                        f'SELECT setval(%s, GREATEST(COALESCE((SELECT MAX("{c}") FROM "{t}"), 1), 1))',
                        [seq],
                    )

        # FK/triggerlarni qayta yoqish
        await conn.execute_query("SET session_replication_role = DEFAULT;")

        return True, (
            f"JSON backup muvaffaqiyatli tiklandi\n"
            f"📊 Jadvallar: {len(tables)} | Qatorlar: {restored_rows}"
        )

    except Exception as e:
        # Xatolik bo'lsa, session_replication_role ni qaytarish
        try:
            await conn.execute_query("SET session_replication_role = DEFAULT;")
        except Exception:
            pass
        logger.exception("JSON restore xatosi: %s", e)
        return False, f"Tiklashda xato: {str(e)[:300]}"


async def backup_restore_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📥 Backup tiklash — fayl yuborishni so'rash."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in (ADMIN_ID, MANAGER_ID):
        return

    context.user_data["state"] = "WAITING_BACKUP_FILE"

    cancel_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="backup_restore_cancel")],
    ])

    await query.edit_message_text(
        "📥 <b>Backup tiklash</b>\n\n"
        "Backup faylni hujjat (document) sifatida yuboring.\n\n"
        "📎 Qabul qilinadigan formatlar:\n"
        "• <code>.sql.gz</code> — SQL backup (pg_dump)\n"
        "• <code>.json.gz</code> — JSON backup\n"
        "• <code>.sql</code> — SQL fayl\n"
        "• <code>.json</code> — JSON fayl\n\n"
        "⚠️ <i>Fayl hajmi 20 MB dan oshmasligi kerak (Telegram cheklovi).</i>",
        reply_markup=cancel_keyboard,
        parse_mode="HTML",
    )


async def backup_restore_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Backup tiklashni bekor qilish."""
    query = update.callback_query
    await query.answer("Bekor qilindi")

    context.user_data.pop("state", None)
    context.user_data.pop("restore_file_path", None)

    await query.edit_message_text(
        "❌ Backup tiklash bekor qilindi.",
        parse_mode="HTML",
    )


async def restore_receive_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin backup faylni yuborsa — qabul qilish va tasdiqlashni so'rash."""
    user_id = update.effective_user.id
    if user_id not in (ADMIN_ID, MANAGER_ID):
        return

    state = context.user_data.get("state")
    if state != "WAITING_BACKUP_FILE":
        return

    doc = update.message.document
    if not doc:
        await update.message.reply_text(
            "⚠️ Iltimos, faylni <b>hujjat</b> (document) sifatida yuboring.",
            parse_mode="HTML",
        )
        return

    file_name = (doc.file_name or "").lower()

    # Format tekshiruvi
    valid = any(file_name.endswith(ext) for ext in _ALLOWED_EXTENSIONS)
    if not valid:
        await update.message.reply_text(
            "❌ <b>Noto'g'ri fayl formati!</b>\n\n"
            "Qabul qilinadigan formatlar:\n"
            "• <code>.sql.gz</code>\n"
            "• <code>.json.gz</code>\n"
            "• <code>.sql</code>\n"
            "• <code>.json</code>",
            parse_mode="HTML",
        )
        return

    # Hajm tekshiruvi (Telegram 20 MB limit)
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "❌ Fayl hajmi juda katta (20 MB dan oshmasligi kerak).",
            parse_mode="HTML",
        )
        return

    # Faylni yuklab olish
    await update.message.reply_text(
        "⏳ <b>Fayl yuklab olinmoqda...</b>",
        parse_mode="HTML",
    )

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        tmp = Path(gettempdir())
        local_path = tmp / f"restore_{doc.file_name}"
        await tg_file.download_to_drive(local_path)
    except Exception as e:
        logger.exception("Backup faylni yuklab olishda xato: %s", e)
        await update.message.reply_text(
            f"❌ Faylni yuklab olishda xato:\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
        )
        return

    # Fayl yo'lini saqlash
    context.user_data["restore_file_path"] = str(local_path)
    context.user_data["state"] = "WAITING_RESTORE_CONFIRM"

    # Fayl hajmi
    size_mb = local_path.stat().st_size / 1024 / 1024

    # Format aniqlash
    if file_name.endswith(".sql.gz") or file_name.endswith(".sql"):
        fmt = "SQL (pg_dump)"
    else:
        fmt = "JSON"

    confirm_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data="backup_restore_confirm"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data="backup_restore_reject"),
        ],
    ])

    await update.message.reply_text(
        "⚠️ <b>DIQQAT! Ma'lumotlar bazasini tiklash</b>\n\n"
        f"📦 Fayl: <code>{doc.file_name}</code>\n"
        f"📁 Hajmi: {size_mb:.2f} MB\n"
        f"📋 Format: {fmt}\n\n"
        "🔴 <b>Bu amal mavjud barcha ma'lumotlarni O'CHIRADI\n"
        "va backup fayldan tiklaydi!</b>\n\n"
        "Davom etishni tasdiqlaysizmi?",
        reply_markup=confirm_keyboard,
        parse_mode="HTML",
    )


async def restore_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tiklashni tasdiqlash yoki bekor qilish callback."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in (ADMIN_ID, MANAGER_ID):
        return

    action = query.data  # backup_restore_confirm yoki backup_restore_reject

    if action == "backup_restore_reject":
        # Bekor qilish
        file_path = context.user_data.pop("restore_file_path", None)
        context.user_data.pop("state", None)

        # Temp faylni o'chirish
        if file_path:
            try:
                Path(file_path).unlink(missing_ok=True)
            except OSError:
                pass

        await query.edit_message_text(
            "❌ Backup tiklash bekor qilindi.\n"
            "Ma'lumotlar bazasi o'zgartirilmadi.",
            parse_mode="HTML",
        )
        return

    # Tasdiqlash — tiklashni boshlash
    file_path_str = context.user_data.pop("restore_file_path", None)
    context.user_data.pop("state", None)

    if not file_path_str:
        await query.edit_message_text(
            "❌ Backup fayli topilmadi. Qaytadan urinib ko'ring.",
            parse_mode="HTML",
        )
        return

    file_path = Path(file_path_str)
    if not file_path.exists():
        await query.edit_message_text(
            "❌ Backup fayli serverdan topilmadi. Qaytadan yuboring.",
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        "⏳ <b>Ma'lumotlar bazasi tiklanmoqda...</b>\n"
        "Bu bir necha soniya olishi mumkin. Iltimos kuting.",
        parse_mode="HTML",
    )

    try:
        file_name = file_path.name.lower()
        if file_name.endswith(".sql.gz") or file_name.endswith(".sql"):
            success, message = await _restore_from_sql(file_path)
        elif file_name.endswith(".json.gz") or file_name.endswith(".json"):
            success, message = await _restore_from_json(file_path)
        else:
            success, message = False, "Noma'lum fayl formati"

        if success:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "✅ <b>Ma'lumotlar bazasi muvaffaqiyatli tiklandi!</b>\n\n"
                    f"📋 {message}\n"
                    f"🕒 {datetime.now():%Y-%m-%d %H:%M}"
                ),
                parse_mode="HTML",
                direct=True,
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"❌ <b>Tiklashda xato:</b>\n"
                    f"<code>{message}</code>"
                ),
                parse_mode="HTML",
                direct=True,
            )
    except Exception as e:
        logger.exception("Backup tiklashda kutilmagan xato: %s", e)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"❌ <b>Kutilmagan xato:</b>\n<code>{str(e)[:300]}</code>",
            parse_mode="HTML",
            direct=True,
        )
    finally:
        # Temp faylni o'chirish
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass



async def scheduled_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue: har 6 soatda bosh adminga avtomatik zaxira yuborish."""
    try:
        sent, filename = await send_backup(
            context.bot, [ADMIN_ID], reason="Avtomatik zaxira (har 6 soat)"
        )
        logger.info("Avtomatik zaxira yuborildi (%s), qabul qiluvchilar: %s", filename, sent)
    except Exception as e:
        logger.exception("Avtomatik zaxira nusxasida xato: %s", e)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 <b>Avtomatik zaxira nusxasi xatosi:</b>\n<code>{str(e)[:300]}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
