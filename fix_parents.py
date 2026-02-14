from tortoise import Tortoise, run_async
from database.movie_model import Movie
from database.init_db import init_db

async def main():
    await init_db()

    # Check count
    count = await Movie.filter(parent_movie_id__not_isnull=True).count()
    print(f"Found {count} movies attached to a parent.")

    if count > 0:
        print("Detaching all movies from parents...")
        # Update all to have no parent and no part_number
        await Movie.filter(parent_movie_id__not_isnull=True).update(parent_movie_id=None, part_number=None)
        print("✅ Success! All movies are now independent parents.")
    else:
        print("✅ No attached movies found. Everyone is already a parent.")

if __name__ == "__main__":
    run_async(main())
