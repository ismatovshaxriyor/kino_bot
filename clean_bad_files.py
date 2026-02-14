import asyncio
from tortoise import Tortoise, run_async
from tortoise.expressions import Q
from telegram import Bot
from telegram.error import BadRequest
from database.movie_model import Movie
from database.init_db import init_db
from utils.settings import BOT_TOKEN, ADMIN_ID

async def main():
    print("Connecting to DB...")
    await init_db()

    bot = Bot(token=BOT_TOKEN)

    # Get all movies with file_id
    movies = await Movie.filter(Q(file_id__not_isnull=True) & ~Q(file_id="")).all()
    print(f"Checking {len(movies)} movies for valid file_ids...")

    bad_movies = []

    for i, m in enumerate(movies):
        if i % 10 == 0:
            print(f"Processed {i}/{len(movies)}...")

        try:
            # Try to get file info. This validates the file_id.
            # Note: For very old files, this might fail even if they are sendable?
            # Usually send_video is the ultimate test, but get_file is less invasive.
            # If get_file fails with "Wrong file identifier", it's definitely bad.
            await bot.get_file(m.file_id)

        except BadRequest as e:
            err_msg = str(e)
            if "Wrong file identifier" in err_msg or "file is temporarily unavailable" in err_msg or "Invalid file_id" in err_msg:
                print(f"❌ BAD FILE: {m.movie_name} (ID: {m.movie_id}) - {err_msg}")
                bad_movies.append(m)
            else:
                print(f"⚠️ Warning for {m.movie_name}: {err_msg}")
        except Exception as e:
            print(f"⚠️ Error checking {m.movie_name}: {e}")

        # Rate limit to avoid flooding API
        await asyncio.sleep(0.1)

    print(f"Scan complete. Found {len(bad_movies)} movies with invalid file_ids.")

    if not bad_movies:
        await bot.send_message(chat_id=ADMIN_ID, text="✅ Barcha file_id lar yaroqli ko'rinadi.")
        return

    # Report & Delete
    report = f"🗑 <b>{len(bad_movies)} ta yaroqsiz (buzilgan) fayl topildi va o'chirilmoqda:</b>\n\n"
    for m in bad_movies[:50]:
        report += f"❌ {m.movie_name} (Code: {m.movie_code})\n"

    if len(bad_movies) > 50:
        report += f"\n... va yana {len(bad_movies) - 50} ta."

    try:
        await bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="HTML")
    except:
        pass

    # Delete
    for m in bad_movies:
        await m.delete()

    await bot.send_message(chat_id=ADMIN_ID, text="✅ Buzilgan fayllar o'chirib tashlandi!")
    print("Cleanup done.")

if __name__ == "__main__":
    run_async(main())
