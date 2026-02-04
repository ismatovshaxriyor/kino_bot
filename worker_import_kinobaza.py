import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from database import LanguageEnum, Movie, QualityEnum
from database.init_db import init_db
from tortoise import Tortoise
from telegram import Bot
from utils.settings import ADMIN_ID, BOT_TOKEN


SERIAL_PATTERNS = (
    "serial",
    "seriali",
    "mavsum",
    "qism",
    "season",
    "episode",
)


@dataclass
class ParsedMovie:
    movie_code: int
    file_id: str
    movie_name: str
    movie_year: int | None
    movie_quality: QualityEnum | None
    movie_language: LanguageEnum | None
    views: int


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_title(raw: str) -> str:
    text = normalize_spaces(raw)
    text = re.sub(r"^[^\w\"'“”‘’]+", "", text)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return normalize_spaces(text)


def extract_year(title: str) -> int | None:
    match = re.search(r"(19\d{2}|20\d{2})", title)
    return int(match.group(1)) if match else None


def parse_quality(raw: str) -> QualityEnum | None:
    text = (raw or "").lower()
    if "1080" in text:
        return QualityEnum.P1080
    if "720" in text:
        return QualityEnum.P720
    if "480" in text:
        return QualityEnum.P480
    if "360" in text:
        return QualityEnum.P360
    return None


def parse_language(raw: str) -> LanguageEnum | None:
    text = (raw or "").lower()
    if "o'zbek" in text or "ozbek" in text:
        return LanguageEnum.UZBEK
    if "ingliz" in text or "english" in text:
        return LanguageEnum.ENGLISH
    if "rus" in text or "russian" in text:
        return LanguageEnum.RUSSIAN
    return None


def extract_file_id(raw: str) -> str:
    text = normalize_spaces(raw)
    match = re.search(r"(BAACAg[\w-]+)", text)
    return match.group(1) if match else ""


def infer_code(key: str, entry: dict[str, Any]) -> int | None:
    key_text = str(key).strip()
    if key_text.isdigit():
        return int(key_text)

    file_id = normalize_spaces(str(entry.get("file_id", "")))
    # Handles bad records like: "21 BAACAg...."
    match = re.match(r"^(\d+)\s+BAACAg", file_id)
    if match:
        return int(match.group(1))

    return None


def is_serial_like(title: str) -> bool:
    t = title.lower()
    return any(p in t for p in SERIAL_PATTERNS)


def parse_entry(key: str, entry: dict[str, Any]) -> tuple[ParsedMovie | None, str | None]:
    code = infer_code(key, entry)
    if code is None:
        return None, "invalid_code"

    title = clean_title(str(entry.get("sarlavha", "")))
    if not title:
        return None, "empty_title"
    if is_serial_like(title):
        return None, "serial_like_title"

    file_id = extract_file_id(str(entry.get("file_id", "")))
    if not file_id:
        return None, "empty_file_id"

    year = extract_year(title)
    quality = parse_quality(str(entry.get("sifat", "")))
    language = parse_language(str(entry.get("til", "")))

    try:
        views = int(entry.get("views", 0) or 0)
    except ValueError:
        views = 0

    return ParsedMovie(
        movie_code=code,
        file_id=file_id,
        movie_name=title[:255],
        movie_year=year,
        movie_quality=quality,
        movie_language=language,
        views=views,
    ), None


