"""Link asosidagi serial (kanal-havolali) — admin CRUD.

Ba'zi seriallar botga video sifatida yuklanmaydi, ular allaqachon boshqa
kanalda joylashgan bo'ladi. Bu modul shunday seriallar uchun alohida oqim
taqdim etadi: kod/rasm(ixtiyoriy)/nom/yil/tavsif so'raladi, so'ng har bir
qism uchun kanal postiga havola bittalab yig'iladi (tugatishdan oldin
istalgan qismni tahrirlash imkoni bilan). Render qatlami
``utils/movie_card.py``dagi ``build_linked_series_card``/``send_linked_series_card``
orqali — bu yerda faqat CRUD (Movie satrlarini yaratish/tahrirlash/o'chirish).
"""
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler,
    CommandHandler, filters,
)

from database import Movie
from utils.decorators import admin_required
from utils import get_linked_series_page
from utils.admin_btns import get_admin_keyboard


# --- Qo'shish oqimi holatlari ---
LS_CODE, LS_POSTER, LS_NAME, LS_YEAR, LS_DESC, LS_CONFIRM_ROOT, \
LS_COLLECT_LINKS, LS_SELECT_LINK_EDIT, LS_RECEIVE_LINK_EDIT = range(9)

# --- Ro'yxat/Tahrirlash/O'chirish oqimi holatlari ---
LS_EDIT_MENU, LS_EDIT_WAITING_INPUT, LS_EDIT_WAITING_POSTER, LS_EDIT_WAITING_LINK = range(9, 13)

LS_EDIT_MENU_PATTERN = (
    r"^ls:(edit_name_\d+|edit_year_\d+|edit_code_\d+|edit_desc_\d+|edit_poster_\d+|"
    r"parts_\d+|add_link_\d+|edit_link_\d+|delete_link_\d+|"
    r"delete_confirm_\d+|delete_yes_\d+|delete_no_\d+|"
    r"back_to_view_\d+|back_to_list)$"
)


def _is_url(text: str) -> bool:
    return text.strip().startswith(("http://", "https://"))


# ============================== RO'YXAT ==============================

def _linked_series_keyboard(movies, page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    buttons = []
    for movie in movies:
        buttons.append([InlineKeyboardButton(
            text=f"{movie.movie_name} → {movie.movie_code or '-'}",
            callback_data=f"ls:view_{movie.movie_id}"
        )])

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"ls:list_page_{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton("➡️ Keyingisi", callback_data=f"ls:list_page_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("➕ Link serial qo'shish", callback_data="ls:add")])
    return InlineKeyboardMarkup(buttons)


@admin_required
async def ls_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 1
    context.user_data["LS_PAGE"] = page
    data = await get_linked_series_page(page)
    keyboard = _linked_series_keyboard(data["movies"], data["page"], data["has_prev"], data["has_next"])
    await update.message.reply_text("🔗 <b>Link seriallar ro'yxati</b>", reply_markup=keyboard, parse_mode="HTML")


async def ls_list_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.removeprefix("ls:list_page_"))
    context.user_data["LS_PAGE"] = page
    data = await get_linked_series_page(page)
    keyboard = _linked_series_keyboard(data["movies"], data["page"], data["has_prev"], data["has_next"])
    await query.edit_message_text("🔗 <b>Link seriallar ro'yxati</b>", reply_markup=keyboard, parse_mode="HTML")


# ============================== QO'SHISH ==============================

async def _update_anchor(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, reply_markup=None) -> None:
    """Bitta "anchor" xabarni oqim davomida tahrirlab boradi (chatni tozalab turish uchun)."""
    anchor_id = context.user_data.get('ls_anchor_msg_id')
    if anchor_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=anchor_id, text=text,
                reply_markup=reply_markup, parse_mode="HTML",
            )
            return
        except Exception:
            pass
    msg = await context.bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML", direct=True)
    if msg:
        context.user_data['ls_anchor_msg_id'] = msg.message_id


