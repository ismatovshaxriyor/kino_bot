import asyncio
from tortoise import Tortoise, run_async
from tortoise.expressions import Q
from telegram import Bot
from database.movie_model import Movie
from database.init_db import init_db
from utils.settings import BOT_TOKEN, ADMIN_ID

async def main():
    print("Connecting to DB...")
    await init_db()

    if not BOT_TOKEN or not ADMIN_ID:
        print("❌ BOT_TOKEN or ADMIN_ID missing in settings.")
        return

    bot = Bot(token=BOT_TOKEN)

    # Find movies with no file_id (None or empty string)
    empty_movies = await Movie.filter(Q(file_id__isnull=True) | Q(file_id="")).all()

    to_delete = []
    kept_containers = 0

    print(f"Found {len(empty_movies)} movies with no file_id. Checking for parts...")

    for m in empty_movies:
        # Check if it has parts (if so, it's a container, keep it)
        child_count = await Movie.filter(parent_movie=m).count()
        if child_count > 0:
            kept_containers += 1
            # print(f"Skipping container: {m.movie_name} ({child_count} parts)")
        else:
            to_delete.append(m)

    print(f"Containers kept: {kept_containers}")
    print(f"Movies to delete: {len(to_delete)}")

    if not to_delete:
        msg = "✅ Video fayli bo'lmagan (va qismlari yo'q) ortiqcha kinolar topilmadi."
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=msg)
        except Exception as e:
            print(f"Failed to send message: {e}")
        print("Nothing to delete.")
        return

    # Send Report
    report_header = f"🗑 <b>{len(to_delete)} ta faylsiz kino topildi va o'chirilmoqda:</b>\n\n"
    report_body = ""

    for i, m in enumerate(to_delete):
        line = f"{i+1}. {m.movie_name} (Code: {m.movie_code})\n"
        if len(report_body) + len(line) > 3500: # Split if too long
            await bot.send_message(chat_id=ADMIN_ID, text=report_header + report_body, parse_mode="HTML")
            report_body = ""
            report_header = "Has ...\n"
        report_body += line

    if report_body:
        await bot.send_message(chat_id=ADMIN_ID, text=report_header + report_body, parse_mode="HTML")

    # Delete
    deleted_count = 0
    for m in to_delete:
        await m.delete()
        deleted_count += 1

    final_msg = f"✅ <b>{deleted_count} ta kino muvaffaqiyatli o'chirildi!</b>"
    await bot.send_message(chat_id=ADMIN_ID, text=final_msg, parse_mode="HTML")
    print("Done.")

if __name__ == "__main__":
    run_async(main())
