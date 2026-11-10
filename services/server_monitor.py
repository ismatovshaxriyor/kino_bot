"""Server va AWS kuzatuvi.

- Server: disk, RAM, Postgres, Redis va worker navbati (har 15 daqiqada).
- AWS: Cost Explorer orqali kredit sarfi va qolgan kunlar (har kuni 09:00) — faqat o'qish kaliti bilan.
  Kredit kam qolgan bo'lsa har kuni eslatadi.

Ogohlantirishlar ADMIN_ID ga `direct=True` bilan yuboriladi, shuning uchun Redis/worker
yiqilgan bo'lsa ham yetib boradi. Muammo holati xotirada saqlanadi: bir xil muammo har safar emas,
faqat paydo bo'lganda, REALERT_AFTER dan keyin va tiklanganda xabar qilinadi.
"""

import asyncio
import logging
import shutil
import time
from datetime import date, time as dtime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes
from tortoise import connections

from utils.redis_manager import r, QUEUE_NAME
from utils.settings import (
    ADMIN_ID, MANAGER_ID,
    AWS_MONITOR_ENABLED, AWS_CREDIT_TOTAL_USD, AWS_CREDIT_START, AWS_CREDIT_EXPIRES,
)

logger = logging.getLogger(__name__)

HEALTH_INTERVAL = timedelta(minutes=15)
# Cost Explorer so'rovi pullik (~$0.01) — sutkada bir marta yetarli
AWS_CHECK_TIME = dtime(hour=9, minute=0, tzinfo=ZoneInfo("Asia/Tashkent"))

DISK_WARN_PERCENT = 85
MEM_MIN_AVAILABLE_MB = 150
QUEUE_MAX_LEN = 500
REALERT_AFTER = 6 * 3600          # davom etayotgan muammo haqida qayta eslatish (soniya)

# Kredit "kam qoldi" deb hisoblanadi: shu kundan kam yetsa YOKI qolgan summa boshlang'ichning shu ulushidan kam bo'lsa
CREDIT_LOW_DAYS = 30
CREDIT_LOW_FRACTION = 0.2
CREDIT_URGENT_DAYS = 7            # shundan kam qolsa — 🚨
AWS_CACHE_TTL = 30 * 60           # /aws buyrug'i uchun kesh (soniya)

_active: dict[str, float] = {}    # muammo kaliti -> oxirgi ogohlantirish vaqti
_aws_cache: dict = {"ts": 0.0, "data": None}


# ============================= SERVER =============================

def _disk_percent() -> int:
    u = shutil.disk_usage("/")
    # df kabi: used / (used + avail)
    return round(u.used / (u.used + u.free) * 100)


def _mem_available_mb() -> int | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


async def collect_health() -> tuple[dict, dict[str, str]]:
    """(ko'rsatkichlar, muammolar) qaytaradi. Muammolar: {kalit: matn}."""
    stats: dict = {}
    problems: dict[str, str] = {}

    stats["disk"] = _disk_percent()
    if stats["disk"] >= DISK_WARN_PERCENT:
        problems["server:disk"] = f"Disk {stats['disk']}% to'ldi (chegara {DISK_WARN_PERCENT}%)"

    stats["mem_mb"] = _mem_available_mb()
    if stats["mem_mb"] is not None and stats["mem_mb"] < MEM_MIN_AVAILABLE_MB:
        problems["server:ram"] = f"Bo'sh RAM kam: {stats['mem_mb']} MB (chegara {MEM_MIN_AVAILABLE_MB} MB)"

    try:
        await asyncio.wait_for(connections.get("default").execute_query("SELECT 1"), timeout=10)
        stats["postgres"] = True
    except Exception as e:
        stats["postgres"] = False
        problems["server:postgres"] = f"Postgres javob bermayapti: <code>{escape(str(e)[:150])}</code>"

    try:
        await asyncio.wait_for(r.ping(), timeout=5)
        stats["redis"] = True
        stats["queue"] = await r.llen(QUEUE_NAME)
        if stats["queue"] > QUEUE_MAX_LEN:
            problems["server:queue"] = (
                f"Xabarlar navbati {stats['queue']} ta (chegara {QUEUE_MAX_LEN}) — worker ishlayaptimi?"
            )
    except Exception as e:
        stats["redis"] = False
        stats["queue"] = None
        problems["server:redis"] = f"Redis javob bermayapti: <code>{escape(str(e)[:150])}</code>"

    return stats, problems