def _collect_links_keyboard(has_parts: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_parts:
        rows.append([InlineKeyboardButton("✏️ Qismni tahrirlash", callback_data="ls:choose_edit")])
    rows.append([InlineKeyboardButton("✅ Tugatish", callback_data="ls:finish")])
    return InlineKeyboardMarkup(rows)


async def _update_collect_msg(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    root_id = context.user_data.get('ls_root_id')
    has_parts = await Movie.filter(parent_movie_id=root_id).exists()
    keyboard = _collect_links_keyboard(has_parts=has_parts)

    msg_id = context.user_data.get('ls_collect_msg_id')
    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=text,
                reply_markup=keyboard, parse_mode="HTML",
            )
            return
        except Exception:
            pass
    msg = await context.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML", direct=True)
    if msg:
        context.user_data['ls_collect_msg_id'] = msg.message_id


@admin_required
async def ls_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data['ls_anchor_msg_id'] = query.message.message_id
    await query.edit_message_text("✍️ <b>Kod kiriting:</b>", parse_mode="HTML")
    return LS_CODE


async def ls_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_CODE
    code = update.message.text.strip()
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass

    if not code.isdecimal():
        await _update_anchor(context, chat_id, "⚠️ <b>Kod raqam bo'lishi kerak. Qaytadan kiriting:</b>")
        return LS_CODE

    existing = await Movie.get_or_none(movie_code=int(code))
    if existing:
        await _update_anchor(
            context, chat_id,
            f"⚠️ <b>Bu kod band!</b>\n\n<b>{escape(existing.movie_name)}</b> kinosiga biriktirilgan.\n\nBoshqa kod kiriting:",
        )
        return LS_CODE

    context.user_data['ls_code'] = int(code)
    await _update_anchor(
        context, chat_id,
        "🖼 <b>Muqova rasmini yuboring</b>\n\n(Ixtiyoriy — o'tkazib yuborish uchun <code>.</code> yuboring)",
    )
    return LS_POSTER


async def ls_receive_poster_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return LS_POSTER
    photo = update.message.photo[-1].file_id if update.message.photo else (
        update.message.document.file_id if update.message.document else None
    )
    if not photo:
        return LS_POSTER

    context.user_data['ls_poster'] = photo
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass
    await _update_anchor(context, chat_id, "🎬 <b>Nomini kiriting:</b>")
    return LS_NAME


async def ls_receive_poster_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_POSTER
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass

    if text != ".":
        await _update_anchor(context, chat_id, "⚠️ <b>Rasm yuboring yoki o'tkazib yuborish uchun <code>.</code> yuboring:</b>")
        return LS_POSTER

    context.user_data['ls_poster'] = None
    await _update_anchor(context, chat_id, "🎬 <b>Nomini kiriting:</b>")
    return LS_NAME


async def ls_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_NAME
    context.user_data['ls_name'] = update.message.text.strip()
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass
    await _update_anchor(context, chat_id, "📅 <b>Yilni kiriting</b>\n\n(Masalan: 2024, o'tkazib yuborish uchun <code>.</code>)")
    return LS_YEAR


async def ls_receive_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_YEAR
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass

    if not text.isdecimal() and text != ".":
        await _update_anchor(context, chat_id, "⚠️ <b>Yil faqat son yoki <code>.</code> bo'lishi kerak. Qaytadan kiriting:</b>")
        return LS_YEAR

    context.user_data['ls_year'] = int(text) if text != "." else None
    await _update_anchor(context, chat_id, "📝 <b>Tavsif kiriting</b>\n\n(O'tkazib yuborish uchun <code>.</code>)")
    return LS_DESC


async def ls_receive_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_DESC
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass

    context.user_data['ls_desc'] = None if text == "." else text

    poster = context.user_data.get('ls_poster')
    name = context.user_data.get('ls_name')
    year = context.user_data.get('ls_year')
    desc = context.user_data.get('ls_desc')

    preview = (
        f"🔗 <b>Link serial ma'lumotlarini tekshiring</b>\n\n"
        f"🏷 <b>Nomi:</b> {escape(str(name))}\n"
        f"🔢 <b>Kodi:</b> {context.user_data.get('ls_code')}\n"
        f"📅 <b>Yili:</b> {year or 'Koʻrsatilmagan'}\n"
        f"📝 <b>Tavsif:</b> {escape(desc) if desc else 'Koʻrsatilmagan'}\n\n"
        f"Tasdiqlaysizmi?"
    )
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data="ls:confirm_root"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data="ls:cancel_root"),
    ]])

    anchor_id = context.user_data.get('ls_anchor_msg_id')
    if anchor_id:
        try:
            await context.bot.delete_message(chat_id, anchor_id)
        except Exception:
            pass

    if poster:
        msg = await context.bot.send_photo(chat_id, poster, caption=preview, reply_markup=btns, parse_mode="HTML", direct=True)
    else:
        msg = await context.bot.send_message(chat_id, preview, reply_markup=btns, parse_mode="HTML", direct=True)
    if msg:
        context.user_data['ls_confirm_msg_id'] = msg.message_id
    return LS_CONFIRM_ROOT


