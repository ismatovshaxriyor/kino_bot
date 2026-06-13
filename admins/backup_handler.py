"""Ma'lumotlar bazasidan zaxira nusxa olish va adminlarga yuborish.

- Asosiy yo'l: ``pg_dump`` (toza SQL, gzip bilan siqilgan) — to'liq qayta tiklanadi.
- Zaxira yo'l: ``pg_dump`` topilmasa, barcha jadvallarni Tortoise/raw SQL orqali
  JSON formatda eksport qilish (gzip bilan).

Fayl Telegramga ``send_document`` orqali to'g'ridan-to'g'ri yuboriladi
(bu metod Redis navbatiga tushmaydi, shu sababli worker'ga bog'liq emas).
"""
import asyncio
import gzip
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir

from telegram import Update
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


async def backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💾 Zaxira nusxa tugmasi — faqat bosh admin va managerga ruxsat."""
    user_id = update.effective_user.id
    if user_id not in (ADMIN_ID, MANAGER_ID):
        return  # Tugma faqat super-adminlarga ko'rinadi; boshqalarni jim e'tiborsiz qoldiramiz

    chat_id = update.effective_chat.id

    # Status xabarlari to'g'ridan-to'g'ri (direct=True) yuboriladi — chunki backup fayli
    # ham (send_document) navbatsiz ketadi; aks holda xabarlar tartibi buziladi.
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ <b>Zaxira nusxa tayyorlanmoqda...</b>\nBu bir necha soniya olishi mumkin.",
        parse_mode="HTML",
        direct=True,
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
