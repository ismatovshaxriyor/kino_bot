"""Kino nomi bo'yicha pg_trgm asosidagi moslashuvchan (fuzzy) qidiruv.

Postgres tomonida `uz_normalize()` funksiyasi (database/init_db.py dagi
ensure_search_index() da yaratiladi) apostrof variantlarini
(', ', ', ʻ, ʼ, `, ´, ʹ, ʺ) va registrni bir xillashtiradi, shuning uchun
"po'lat", "po'lat" va "polat" bir xil so'z sifatida topiladi. Aniq substring
mos kelish natijalari trigram o'xshashlik darajasidan ustun qo'yib
saralanadi, shu bilan birga bir-ikkita harfi xato yozilgan so'zlar ham
(masalan "pulat" -> "po'lat") topiladi.
"""
from tortoise import Tortoise

SIMILARITY_THRESHOLD = 0.25

_WHERE_CLAUSE = """
    parent_movie_id IS NULL
    AND (
        uz_normalize(movie_name) ILIKE '%%' || uz_normalize(%s) || '%%'
        OR similarity(uz_normalize(movie_name), uz_normalize(%s)) > %s
    )
"""


async def search_movie_ids(query: str, *, limit: int, offset: int = 0) -> tuple[list[int], int]:
    """Fuzzy qidiruvga mos kino id'larini (o'xshashlik bo'yicha saralangan) va jami sonini qaytaradi."""
    conn = Tortoise.get_connection("default")

    count_rows = await conn.execute_query_dict(
        f"SELECT COUNT(*) AS cnt FROM movie WHERE {_WHERE_CLAUSE}",
        [query, query, SIMILARITY_THRESHOLD],
    )
    total = count_rows[0]["cnt"] if count_rows else 0

    rows = await conn.execute_query_dict(
        f"""
        SELECT movie_id FROM movie
        WHERE {_WHERE_CLAUSE}
        ORDER BY
            (uz_normalize(movie_name) ILIKE '%%' || uz_normalize(%s) || '%%') DESC,
            similarity(uz_normalize(movie_name), uz_normalize(%s)) DESC,
            movie_name ASC
        LIMIT %s OFFSET %s
        """,
        [query, query, SIMILARITY_THRESHOLD, query, query, limit, offset],
    )
    return [r["movie_id"] for r in rows], total


async def search_movies(query: str, *, limit: int, offset: int = 0):
    """Fuzzy qidiruv natijasidagi Movie obyektlarini (saralangan tartibda) va jami sonini qaytaradi."""
    from database import Movie

    ids, total = await search_movie_ids(query, limit=limit, offset=offset)
    if not ids:
        return [], total

    movies = await Movie.filter(movie_id__in=ids)
    by_id = {m.movie_id: m for m in movies}
    ordered = [by_id[i] for i in ids if i in by_id]
    return ordered, total