async def ls_confirm_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if query.data == "ls:cancel_root":
        if query.message.caption is not None:
            await query.edit_message_caption("❌ <b>Bekor qilindi.</b>", parse_mode="HTML", reply_markup=None)
        else:
            await query.edit_message_text("❌ <b>Bekor qilindi.</b>", parse_mode="HTML", reply_markup=None)
        await context.bot.send_message(chat_id, "Admin panel:", reply_markup=get_admin_keyboard(chat_id))
        context.user_data.clear()
        return ConversationHandler.END

    root = await Movie.create(
        movie_code=context.user_data.get('ls_code'),
        movie_name=context.user_data.get('ls_name'),
        movie_year=context.user_data.get('ls_year'),
        movie_description=context.user_data.get('ls_desc'),
        poster_file_id=context.user_data.get('ls_poster'),
        is_linked_series=True,
        file_id=None,
    )

    if query.message.caption is not None:
        await query.edit_message_caption(f"✅ <b>{escape(root.movie_name)}</b> yaratildi.", parse_mode="HTML", reply_markup=None)
    else:
        await query.edit_message_text(f"✅ <b>{escape(root.movie_name)}</b> yaratildi.", parse_mode="HTML", reply_markup=None)

    context.user_data.clear()
    context.user_data['ls_root_id'] = root.movie_id

    msg = await context.bot.send_message(
        chat_id, "🔗 <b>1-qism havolasini yuboring:</b>",
        reply_markup=_collect_links_keyboard(has_parts=False), parse_mode="HTML", direct=True,
    )
    if msg:
        context.user_data['ls_collect_msg_id'] = msg.message_id
    return LS_COLLECT_LINKS


async def ls_receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_COLLECT_LINKS
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()
    except Exception:
        pass

    if not _is_url(text):
        await _update_collect_msg(context, chat_id, "⚠️ <b>Bu havolaga o'xshamayapti (http/https bilan boshlanishi kerak). Qaytadan yuboring:</b>")
        return LS_COLLECT_LINKS

    root_id = context.user_data.get('ls_root_id')
    root = await Movie.get_or_none(movie_id=root_id)
    next_num = await Movie.filter(parent_movie_id=root_id).count() + 1

    await Movie.create(
        parent_movie_id=root_id,
        part_number=next_num,
        watch_url=text,
        movie_name=f"{root.movie_name} - {next_num}-qism" if root else f"{next_num}-qism",
    )

    await _update_collect_msg(
        context, chat_id,
        f"✅ <b>{next_num}-qism qo'shildi.</b>\n\nYana havola yuboring, yoki tugatgan bo'lsangiz tugmalardan foydalaning.",
    )
    return LS_COLLECT_LINKS


