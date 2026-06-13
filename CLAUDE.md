# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Telegram movie bot ("KinoBot") built with `python-telegram-bot` v22 (async). Users browse/search a catalog of movies by name, genre, year, and rating, watch them inline, rate them, and get AI recommendations. Admins/managers manage the catalog (movies, genres, countries, channels, managers), broadcast messages, and view statistics. The UI language is Uzbek; code comments are mostly Uzbek.

## Running

The system runs as **two separate processes** that communicate over a Redis queue:

```bash
python main.py     # the bot: polls Telegram, handles updates, enqueues outbound messages
python worker.py   # the worker: drains the Redis queue and actually sends messages to Telegram
```

Both must run for the bot to deliver any outbound message (see Architecture). Start infrastructure first:

```bash
docker-compose up -d        # Redis (localhost:6379) + Postgres
```

Dependencies: `pip install -r requirements.txt` (includes `APScheduler` for the JobQueue). Requires a `.env` (loaded by `utils/settings.py`) with: `BOT_TOKEN`, `ADMIN_ID`, `MANAGER_ID`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT`, and optionally `REDIS_URL` (default `redis://localhost`). `settings.py` validates the required vars at import and raises `ConfigError` with a clear message if any are missing. There is no test suite or linter configured.

## Database migrations (aerich + Tortoise ORM)

`pyproject.toml` points aerich at `database.TORTOISE_ORM` with migrations in `./migrations`.

```bash
aerich migrate --name <desc>   # generate a migration after changing models
aerich upgrade                 # apply migrations
```

DB connects via `psycopg://` (Postgres). `init_db.py` builds `TORTOISE_ORM` from `DATABASE_URL` and `post_init()` runs `Tortoise.init`, creates the `pg_trgm` GIN index on `movie_name` (idempotent `ensure_search_index()`, which speeds up the `icontains` searches and degrades gracefully without the privilege), and registers bot commands on startup.

## Architecture

### Redis send-queue / worker indirection (most important to understand)

`utils/redis_manager.py` **monkey-patches** `Bot`/`ExtBot` methods (`send_message`, `send_video`, `edit_message_text`, `edit_message_caption`, `edit_message_reply_markup`, `delete_message`). `apply_redis_patch()` is called at the top of `main.py` *before* the Application is built.

Consequences when working in handlers/callbacks:
- Calling `await update.message.reply_text(...)`, `context.bot.send_message(...)`, etc. does **not** send immediately — it serializes the call and `rpush`es it onto the `bot_queue` Redis list. `worker.py` (`run_worker`) `blpop`s and invokes the *original* method. **If the worker isn't running, nothing is delivered.**
- Patched send methods return `None`, not a `Message`. Do not rely on the return value (e.g. to capture `message_id`) for queued sends.
- To bypass the queue and send synchronously (and get a real return value), pass `direct=True` to `send_message`/`send_video`.
- Only JSON-serializable kwargs survive: `clean_kwargs()` drops `DefaultValue` sentinels, converts enums via `.value`, and turns `reply_markup` into a dict. Passing non-trivial objects through these calls will silently drop them.
- The worker centralizes error handling: `BadRequest "message is not modified"` is swallowed; a failed `send_video` sends the user a friendly fallback and notifies `ADMIN_ID`/`MANAGER_ID` with the parsed movie name/code; worker-level exceptions are reported to `ADMIN_ID`. It also paces sends (`SEND_INTERVAL`) and, on `RetryAfter` (flood-limit), sleeps and re-queues the message to the front of the list. `REDIS_URL` comes from settings.

### Handler registration

`main.py` is the single wiring point. All handlers/callbacks/admin modules are star-imported via package `__init__.py` files (`handlers/`, `callbacks/`, `admins/`). Routing patterns:
- Reply-keyboard buttons are matched by emoji `filters.Regex(...)` text, gated by `filters.ChatType.PRIVATE`.
- `CallbackQueryHandler`s are split by `callback_data` prefix (`movie_`, `genre_`, `country_`, `manager_`, `channel_`, `stats_`, and a combined user pattern `ugenre_|uyear_|upage_|umovie_|...`). When adding a new callback button, register its prefix here.
- Multi-step flows use `ConversationHandler` (e.g. `add_movie_conf_handler`, `edit_movie_handler`, `broadcast_conv_handler`).

### Directory roles

