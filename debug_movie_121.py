from tortoise import Tortoise, run_async
from database.movie_model import Movie
from database.init_db import init_db

async def main():
    await init_db()

    # Check movie 121
    m = await Movie.get_or_none(movie_code=121)
    if not m:
        print("❌ Movie 121 not found via code.")
        # Try finding by name "Qasos"
        m = await Movie.filter(movie_name__icontains="Qasos").first()
        if m:
            print(f"Found 'Qasos' with ID {m.movie_id}, Code {m.movie_code}")
        else:
            print("❌ Movie 'Qasos' not found.")
            return

    print(f"Movie: {m.movie_name} (Code: {m.movie_code})")
    print(f"File ID Raw: '{m.file_id}'")
    print(f"File ID Type: {type(m.file_id)}")
    print(f"Parent: {m.parent_movie_id}")

    parts = await Movie.filter(parent_movie=m).count()
    print(f"Parts count: {parts}")

    if m.file_id == "None":
        print("⚠️ WARNING: file_id is literal string 'None'!")

    if len(str(m.file_id)) < 10:
        print("⚠️ WARNING: file_id seems too short/invalid.")

if __name__ == "__main__":
    run_async(main())