async def ls_choose_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    root_id = context.user_data.get('ls_root_id')
    parts = await Movie.filter(parent_movie_id=root_id).order_by('part_number')

    rows, row = [], []
    for p in parts:
        row.append(InlineKeyboardButton(f"▶️ {p.part_number}", callback_data=f"ls:pick_edit_{p.movie_id}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Ortga", callback_data="ls:back_to_collect")])

    await query.edit_message_text("✏️ <b>Qaysi qismni tahrirlaysiz?</b>", reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
    return LS_SELECT_LINK_EDIT


async def ls_pick_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    part_id = int(query.data.removeprefix("ls:pick_edit_"))
    part = await Movie.get_or_none(movie_id=part_id)
    if not part:
        await query.answer("⚠️ Qism topilmadi.", show_alert=True)
        return LS_SELECT_LINK_EDIT

    context.user_data['ls_editing_part_id'] = part_id
    await query.edit_message_text(f"✏️ <b>{part.part_number}-qism uchun yangi havolani yuboring:</b>", parse_mode="HTML")
    return LS_RECEIVE_LINK_EDIT


async def ls_back_to_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    root_id = context.user_data.get('ls_root_id')
    has_parts = await Movie.filter(parent_movie_id=root_id).exists()
    await query.edit_message_text(
        "🔗 <b>Yana havola yuboring, yoki tugatgan bo'lsangiz tugmalardan foydalaning.</b>",
        reply_markup=_collect_links_keyboard(has_parts=has_parts),
        parse_mode="HTML",
    )
    context.user_data['ls_collect_msg_id'] = query.message.message_id
    return LS_COLLECT_LINKS


async def ls_receive_link_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_RECEIVE_LINK_EDIT
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    part_id = context.user_data.get('ls_editing_part_id')
    try:
        await update.message.delete()
    except Exception:
        pass

    if not _is_url(text):
        await context.bot.send_message(chat_id, "⚠️ <b>Bu havolaga o'xshamayapti. Qaytadan yuboring:</b>", parse_mode="HTML")
        return LS_RECEIVE_LINK_EDIT

    part = await Movie.get_or_none(movie_id=part_id)
    if part:
        part.watch_url = text
        await part.save()
        confirm_text = f"✅ <b>{part.part_number}-qism havolasi yangilandi.</b>"
    else:
        confirm_text = "⚠️ Qism topilmadi."

    context.user_data.pop('ls_editing_part_id', None)
    await _update_collect_msg(
        context, chat_id,
        confirm_text + "\n\nYana havola yuboring, yoki tugatgan bo'lsangiz tugmalardan foydalaning.",
    )
    return LS_COLLECT_LINKS


async def ls_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    root_id = context.user_data.get('ls_root_id')
    root = await Movie.get_or_none(movie_id=root_id)
    count = await Movie.filter(parent_movie_id=root_id).count()

    name = escape(root.movie_name) if root else "Serial"
    await query.edit_message_text(f"🎉 <b>{name}</b> — {count} ta qism bilan qo'shildi!", parse_mode="HTML")
    await context.bot.send_message(update.effective_chat.id, "Admin panel:", reply_markup=get_admin_keyboard(update.effective_chat.id))

    context.user_data.clear()
    return ConversationHandler.END


async def ls_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "❌ <b>Bekor qilindi.</b> (Hozirgacha qo'shilgan ma'lumotlar saqlanib qoladi.)",
            reply_markup=get_admin_keyboard(update.effective_chat.id),
            parse_mode="HTML",
        )
    context.user_data.clear()
    return ConversationHandler.END


async def ls_add_start_from_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    from handlers.start_handler import start_handler
    await start_handler(update, context)
    return ConversationHandler.END


# ============================== TAHRIRLASH / O'CHIRISH ==============================

async def _ls_edit_message(query, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if query.message.caption is not None:
        await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")


@admin_required
async def ls_view(update: Update, context: ContextTypes.DEFAULT_TYPE, movie_id: int | None = None):
    query = update.callback_query
    if query:
        await query.answer()
        if movie_id is None:
            movie_id = int(query.data.removeprefix("ls:view_"))
        context.user_data['ls_edit_id'] = movie_id

    movie = await Movie.get_or_none(movie_id=movie_id, is_linked_series=True)
    if not movie:
        if query:
            await _ls_edit_message(query, "⚠️ Serial topilmadi.")
        return ConversationHandler.END

    parts_count = await Movie.filter(parent_movie_id=movie_id).count()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 Nomi: {movie.movie_name[:20]}", callback_data=f"ls:edit_name_{movie_id}")],
        [InlineKeyboardButton(f"📅 Yil: {movie.movie_year or '-'}", callback_data=f"ls:edit_year_{movie_id}"),
         InlineKeyboardButton(f"📥 Kod: {movie.movie_code or '-'}", callback_data=f"ls:edit_code_{movie_id}")],
        [InlineKeyboardButton("📝 Tavsifni o'zgartirish", callback_data=f"ls:edit_desc_{movie_id}")],
        [InlineKeyboardButton("🖼 Rasmni almashtirish", callback_data=f"ls:edit_poster_{movie_id}")],
        [InlineKeyboardButton(f"🔗 Qismlar: {parts_count} ta", callback_data=f"ls:parts_{movie_id}")],
        [InlineKeyboardButton("🗑 O'chirish", callback_data=f"ls:delete_confirm_{movie_id}")],
        [InlineKeyboardButton("🔙 Ortga", callback_data="ls:back_to_list")],
    ])
    text = f"🔗 <b>Link serial tahrirlash:</b>\n\n🎬 {escape(movie.movie_name)}\n\nO'zgartirmoqchi bo'lgan ma'lumotni tanlang:"

    if query:
        await _ls_edit_message(query, text, keyboard)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=keyboard, parse_mode="HTML")
    return LS_EDIT_MENU


