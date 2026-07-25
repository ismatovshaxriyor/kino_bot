from database import Movie
from utils import PAGE_SIZE

async def get_movies_page(page: int = 1):
    offset = (page - 1) * PAGE_SIZE

    total = await Movie.filter(parent_movie=None, is_linked_series=False).count()

    movies = await Movie.filter(parent_movie=None, is_linked_series=False) \
        .order_by('-created_at') \
        .offset(offset) \
        .limit(PAGE_SIZE)

    return {
        "movies": movies,
        "page": page,
        "has_prev": page > 1,
        "has_next": offset + PAGE_SIZE < total
    }


async def get_linked_series_page(page: int = 1):
    offset = (page - 1) * PAGE_SIZE

    total = await Movie.filter(parent_movie=None, is_linked_series=True).count()

    movies = await Movie.filter(parent_movie=None, is_linked_series=True) \
        .order_by('-created_at') \
        .offset(offset) \
        .limit(PAGE_SIZE)

    return {
        "movies": movies,
        "page": page,
        "has_prev": page > 1,
        "has_next": offset + PAGE_SIZE < total
    }

