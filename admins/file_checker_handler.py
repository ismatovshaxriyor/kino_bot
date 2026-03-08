import asyncio
import os
from datetime import datetime
from telegram import Update
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut, NetworkError
from telegram.ext import ContextTypes

from database import Movie
from utils import admin_required, ADMIN_ID
from utils.redis_manager import _original_send_video, _original_delete_message


@admin_required
async def file_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin 'Tekshirish' tugmasini bosganda — barcha kinolarning file_id sini tekshirish"""
    chat_id = update.effective_chat.id
    admin_id = update.effective_user.id

    # direct=True — Redis ni chetlab o'tish, chunki bizga message_id kerak
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔍 <b>Tekshirish boshlanmoqda...</b>\n\n"
            "Barcha kinolarning video fayllari tekshirilmoqda.\n"
            "Bu biroz vaqt olishi mumkin."
        ),
        parse_mode="HTML",
        direct=True,
    )

    # Background task ishga tushirish
    asyncio.create_task(
        _check_files_worker(
            bot=context.bot,
            status_chat_id=chat_id,
            status_msg_id=status_msg.message_id,
            admin_id=admin_id,
        )
    )


async def _get_movie_label(movie) -> dict:
    """Kino haqida to'liq ma'lumot qaytaradi"""
    if movie.parent_movie_id:
        parent = await Movie.get_or_none(movie_id=movie.parent_movie_id)
        parent_name = parent.movie_name if parent else "???"
        parent_code = parent.movie_code if parent else "???"
        return {
            "short": f"📎 {parent_name} — {movie.part_number}-qism (ID: {movie.movie_id})",
            "detail": (
                f"Kino: {parent_name}\n"
                f"  Kod: {parent_code}\n"
                f"  Qism: {movie.part_number}-qism\n"
                f"  Movie ID: {movie.movie_id}\n"
                f"  File ID: {movie.file_id[:40]}..."
            ),
        }
    else:
        return {
            "short": f"🎬 {movie.movie_name} (Kod: {movie.movie_code})",
            "detail": (
                f"Kino: {movie.movie_name}\n"
                f"  Kod: {movie.movie_code}\n"
                f"  Movie ID: {movie.movie_id}\n"
                f"  Yil: {movie.movie_year or 'N/A'}\n"
                f"  File ID: {movie.file_id[:40]}..."
            ),
        }


# Yaroqli file_id xatolar (fayl bor, lekin texnik cheklov)
VALID_ERRORS = [
    "file is too big",        # 20MB+ fayl — lekin ishlaydi
]

# Yaroqsiz file_id xatolar (fayl buzilgan/eskirgan)
INVALID_ERRORS = [
    "wrong file identifier",   # file_id noto'g'ri/buzilgan
    "wrong remote file",       # remote fayl yaroqsiz
    "file reference expired",  # file_id eskirgan (Telegram yangilagan)
    "invalid file_id",         # yaroqsiz format
    "wrong type",              # noto'g'ri fayl turi
    "file not found",          # fayl topilmadi
]


async def _check_single_file(bot, admin_id: int, file_id: str, max_retries: int = 2):
    """Bitta file_id ni tekshirish. Qaytaradi: (yaroqli: bool, xato: str|None)"""
    for attempt in range(max_retries + 1):
        try:
            # Original send_video — Redis patchini chetlab o'tish
            sent = await _original_send_video(
                bot,
                chat_id=admin_id,
                video=file_id,
                disable_notification=True,
            )
            # Yuborilgan xabarni darhol o'chirish
            try:
                await _original_delete_message(bot, chat_id=admin_id, message_id=sent.message_id)
            except Exception:
                pass
            return True, None

        except RetryAfter as e:
            # Rate limit — kutish va qayta urinish
            wait_time = e.retry_after + 1
            await asyncio.sleep(wait_time)
            continue

        except BadRequest as e:
            error_text = str(e).lower()
            # Yaroqli xatolar — fayl bor, texnik cheklov
            for valid_err in VALID_ERRORS:
                if valid_err in error_text:
                    return True, None
            # Yaroqsiz — fayl buzilgan
            return False, str(e)

        except Forbidden as e:
            # Bot bloklangan — bu fayl emas, bot muammosi
            return True, None

        except (TimedOut, NetworkError) as e:
            # Tarmoq xatolik — qayta urinish
            if attempt < max_retries:
                await asyncio.sleep(2)
                continue
            return None, f"Tarmoq xatoligi: {e}"

        except Exception as e:
            return False, str(e)

    return None, "Max retries exceeded"


async def _check_files_worker(bot, status_chat_id: int, status_msg_id: int, admin_id: int):
    """Background task: barcha kinolarning file_id sini tekshirish"""
    movies = await Movie.filter(file_id__isnull=False, parent_movie_id__isnull=True).order_by('movie_code')
    parts = await Movie.filter(file_id__isnull=False, parent_movie_id__isnull=False).order_by('parent_movie_id', 'part_number')

    # Bo'sh file_id larni filtrlash
    all_movies = [m for m in list(movies) + list(parts) if m.file_id and m.file_id.strip()]
    total = len(all_movies)

    if total == 0:
        try:
            await bot.edit_message_text(
                chat_id=status_chat_id,
                message_id=status_msg_id,
                text="📭 Tekshirish uchun kino topilmadi.",
            )
        except Exception:
            pass
        return

    valid = 0
    invalid_items = []
    skipped = 0

    for i, movie in enumerate(all_movies):
        is_valid, error = await _check_single_file(bot, admin_id, movie.file_id)

        if is_valid is True:
            valid += 1
        elif is_valid is False:
            info = await _get_movie_label(movie)
            info["error"] = error
            invalid_items.append(info)
        else:
            # None — tarmoq xatolik, aniq emas
            skipped += 1

        # Progress: har 30 ta kinoda yangilash
        if (i + 1) % 30 == 0 or (i + 1) == total:
            try:
                await bot.edit_message_text(
                    chat_id=status_chat_id,
                    message_id=status_msg_id,
                    text=(
                        f"🔍 <b>Tekshirilmoqda...</b>\n\n"
                        f"📊 {i + 1}/{total} | ✅ {valid} | ❌ {len(invalid_items)}"
                        + (f" | ⏭ {skipped}" if skipped else "")
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        # Rate limit himoya
        await asyncio.sleep(0.3)

    # Yakuniy natija
    if invalid_items:
        skipped_text = f"\n⏭ O'tkazildi (tarmoq xato): {skipped}" if skipped else ""
        result_text = (
            f"⚠️ <b>Tekshirish yakunlandi!</b>\n\n"
            f"📊 Jami: {total}\n"
            f"✅ Yaroqli: {valid}\n"
            f"❌ Yaroqsiz: {len(invalid_items)}"
            f"{skipped_text}\n\n"
            f"📄 To'liq hisobot fayl sifatida yuborildi."
        )

        # TXT fayl yaratish
        report_path = f"/tmp/file_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"========================================\n")
            f.write(f"  YAROQSIZ KINOLAR HISOBOTI\n")
            f.write(f"  Sana: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"========================================\n\n")
            f.write(f"Jami tekshirildi: {total}\n")
            f.write(f"Yaroqli: {valid}\n")
            f.write(f"Yaroqsiz: {len(invalid_items)}\n")
            if skipped:
                f.write(f"O'tkazildi (tarmoq xato): {skipped}\n")
            f.write(f"\n{'='*40}\n\n")

            for idx, item in enumerate(invalid_items, 1):
                f.write(f"--- #{idx} ---\n")
                f.write(f"{item['detail']}\n")
                f.write(f"  Xato: {item.get('error', 'Nomalum')}\n\n")

        try:
            await bot.edit_message_text(
                chat_id=status_chat_id,
                message_id=status_msg_id,
                text=result_text,
                parse_mode="HTML",
            )
        except Exception:
            pass

        # TXT faylni yuborish
        try:
            from utils.redis_manager import _original_send_message
            with open(report_path, "rb") as doc:
                await bot.send_document(
                    chat_id=admin_id,
                    document=doc,
                    filename=f"yaroqsiz_kinolar_{datetime.now().strftime('%Y%m%d')}.txt",
                    caption=f"📄 Yaroqsiz kinolar: {len(invalid_items)} ta",
                )
        except Exception:
            pass

        # Vaqtinchalik faylni o'chirish
        try:
            os.remove(report_path)
        except Exception:
            pass

    else:
        skipped_text = f"\n⏭ O'tkazildi (tarmoq xato): {skipped}" if skipped else ""
        result_text = (
            f"✅ <b>Tekshirish yakunlandi!</b>\n\n"
            f"📊 Jami: {total}\n"
            f"✅ Barcha kinolar yaroqli!"
            f"{skipped_text}\n\n"
            f"Hech qanday yaroqsiz fayl topilmadi. 🎉"
        )
        try:
            await bot.edit_message_text(
                chat_id=status_chat_id,
                message_id=status_msg_id,
                text=result_text,
                parse_mode="HTML",
            )
        except Exception:
            pass