async def ls_show_parts(update: Update, context: ContextTypes.DEFAULT_TYPE, movie_id: int):
    query = update.callback_query
    parts = await Movie.filter(parent_movie_id=movie_id).order_by('part_number')

    btns = []
    for p in parts:
        play_btn = (
            InlineKeyboardButton(f"▶️ {p.part_number}-qism", url=p.watch_url)
            if p.watch_url else
            InlineKeyboardButton(f"▶️ {p.part_number}-qism", callback_data="noop")
        )
        btns.append([
            play_btn,
            InlineKeyboardButton("✏️", callback_data=f"ls:edit_link_{p.movie_id}"),
            InlineKeyboardButton("🗑", callback_data=f"ls:delete_link_{p.movie_id}"),
        ])
    btns.append([InlineKeyboardButton("➕ Havola qo'shish", callback_data=f"ls:add_link_{movie_id}")])
    btns.append([InlineKeyboardButton("🔙 Ortga", callback_data=f"ls:back_to_view_{movie_id}")])

    text = f"🔗 <b>Qismlar boshqaruvi</b>\n\nJami: {len(parts)} ta qism"
    await _ls_edit_message(query, text, InlineKeyboardMarkup(btns))
    return LS_EDIT_MENU


async def ls_edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "ls:back_to_list":
        await query.delete_message()
        page = context.user_data.get("LS_PAGE", 1)
        ls_data = await get_linked_series_page(page)
        keyboard = _linked_series_keyboard(ls_data["movies"], ls_data["page"], ls_data["has_prev"], ls_data["has_next"])
        await context.bot.send_message(update.effective_chat.id, "🔗 <b>Link seriallar ro'yxati</b>", reply_markup=keyboard, parse_mode="HTML")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("ls:delete_confirm_"):
        movie_id = int(data.removeprefix("ls:delete_confirm_"))
        parts_count = await Movie.filter(parent_movie_id=movie_id).count()
        warning = f"\n\n⚠️ <b>Bu serialning {parts_count} ta qismi bor — birga o'chadi!</b>" if parts_count else ""
        btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 HA, O'CHIRISH", callback_data=f"ls:delete_yes_{movie_id}")],
            [InlineKeyboardButton("🔙 YO'Q, QAYTISH", callback_data=f"ls:delete_no_{movie_id}")],
        ])
        await _ls_edit_message(query, f"🗑 <b>Rostdan ham o'chirmoqchimisiz?</b>{warning}", btns)
        return LS_EDIT_MENU

    if data.startswith("ls:delete_yes_"):
        movie_id = int(data.removeprefix("ls:delete_yes_"))
        movie = await Movie.get_or_none(movie_id=movie_id)
        if movie:
            await movie.delete()
        await _ls_edit_message(query, "🗑 <b>Link serial muvaffaqiyatli o'chirildi!</b>", None)
        await context.bot.send_message(update.effective_chat.id, "Admin panel:", reply_markup=get_admin_keyboard(update.effective_chat.id))
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("ls:delete_no_"):
        movie_id = int(data.removeprefix("ls:delete_no_"))
        return await ls_view(update, context, movie_id=movie_id)

    if data.startswith("ls:edit_poster_"):
        movie_id = int(data.removeprefix("ls:edit_poster_"))
        context.user_data['ls_edit_id'] = movie_id
        await _ls_edit_message(query, "🖼 <b>Yangi rasm yuboring:</b>\n\n(Bekor qilish uchun /cancel)")
        return LS_EDIT_WAITING_POSTER

    if data.startswith("ls:parts_"):
        movie_id = int(data.removeprefix("ls:parts_"))
        context.user_data['ls_edit_id'] = movie_id
        return await ls_show_parts(update, context, movie_id)

    if data.startswith("ls:add_link_"):
        movie_id = int(data.removeprefix("ls:add_link_"))
        context.user_data['ls_edit_id'] = movie_id
        context.user_data.pop('ls_editing_part_id', None)
        await _ls_edit_message(query, "🔗 <b>Yangi qism uchun havolani yuboring:</b>\n\n(Bekor qilish uchun /cancel)")
        return LS_EDIT_WAITING_LINK

    if data.startswith("ls:edit_link_"):
        part_id = int(data.removeprefix("ls:edit_link_"))
        part = await Movie.get_or_none(movie_id=part_id)
        if not part:
            await query.answer("⚠️ Qism topilmadi.", show_alert=True)
            return LS_EDIT_MENU
        context.user_data['ls_editing_part_id'] = part_id
        await _ls_edit_message(query, f"✏️ <b>{part.part_number}-qism uchun yangi havolani yuboring:</b>\n\n(Bekor qilish uchun /cancel)")
        return LS_EDIT_WAITING_LINK

    if data.startswith("ls:delete_link_"):
        part_id = int(data.removeprefix("ls:delete_link_"))
        part = await Movie.get_or_none(movie_id=part_id)
        movie_id = context.user_data.get('ls_edit_id')
        if part and part.parent_movie_id:
            await part.delete()
            await query.answer("🗑 Qism o'chirildi!", show_alert=True)
        else:
            await query.answer("⚠️ Qism topilmadi.", show_alert=True)
        return await ls_show_parts(update, context, movie_id)

    if data.startswith("ls:back_to_view_"):
        movie_id = int(data.removeprefix("ls:back_to_view_"))
        return await ls_view(update, context, movie_id=movie_id)

    field_map = {
        "ls:edit_name_": ("Nomi", "movie_name"),
        "ls:edit_year_": ("Yili", "movie_year"),
        "ls:edit_code_": ("Kodi (dublikat bo'lmasligi kerak)", "movie_code"),
        "ls:edit_desc_": ("Tavsifi", "movie_description"),
    }
    for prefix, (label, field) in field_map.items():
        if data.startswith(prefix):
            movie_id = int(data.removeprefix(prefix))
            context.user_data['ls_edit_id'] = movie_id
            context.user_data['ls_edit_field'] = field
            await _ls_edit_message(query, f"✍️ <b>Yangi {label}ni kiriting:</b>\n\n(Bekor qilish uchun /cancel)")
            return LS_EDIT_WAITING_INPUT

    return LS_EDIT_MENU