- `handlers/` — user-facing commands & message handlers (start, search, history, top, inline query, AI assistant, error handler).
- `callbacks/` — inline-button callback query handlers, split by domain.
- `admins/` — admin/manager features: add/edit movie conversations, genres, countries, channels, managers, broadcast, statistics, file checker.
- `database/` — Tortoise models (`Movie`, `Genre`, `Countries`, `Channels`, `User`, `UserMovieHistory`, `Rating`) + `init_db`. Package `__init__` re-exports all models; Tortoise's app config registers models under `"database"`.
- `utils/` — `settings.py` (env/config + validation, `PAGE_SIZE=40`, `MOVIES_PER_PAGE=15`, `REDIS_URL`), `redis_manager.py`, `movie_card.py`, `decorators.py`, `pagination.py`, keyboard builders (`admin_btns`, `user_btns`), `checker.py` (subscription checks), `error_notificator.py`.
- `utils/movie_card.py` — **the single source of truth for rendering a movie**. `build_movie_card(movie, *, user, user_id, bot_username)` returns `(caption_html, reply_markup)` (rating/edit/share/part-nav buttons); `build_parts_list_card(movie, child_parts)` returns the part-picker; `movie_caption`, `get_child_parts`, `is_privileged`. The user-facing movie card was previously copy-pasted across `user_callbacks.py`, `common_handler.py`, and `inline_query_handler.py` — always render via this helper, never re-inline it. `is_privileged()` uses `user.user_type == USER_TYPE.ADMIN` (note: `str(user.user_type) == 'admin'` is broken on Python 3.11+).
- `services/ai_assistant.py` — Gemini (`google-genai`) wrapper with in-memory cache, rate limiting, quota-retry decorator, and DuckDuckGo web-search enrichment. Exposes a module-level singleton `ai_assistant`. **It is synchronous** (`requests`, `time.sleep`, blocking SDK) — callers MUST offload it with `await asyncio.to_thread(...)` (see `handlers/common_handler.py`) or it blocks the whole event loop.
- `admins/backup_handler.py` — DB backup: `create_backup()` tries host `pg_dump` → `pg_dump` inside the Postgres container (if `DB_DOCKER_CONTAINER` is set) → a generic JSON dump of all public tables via raw SQL, in that order (all gzipped). `send_backup()` sends it as a **document** (`send_document` is not Redis-patched, so it bypasses the worker; status messages use `direct=True` to keep ordering). The "💾 Zaxira nusxa" reply button (`backup_handler`, super-admin only — `ADMIN_ID`/`MANAGER_ID`) and the `daily_backup_job` JobQueue task (registered in `main.py` via `run_daily` at 03:00 Asia/Tashkent, sends to `ADMIN_ID`) both use it. **Prefer the SQL format** — it restores with one command; the JSON fallback is data-only (no schema) and needs `scripts/restore_backup.py`. To force SQL on a host without `pg_dump`, set `PG_DUMP_PATH` or `DB_DOCKER_CONTAINER=my_bot_postgres` in `.env`.
- `scripts/restore_backup.py` — standalone restore tool (reads `DB_*` from `.env`). `.sql.gz`/`.sql` → piped to `psql` (or `docker exec ... psql`). `.json.gz`/`.json` → requires the schema to already exist (`aerich upgrade` first), then `--yes` to TRUNCATE + re-insert all tables with FK checks disabled (`session_replication_role=replica`), JSONB values re-wrapped, and sequences reset via `setval(GREATEST(MAX, 1))`. Both paths are tested against the live schema.
- `migrations/models/` — aerich migration history.

### Access control & gating decorators (`utils/decorators.py`)

- `@admin_required` — allows users whose DB `user_type == 'admin'` OR whose id is `ADMIN_ID`/`MANAGER_ID`; raises `PermissionDenied` otherwise.
- `@channel_subscription_required` — forces subscription to all `Channels` before proceeding, otherwise shows join buttons + a "check" button.
- `@user_registered_required` — requires the user to exist in DB (have pressed `/start`).

### Models of note

- `Movie` supports self-referencing parts via `parent_movie`/`part_number`, has unique `movie_code`, and stores aggregate rating as `total_rating_sum`/`rating_count` with an `average_rating` property (don't recompute from `Rating` rows on read paths). `movie_quality`/`movie_language` are `CharEnumField`s (`QualityEnum`, `LanguageEnum`).
- `User.user_type` is the `USER_TYPE` enum used by `@admin_required`.