async def import_from_json(path: Path, apply: bool) -> tuple[dict[str, int], str, list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    await init_db()

    stats = {
        "total_records": 0,
        "single_items": 0,
        "multi_items_skipped": 0,
        "parsed_ok": 0,
        "created": 0,
        "skipped_existing": 0,
        "skipped_invalid_code": 0,
        "skipped_empty_title": 0,
        "skipped_empty_file_id": 0,
        "skipped_serial_like_title": 0,
    }
    skipped_details: list[dict[str, Any]] = []

    for key, value in raw.items():
        if isinstance(value, list):
            stats["total_records"] += len(value)
            if len(value) > 1:
                # User rule: if one code contains multiple movies, treat as serial and skip.
                stats["multi_items_skipped"] += len(value)
                for idx, serial_item in enumerate(value):
                    if isinstance(serial_item, dict):
                        skipped_details.append(
                            {
                                "key": str(key),
                                "index": idx,
                                "reason": "multi_items_serial_group",
                                "title": serial_item.get("sarlavha", ""),
                                "file_id": serial_item.get("file_id", ""),
                            }
                        )
                continue
            items = value
        elif isinstance(value, dict):
            stats["total_records"] += 1
            items = [value]
        else:
            continue

        for idx, entry in enumerate(items):
            if not isinstance(entry, dict):
                continue
            stats["single_items"] += 1
            parsed, reason = parse_entry(str(key), entry)
            if not parsed:
                stats[f"skipped_{reason}"] += 1
                skipped_details.append(
                    {
                        "key": str(key),
                        "index": idx,
                        "reason": reason,
                        "title": entry.get("sarlavha", ""),
                        "file_id": entry.get("file_id", ""),
                    }
                )
                continue
            stats["parsed_ok"] += 1

            existing = await Movie.get_or_none(movie_code=parsed.movie_code)
            if existing:
                stats["skipped_existing"] += 1
                skipped_details.append(
                    {
                        "key": str(key),
                        "index": idx,
                        "reason": "existing",
                        "movie_code": parsed.movie_code,
                        "title": parsed.movie_name,
                        "file_id": parsed.file_id,
                    }
                )
                continue

            if apply:
                await Movie.create(
                    movie_code=parsed.movie_code,
                    file_id=parsed.file_id,
                    movie_name=parsed.movie_name,
                    movie_year=parsed.movie_year,
                    movie_quality=parsed.movie_quality,
                    movie_language=parsed.movie_language,
                )
                stats["created"] += 1

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n=== IMPORT MODE: {mode} ===")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print("===========================\n")

    await Tortoise.close_connections()
    return stats, mode, skipped_details


def format_stats_message(stats: dict[str, int], mode: str, source_file: str, report_file: str | None = None) -> str:
    return (
        "📥 <b>Kinobaza import yakuni</b>\n\n"
        f"🧾 Rejim: <b>{mode}</b>\n"
        f"📄 Fayl: <code>{source_file}</code>\n\n"
        f"Jami yozuvlar: <b>{stats['total_records']}</b>\n"
        f"Yagona itemlar: <b>{stats['single_items']}</b>\n"
        f"Ko'p item (serial) skip: <b>{stats['multi_items_skipped']}</b>\n"
        f"Parserdan o'tgan: <b>{stats['parsed_ok']}</b>\n"
        f"DB ga qo'shilgan: <b>{stats['created']}</b>\n\n"
        "<b>Skip sabablar:</b>\n"
        f"• existing: <b>{stats['skipped_existing']}</b>\n"
        f"• invalid_code: <b>{stats['skipped_invalid_code']}</b>\n"
        f"• empty_title: <b>{stats['skipped_empty_title']}</b>\n"
        f"• empty_file_id: <b>{stats['skipped_empty_file_id']}</b>\n"
        f"• serial_like_title: <b>{stats['skipped_serial_like_title']}</b>\n"
        f"• multi_items_serial_group: <b>{stats['multi_items_skipped']}</b>\n\n"
        f"📎 Skipped report: <code>{report_file or 'N/A'}</code>"
    )


async def notify_admin(chat_id: int, text: str) -> None:
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


def build_skipped_detail_chunks(skipped_records: list[dict[str, Any]], chunk_limit: int = 3500) -> list[str]:
    if not skipped_records:
        return []

    chunks: list[str] = []
    current = "⚠️ <b>Skip bo'lgan kinolar:</b>\n\n"

    for i, item in enumerate(skipped_records, start=1):
        reason = str(item.get("reason", "unknown"))
        title = escape(str(item.get("title", "")) or "Noma'lum")
        key = escape(str(item.get("key", "")))
        movie_code = item.get("movie_code")
        code_part = f" | code=<code>{movie_code}</code>" if movie_code is not None else ""
        line = f"{i}) <b>Skipped movie:</b> {title}\nSabab: <code>{reason}</code> | key=<code>{key}</code>{code_part}\n\n"

        if len(current) + len(line) > chunk_limit:
            chunks.append(current)
            current = line
        else:
            current += line

    if current.strip():
        chunks.append(current)

    return chunks


async def notify_admin_with_skipped(chat_id: int, summary_text: str, skipped_records: list[dict[str, Any]]) -> None:
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=chat_id, text=summary_text, parse_mode="HTML")
    for chunk in build_skipped_detail_chunks(skipped_records):
        await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import kinobaza.json into Movie table")
    parser.add_argument("--file", default="kinobaza.json", help="Path to source JSON")
    parser.add_argument("--apply", action="store_true", help="Write to database (default: dry-run)")
    parser.add_argument("--notify-admin", action="store_true", help="Send import summary to admin in Telegram")
    parser.add_argument("--notify-chat-id", type=int, default=ADMIN_ID, help="Telegram chat id for notification")
    parser.add_argument("--report-file", default="import_skipped_report.json", help="Path to write skipped records report")
    args = parser.parse_args()

    stats, mode, skipped_details = asyncio.run(import_from_json(Path(args.file), apply=args.apply))

    report_path = Path(args.report_file)
    report_payload = {
        "source_file": args.file,
        "mode": mode,
        "stats": stats,
        "skipped_count": len(skipped_details),
        "skipped_records": skipped_details,
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📝 Skipped report saved: {report_path} (count={len(skipped_details)})")

    if args.notify_admin:
        if not BOT_TOKEN or not args.notify_chat_id:
            print("⚠️ notify-admin tanlandi, lekin BOT_TOKEN yoki chat_id topilmadi.")
            return
        message = format_stats_message(stats, mode, args.file, str(report_path))
        asyncio.run(notify_admin_with_skipped(args.notify_chat_id, message, skipped_details))
        print(f"✅ Adminga yuborildi: chat_id={args.notify_chat_id}")


if __name__ == "__main__":
    main()
