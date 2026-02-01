from database import Movie
from utils import PAGE_SIZE

async def get_movies_page(page: int = 1):
    offset = (page - 1) * PAGE_SIZE

    total = await Movie.all().count()

    movies = await Movie.all() \
        .order_by('-created_at') \
        .offset(offset) \
        .limit(PAGE_SIZE)

    return {
        "movies": movies,
        "page": page,
        "has_prev": page > 1,
        "has_next": offset + PAGE_SIZE < total
    }

