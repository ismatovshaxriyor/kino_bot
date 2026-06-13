"""Kino kartasi (caption + tugmalar) uchun markazlashtirilgan yordamchilar.

Ilgari bir xil "kino kartasi" mantig'i bir nechta joyda (user_callbacks,
common_handler) nusxalangan edi. Endi hammasi shu modulda — bitta manba.
"""
from html import escape
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import Movie, Rating
from database.user_model import USER_TYPE
from utils.settings import ADMIN_ID, MANAGER_ID

# Caption ichidagi tavsif uchun maksimal uzunlik
DESC_LIMIT = 400

# Ma'lumot yo'q bo'lganda ko'rsatiladigan matn
UNKNOWN = "Noma'lum"


def is_privileged(user, user_id: int) -> bool:
    """Foydalanuvchi admin/manager huquqiga egami?

    Eslatma: ``str(user.user_type) == 'admin'`` Python 3.11+ da ishlamaydi
    (``str(Enum)`` enum nomini qaytaradi), shu sababli enum bilan solishtiramiz.
    """
    if user is not None and user.user_type == USER_TYPE.ADMIN:
        return True
    return user_id in (ADMIN_ID, MANAGER_ID)


async def get_child_parts(movie: Movie) -> list[Movie]:
    """Kinoning qism-bolalari (part_number bo'yicha tartiblangan)."""
    return await Movie.filter(parent_movie=movie).order_by("part_number")


async def movie_caption(movie: Movie) -> str:
    """Kino ma'lumotlari (HTML caption). Janr/davlatlarni o'zi yuklaydi."""
    genres = await movie.movie_genre.all().order_by("name")
    genres_text = ", ".join(g.name for g in genres) if genres else UNKNOWN

    countries = await movie.movie_country.all().order_by("name")
    countries_text = ", ".join(c.name for c in countries) if countries else UNKNOWN

    caption = (
        f"🎬 <b>{escape(movie.movie_name)}</b>\n\n"
        f"📅 <b>Yil:</b> {movie.movie_year or UNKNOWN}\n"
        f"🎭 <b>Janr:</b> {escape(genres_text)}\n"
        f"🌍 <b>Davlat:</b> {escape(countries_text)}\n"
        f"⏱ <b>Davomiylik:</b> {movie.duration_formatted}\n"
        f"📺 <b>Sifat:</b> {movie.movie_quality.value if movie.movie_quality else UNKNOWN}\n"
        f"🗣 <b>Til:</b> {movie.movie_language.value if movie.movie_language else UNKNOWN}\n"
        f"⭐ <b>Reyting:</b> {movie.average_rating}/5 ({movie.rating_count} ovoz)\n"
    )

    if movie.movie_description:
        desc = movie.movie_description[:DESC_LIMIT]
        if len(movie.movie_description) > DESC_LIMIT:
            desc += "..."
        caption += f"\n📝 <b>Tavsif:</b> {escape(desc)}\n"

    if movie.movie_code:
        caption += f"\n📥 <b>Kod:</b> <code>{movie.movie_code}</code>"

    return caption


def _share_button(movie: Movie, bot_username: str) -> InlineKeyboardButton:
    share_text = f"🎬 {movie.movie_name} kinosini tavsiya qilaman!\n\nBot orqali ko'rish:"
    share_url = (
        f"https://t.me/share/url?url=https://t.me/{bot_username}"
        f"?start={movie.movie_code}&text={quote(share_text)}"
    )
    return InlineKeyboardButton("↗️ Do'stlarga ulashish", url=share_url)


async def _part_nav_buttons(movie: Movie) -> list:
    """Qismli kino uchun oldingi/keyingi/ro'yxat navigatsiya tugmalari."""
    if not movie.parent_movie_id:
        # Parent (container) — bolalari bormi?
        child_count = await Movie.filter(parent_movie=movie).count()
        if child_count > 0:
            return [[InlineKeyboardButton("🔙 Qismlarga qaytish", callback_data=f"umovie_{movie.movie_id}")]]
        return []

    parent_id = movie.parent_movie_id
    parent = await Movie.get_or_none(movie_id=parent_id)
    if not parent:
        return []

    # Barcha qismlarni yig'ish (parent + children)
    all_parts = []
    if parent.file_id:
        all_parts.append(parent)  # parent o'zi 1-qism
    children = await Movie.filter(parent_movie_id=parent_id).order_by("part_number")
    all_parts.extend(children)

    current_idx = None
    for i, part in enumerate(all_parts):
        if part.movie_id == movie.movie_id:
            current_idx = i
            break

    if current_idx is None:
        return [[InlineKeyboardButton("🔙 Qismlarga qaytish", callback_data=f"umovie_{parent_id}")]]

    nav_row = []
    if current_idx > 0:
        prev_part = all_parts[current_idx - 1]
        nav_row.append(InlineKeyboardButton(f"⬅️ {current_idx}-qism", callback_data=f"uwatch_{prev_part.movie_id}"))

    nav_row.append(InlineKeyboardButton("📋 Qismlar", callback_data=f"umovie_{parent_id}"))

    if current_idx < len(all_parts) - 1:
        next_part = all_parts[current_idx + 1]
        nav_row.append(InlineKeyboardButton(f"➡️ {current_idx + 2}-qism", callback_data=f"uwatch_{next_part.movie_id}"))

    return [nav_row]


async def build_movie_card(movie: Movie, *, user, user_id: int, bot_username: str):
    """Bitta (qismsiz) kino uchun (caption, reply_markup) qaytaradi.

    Tugmalar: Baholash (agar baholamagan bo'lsa), Tahrirlash (admin),
    Ulashish (kod bor bo'lsa) va qism-navigatsiya.
    """
    caption = await movie_caption(movie)

    btns = []
    if not await Rating.exists(user=user, movie=movie):
        btns.append([InlineKeyboardButton("⭐ Baholash", callback_data=f"rate_movie_{movie.movie_id}")])

    if is_privileged(user, user_id):
        btns.append([InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_movie_{movie.movie_id}")])

    if movie.movie_code:
        btns.append([_share_button(movie, bot_username)])

    btns.extend(await _part_nav_buttons(movie))

    return caption, (InlineKeyboardMarkup(btns) if btns else None)


def build_parts_list_card(movie: Movie, child_parts: list[Movie]):
    """Qismli kino uchun (text, reply_markup) — qism tanlash ro'yxati."""
    all_parts = []
    if movie.file_id:
        all_parts.append((movie, "1-qism"))
    for part in child_parts:
        all_parts.append((part, f"{part.part_number}-qism"))

    text = (
        f"🎬 <b>{escape(movie.movie_name)}</b>\n\n"
        f"📀 <b>Qismlar soni:</b> {len(all_parts)} ta\n\n"
        f"👇 Qaysi qismni ko'rmoqchisiz?"
    )

    rows, row = [], []
    for part_movie, label in all_parts:
        row.append(InlineKeyboardButton(f"▶️ {label}", callback_data=f"uwatch_{part_movie.movie_id}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    return text, InlineKeyboardMarkup(rows)