def format_health(stats: dict, problems: dict[str, str]) -> str:
    ok = lambda v: "✅" if v else "🔴"
    mem = f"{stats['mem_mb']} MB" if stats.get("mem_mb") is not None else "noma'lum"
    queue = stats["queue"] if stats.get("queue") is not None else "—"
    return (
        "🖥 <b>Server holati</b>\n"
        f"{'🔴' if 'server:disk' in problems else '✅'} Disk: {stats['disk']}%\n"
        f"{'🔴' if 'server:ram' in problems else '✅'} Bo'sh RAM: {mem}\n"
        f"{ok(stats['postgres'])} Postgres\n"
        f"{ok(stats['redis'])} Redis (navbat: {queue})"
    )


# ============================= OGOHLANTIRISH =============================

async def _send(bot, text: str) -> None:
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML", direct=True)
    except Exception as e:
        logger.error("Monitor ogohlantirishini yuborib bo'lmadi: %s", e)


async def _sync_problems(bot, prefix: str, problems: dict[str, str]) -> None:
    """Muammolar holatini oldingisi bilan solishtirib, faqat o'zgarganda xabar yuborish."""
    now = time.monotonic()
    for key, text in problems.items():
        last = _active.get(key)
        if last is None or now - last >= REALERT_AFTER:
            _active[key] = now
            suffix = "" if last is None else "\n<i>(hali ham davom etyapti)</i>"
            await _send(bot, f"🚨 {text}{suffix}")
    for key in [k for k in _active if k.startswith(prefix) and k not in problems]:
        del _active[key]
        await _send(bot, f"✅ Tiklandi: <code>{escape(key.split(':', 1)[1])}</code>")


async def health_check_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue: server holatini tekshirish."""
    try:
        _, problems = await collect_health()
    except Exception as e:
        logger.exception("Server holatini tekshirishda xato: %s", e)
        return
    await _sync_problems(context.bot, "server:", problems)


# ============================= AWS =============================

def _ce_costs_sync() -> dict:
    """Cost Explorer'dan kredit sarfi va oxirgi 7 kunlik xarajatni olish (bloklaydi — to_thread bilan chaqiring)."""
    import boto3  # sekin import — faqat AWS kuzatuvi yoqilganda kerak

    today = date.today()
    start = date.fromisoformat(AWS_CREDIT_START) if AWS_CREDIT_START else today - timedelta(days=365)
    ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer faqat us-east-1 da

    def totals_by_record_type(start_d: date, end_d: date, granularity: str) -> dict[str, float]:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start_d.isoformat(), "End": end_d.isoformat()},  # End kirmaydi
            Granularity=granularity,
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}],
        )
        out: dict[str, float] = {}
        for period in resp["ResultsByTime"]:
            for g in period["Groups"]:
                out[g["Keys"][0]] = out.get(g["Keys"][0], 0.0) + float(g["Metrics"]["UnblendedCost"]["Amount"])
        return out

    # Kredit manfiy summa sifatida keladi
    credits_used = max(-totals_by_record_type(start, today + timedelta(days=1), "MONTHLY").get("Credit", 0.0), 0.0) + 0.0  # "-0.0" chiqmasin
    week = totals_by_record_type(today - timedelta(days=7), today, "DAILY")
    gross_week = sum(v for k, v in week.items() if k not in ("Credit", "Refund"))
    return {"credits_used": credits_used, "avg_daily": gross_week / 7}


