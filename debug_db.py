from tortoise import Tortoise, run_async
from database.movie_model import Movie
from database.init_db import init_db

async def main():
    await init_db()

    total = await Movie.all().count()
    with_parent = await Movie.filter(parent_movie_id__not_isnull=True).count()
    without_parent = await Movie.filter(parent_movie_id__isnull=True).count()

    print(f"Total: {total}")
    print(f"With Parent: {with_parent}")
    print(f"Without Parent: {without_parent}")

    if with_parent > 0:
        print("Sample with parent:")
        async for m in Movie.filter(parent_movie_id__not_isnull=True).limit(5).prefetch_related('parent_movie'):
            print(f"Movie {m.movie_id} ({m.movie_name}) -> Parent: {m.parent_movie.movie_id} ({m.parent_movie.movie_name})")

        # Check if they all point to the same parent
        parents = await Movie.filter(parent_movie_id__not_isnull=True).values_list('parent_movie_id', flat=True)
        unique_parents = set(parents)
        print(f"Unique parents count: {len(unique_parents)}")
        print(f"Parent IDs: {list(unique_parents)[:10]}")

if __name__ == "__main__":
    run_async(main())