async def ls_receive_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_EDIT_WAITING_INPUT
    new_value = update.message.text.strip()
    movie_id = context.user_data.get('ls_edit_id')
    field = context.user_data.get('ls_edit_field')
    chat_id = update.effective_chat.id

    try:
        await update.message.delete()
    except Exception:
        pass

    movie = await Movie.get_or_none(movie_id=movie_id)
    if not movie:
        await context.bot.send_message(chat_id, "⚠️ Serial topilmadi.")
        return ConversationHandler.END

    if field == "movie_year":
        if not new_value.isdecimal():
            await context.bot.send_message(chat_id, "⚠️ Yil raqam bo'lishi kerak! Qaytadan kiriting:")
            return LS_EDIT_WAITING_INPUT
        movie.movie_year = int(new_value)
    elif field == "movie_code":
        if not new_value.isdecimal():
            await context.bot.send_message(chat_id, "⚠️ Kod raqam bo'lishi kerak! Qaytadan kiriting:")
            return LS_EDIT_WAITING_INPUT
        existing = await Movie.get_or_none(movie_code=int(new_value))
        if existing and existing.movie_id != movie_id:
            await context.bot.send_message(chat_id, "⚠️ Bu kod band! Qaytadan kiriting:")
            return LS_EDIT_WAITING_INPUT
        movie.movie_code = int(new_value)
    elif field == "movie_name":
        movie.movie_name = new_value
    elif field == "movie_description":
        movie.movie_description = new_value

    await movie.save()
    return await ls_view(update, context, movie_id=movie_id)