async def fetch_aws_status(force: bool = False) -> dict:
    if not force and _aws_cache["data"] and time.monotonic() - _aws_cache["ts"] < AWS_CACHE_TTL:
        return _aws_cache["data"]

    raw = await asyncio.to_thread(_ce_costs_sync)
    remaining = max(AWS_CREDIT_TOTAL_USD - raw["credits_used"], 0.0) if AWS_CREDIT_TOTAL_USD else None
    days_by_balance = remaining / raw["avg_daily"] if remaining is not None and raw["avg_daily"] > 0 else None
    days_to_expiry = (date.fromisoformat(AWS_CREDIT_EXPIRES) - date.today()).days if AWS_CREDIT_EXPIRES else None
    candidates = [d for d in (days_by_balance, days_to_expiry) if d is not None]

    data = {
        **raw,
        "remaining": remaining,
        "days_by_balance": days_by_balance,
        "days_to_expiry": days_to_expiry,
        "days_left": min(candidates) if candidates else None,
    }
    _aws_cache.update(ts=time.monotonic(), data=data)
    return data


def format_aws(s: dict) -> str:
    lines = ["☁️ <b>AWS kredit holati</b>"]
    if AWS_CREDIT_TOTAL_USD:
        lines.append(f"💳 Boshlang'ich kredit: ${AWS_CREDIT_TOTAL_USD:,.2f}")
    lines.append(f"🔥 Kredit bilan qoplangan: ${s['credits_used']:,.2f}")
    if s["remaining"] is not None:
        lines.append(f"💰 Qolgan: <b>${s['remaining']:,.2f}</b>")
    lines.append(f"📈 O'rtacha sarf (7 kun): ${s['avg_daily']:,.2f}/kun")
    if s["days_by_balance"] is not None:
        lines.append(f"⏳ Balans yetadi: ~{s['days_by_balance']:.0f} kun")
    if s["days_to_expiry"] is not None:
        lines.append(f"📅 Kredit tugash sanasi: {AWS_CREDIT_EXPIRES} ({s['days_to_expiry']} kun qoldi)")
    lines.append("<i>Cost Explorer ma'lumoti 24 soatgacha kechikishi mumkin.</i>")
    return "\n".join(lines)


def credit_is_low(status: dict) -> bool:
    days, remaining = status["days_left"], status["remaining"]
    if days is not None and days <= CREDIT_LOW_DAYS:
        return True
    return bool(AWS_CREDIT_TOTAL_USD and remaining is not None and remaining <= AWS_CREDIT_TOTAL_USD * CREDIT_LOW_FRACTION)


async def aws_check_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue (har kuni): kredit kam qolgan bo'lsa HAR KUNI eslatish."""
    bot = context.bot
    try:
        status = await fetch_aws_status(force=True)
    except Exception as e:
        logger.exception("AWS Cost Explorer xatosi: %s", e)
        await _sync_problems(bot, "aws:", {"aws:api": f"AWS Cost Explorer'ga ulanib bo'lmadi: <code>{escape(str(e)[:200])}</code>"})
        return
    await _sync_problems(bot, "aws:", {})

    if not credit_is_low(status):
        return
    days = status["days_left"]
    urgent = days is not None and days <= CREDIT_URGENT_DAYS
    title = "🚨 <b>AWS kredit tugash arafasida!</b>" if urgent else "⚠️ <b>AWS kredit kam qoldi</b>"
    await _send(bot, f"{title}\n\n{format_aws(status)}")


# ============================= BUYRUQ + RO'YXATGA OLISH =============================

async def server_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/server yoki /status — server holati (faqat ADMIN_ID/MANAGER_ID)."""
    user = update.effective_user
    if not user or user.id not in (ADMIN_ID, MANAGER_ID):
        return

    try:
        stats, problems = await collect_health()
        text = format_health(stats, problems)
    except Exception as e:
        text = f"🖥 Server holatini olib bo'lmadi: <code>{escape(str(e)[:200])}</code>"

    # direct=True: Redis yiqilgan bo'lsa ham javob yetib boradi
    await context.bot.send_message(chat_id=user.id, text=text, parse_mode="HTML", direct=True)


aws_status_handler = server_status_handler


def register_monitor_jobs(job_queue) -> None:
    job_queue.run_repeating(health_check_job, interval=HEALTH_INTERVAL, first=60, name="server_health")
    logger.info("✅ Server monitori rejalashtirildi (har %s daqiqa)", int(HEALTH_INTERVAL.total_seconds() // 60))