async def ls_receive_edit_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return LS_EDIT_WAITING_POSTER
    photo = update.message.photo[-1].file_id if update.message.photo else (
        update.message.document.file_id if update.message.document else None
    )
    if not photo:
        await update.message.reply_text("⚠️ Iltimos, rasm yuboring.")
        return LS_EDIT_WAITING_POSTER

    movie_id = context.user_data.get('ls_edit_id')
    try:
        await update.message.delete()
    except Exception:
        pass

    movie = await Movie.get_or_none(movie_id=movie_id)
    if not movie:
        await context.bot.send_message(update.effective_chat.id, "⚠️ Serial topilmadi.")
        return ConversationHandler.END

    movie.poster_file_id = photo
    await movie.save()
    return await ls_view(update, context, movie_id=movie_id)


async def ls_receive_edit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return LS_EDIT_WAITING_LINK
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    movie_id = context.user_data.get('ls_edit_id')
    part_id = context.user_data.get('ls_editing_part_id')

    try:
        await update.message.delete()
    except Exception:
        pass

    if not _is_url(text):
        await context.bot.send_message(chat_id, "⚠️ Bu havolaga o'xshamayapti. Qaytadan yuboring:")
        return LS_EDIT_WAITING_LINK

    if part_id:
        part = await Movie.get_or_none(movie_id=part_id)
        if part:
            part.watch_url = text
            await part.save()
    else:
        root = await Movie.get_or_none(movie_id=movie_id)
        next_num = await Movie.filter(parent_movie_id=movie_id).count() + 1
        await Movie.create(
            parent_movie_id=movie_id,
            part_number=next_num,
            watch_url=text,
            movie_name=f"{root.movie_name} - {next_num}-qism" if root else f"{next_num}-qism",
        )

    context.user_data.pop('ls_editing_part_id', None)
    return await ls_view(update, context, movie_id=movie_id)


async def ls_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ Tahrirlash bekor qilindi.", reply_markup=get_admin_keyboard(update.effective_chat.id))
    context.user_data.clear()
    return ConversationHandler.END


linked_series_add_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(ls_add_entry, pattern=r"^ls:add$")],
    states={
        LS_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_code)],
        LS_POSTER: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, ls_receive_poster_photo),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_poster_text),
        ],
        LS_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_name)],
        LS_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_year)],
        LS_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_desc)],
        LS_CONFIRM_ROOT: [CallbackQueryHandler(ls_confirm_root, pattern=r"^ls:(confirm_root|cancel_root)$")],
        LS_COLLECT_LINKS: [
            CallbackQueryHandler(ls_choose_edit, pattern=r"^ls:choose_edit$"),
            CallbackQueryHandler(ls_finish, pattern=r"^ls:finish$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_link),
        ],
        LS_SELECT_LINK_EDIT: [
            CallbackQueryHandler(ls_pick_edit, pattern=r"^ls:pick_edit_\d+$"),
            CallbackQueryHandler(ls_back_to_collect, pattern=r"^ls:back_to_collect$"),
        ],
        LS_RECEIVE_LINK_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_link_edit)],
    },
    fallbacks=[
        CommandHandler('cancel', ls_add_cancel),
        CommandHandler('start', ls_add_start_from_conv),
    ],
    per_user=True,
    block=True,
)


linked_series_edit_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(ls_view, pattern=r"^ls:view_\d+$")],
    states={
        LS_EDIT_MENU: [
            CallbackQueryHandler(ls_view, pattern=r"^ls:view_\d+$"),
            CallbackQueryHandler(ls_edit_menu_callback, pattern=LS_EDIT_MENU_PATTERN),
        ],
        LS_EDIT_WAITING_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_edit_value)],
        LS_EDIT_WAITING_POSTER: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, ls_receive_edit_poster)],
        LS_EDIT_WAITING_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ls_receive_edit_link)],
    },
    fallbacks=[CommandHandler('cancel', ls_edit_cancel)],
)
