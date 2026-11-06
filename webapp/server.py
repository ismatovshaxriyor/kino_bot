"""Admin paneli serveri: aiohttp + WebSocket, real vaqtda server holati.

Xavfsizlik: ochiq faqat statik fayllar (ma'lumotsiz). Barcha metrikalar WebSocket orqali, birinchi xabarda
Telegram `initData` imzosi to'g'ri va foydalanuvchi ADMIN_ID/MANAGER_ID bo'lgandagina yuboriladi.
"""

import asyncio
import json
import logging
import os
import time
from collections import deque
from pathlib import Path

import aiohttp
from aiohttp import web

from utils.settings import ADMIN_ID, BOT_TOKEN, DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, MANAGER_ID, REDIS_URL
from webapp import metrics
from webapp.auth import validate_init_data
from webapp.ngrok_link import run_publisher

logger = logging.getLogger("webapp")

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_IDS = {ADMIN_ID, MANAGER_ID}

FAST_INTERVAL = 2        # soniya: host o'lchovi va ticklar
SLOW_INTERVAL = 5        # soniya: docker/postgres/redis
AWS_INTERVAL = 300       # soniya (server_monitor o'zi 30 daqiqa keshlaydi)
HISTORY_INTERVAL = 60    # soniya: uzoq tarix nuqtasi
FAST_KEEP = 300          # 300 * 2 s = 10 daqiqa
HISTORY_KEEP = 1440      # 1440 * 60 s = 24 soat
MAX_CLIENTS = 5
AUTH_TIMEOUT = 10
FAIL_LIMIT, FAIL_WINDOW = 10, 600   # IP bo'yicha: 10 daqiqada 10 ta muvaffaqiyatsiz urinishdan keyin blok


def make_point(ts: float, host: dict, svc: dict) -> dict:
    """Grafiklar uchun tekis (flat) nuqta. Qiymati yo'q maydonlar None."""
    cpu = host["cpu"] or {}
    r = lambda v, n=1: None if v is None else round(v, n)
    p = {
        "t": round(ts, 1),
        "cpu": cpu.get("busy"), "iowait": cpu.get("iowait"), "steal": cpu.get("steal"),
        "mem": host["mem"]["pct"], "swap": host["mem"]["swap_pct"],
        "load1": host["load"][0], "load5": host["load"][1],
        "rx": r(host["net"] and host["net"]["rx"], 0), "tx": r(host["net"] and host["net"]["tx"], 0),
        "dr": r(host["dio"] and host["dio"]["read"], 0), "dw": r(host["dio"] and host["dio"]["write"], 0),
        "disk": host["disk"]["pct"], "tcp": host["tcp"],
    }
    redis, pg = svc.get("redis"), svc.get("postgres")
    p.update(q=redis and redis["queue"], rmem=redis and redis["mem_mb"], rops=redis and redis["ops"])
    p.update(pgc=pg and pg["conns"], pga=pg and pg["active"], tps=pg and pg["tps"], hit=pg and pg["hit_pct"])
    for c in svc.get("docker") or []:
        if c["cpu"] is not None:
            p[f"cc:{c['name']}"] = c["cpu"]
        if c["mem"] is not None:
            p[f"cm:{c['name']}"] = c["mem"]
    return p


def average_points(points: list[dict]) -> dict:
    keys = {k for p in points for k in p if k != "t"}
    out = {"t": points[-1]["t"]}
    for k in keys:
        vals = [p[k] for p in points if p.get(k) is not None]
        out[k] = round(sum(vals) / len(vals), 2) if vals else None
    return out


def pack(points) -> dict:
    """Tarixni ixcham shaklga o'tkazish: kalitlar bir marta, qatorlar massiv."""
    keys = sorted({k for p in points for k in p if k != "t"})
    return {"keys": keys, "rows": [[p["t"]] + [p.get(k) for k in keys] for p in points]}


class Hub:
    def __init__(self, host: metrics.HostSampler, docker, pg, redis, aws_fn=metrics.aws_status):
        self.host_sampler, self.docker, self.pg, self.redis, self.aws_fn = host, docker, pg, redis, aws_fn
        self.fast = deque(maxlen=FAST_KEEP)
        self.history = deque(maxlen=HISTORY_KEEP)
        self.svc: dict = {"docker": None, "postgres": None, "redis": None, "bot": None}
        self.aws: dict | None = None
        self.clients: set[web.WebSocketResponse] = set()
        self._acc: list[dict] = []
        self._last_hist = time.monotonic()
        self.session: aiohttp.ClientSession | None = None

    # --- yig'ish
    async def collect_slow(self) -> None:
        async def guarded(coro):
            try:
                return await asyncio.wait_for(coro, 4)
            except Exception as e:
                logger.warning("Metrika xatosi: %s", e)
                return None

        docker, pg_bot, redis = await asyncio.gather(
            guarded(self.docker.collect(self.session)), guarded(self.pg.collect()), guarded(self.redis.collect()))
        self.svc["docker"], self.svc["redis"] = docker, redis
        self.svc["postgres"], self.svc["bot"] = pg_bot if pg_bot else (None, self.svc["bot"])

    async def collect_aws(self) -> None:
        try:
            self.aws = await self.aws_fn()
        except Exception as e:
            logger.warning("AWS holati olinmadi: %s", e)

    def tick(self) -> dict:
        ts = time.time()
        host = self.host_sampler.sample()
        point = make_point(ts, host, self.svc)
        self.fast.append(point)
        self._acc.append(point)
        msg = {"type": "tick", "host": host, "svc": self.svc, "aws": self.aws, "point": point,
               "alerts": metrics.evaluate_alerts(host, self.svc, self.aws)}
        if time.monotonic() - self._last_hist >= HISTORY_INTERVAL and self._acc:
            hist = average_points(self._acc)
            self.history.append(hist)
            msg["history_point"] = hist
            self._acc, self._last_hist = [], time.monotonic()
        return msg

    def history_message(self) -> dict:
        return {"type": "history", "fast": pack(self.fast), "slow": pack(self.history)}

    # --- tarqatish
    async def broadcast(self, payload: dict) -> None:
        if not self.clients:
            return
        text = json.dumps(payload, separators=(",", ":"))
        clients = list(self.clients)
        results = await asyncio.gather(*(c.send_str(text) for c in clients), return_exceptions=True)
        for c, res in zip(clients, results):
            if isinstance(res, Exception):
                self.clients.discard(c)


# --- brute-force'dan himoya
_fails: dict[str, list[float]] = {}


def _client_ip(request: web.Request) -> str:
    return (request.headers.get("X-Forwarded-For") or request.remote or "?").split(",")[0].strip()


def _blocked(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    if recent:
        _fails[ip] = recent
    else:
        _fails.pop(ip, None)
    return len(recent) >= FAIL_LIMIT


def _record_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    hub: Hub = request.app["hub"]
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=8192)
    await ws.prepare(request)
    ip = _client_ip(request)

    if _blocked(ip):
        await ws.close(code=4429, message=b"too many attempts")
        return ws
    try:
        msg = await asyncio.wait_for(ws.receive_json(), AUTH_TIMEOUT)
        user = validate_init_data(msg.get("initData"), BOT_TOKEN) if msg.get("type") == "auth" else None
    except Exception:
        user = None
    if not user or user["id"] not in ALLOWED_IDS:
        _record_fail(ip)
        await ws.send_json({"type": "denied"})
        await ws.close(code=4403, message=b"forbidden")
        return ws
    if len(hub.clients) >= MAX_CLIENTS:
        await ws.send_json({"type": "busy"})
        await ws.close(code=4409, message=b"too many clients")
        return ws

    await ws.send_json({"type": "hello", "user": {"id": user["id"], "name": user.get("first_name", "")},
                        "fast_interval": FAST_INTERVAL, "history_interval": HISTORY_INTERVAL})
    await ws.send_str(json.dumps(hub.history_message(), separators=(",", ":")))
    hub.clients.add(ws)
    try:
        async for _ in ws:   # mijozdan xabar kutilmaydi; faqat ulanishni ushlab turamiz
            pass
    finally:
        hub.clients.discard(ws)
    return ws


@web.middleware
async def security_headers(request: web.Request, handler):
    resp = await handler(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self' wss:"
    )
    return resp


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _loop(interval: float, fn) -> None:
    while True:
        started = time.monotonic()
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fon vazifasi xatosi")
        await asyncio.sleep(max(interval - (time.monotonic() - started), 0.2))


def create_app(hub: Hub, *, publisher=None) -> web.Application:
    app = web.Application(middlewares=[security_headers])
    app["hub"] = hub
    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", STATIC_DIR, show_index=False)

    async def on_start(app: web.Application) -> None:
        hub.session = aiohttp.ClientSession()
        hub.host_sampler.sample()  # delta bazasi
        await hub.collect_slow()

        async def fast():
            await asyncio.sleep(0)
            msg = hub.tick()
            await hub.broadcast(msg)

        tasks = [
            _loop(FAST_INTERVAL, fast),
            _loop(SLOW_INTERVAL, hub.collect_slow),
            _loop(AWS_INTERVAL, hub.collect_aws),
        ]
        if publisher:
            tasks.append(publisher(hub.session))
        app["tasks"] = [asyncio.create_task(t) for t in tasks]

    async def on_stop(app: web.Application) -> None:
        for t in app["tasks"]:
            t.cancel()
        await asyncio.gather(*app["tasks"], return_exceptions=True)
        for c in list(hub.clients):
            await c.close()
        await hub.session.close()
        await hub.pg.close()
        await hub.redis.close()

    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    hub = Hub(
        metrics.HostSampler(),
        metrics.DockerStats(os.environ.get("DOCKER_API_URL", "http://127.0.0.1:2375")),
        metrics.PgStats(host=DB_HOST, port=int(DB_PORT), dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD),
        metrics.RedisStats(REDIS_URL),
    )
    publisher = lambda session: run_publisher(session, os.environ.get("NGROK_API_URL", "http://127.0.0.1:4040"))
    host, port = os.environ.get("WEBAPP_HOST", "127.0.0.1"), int(os.environ.get("WEBAPP_PORT", "8787"))
    logger.info("Panel %s:%s da ishga tushmoqda", host, port)
    web.run_app(create_app(hub, publisher=publisher), host=host, port=port, access_log=None, print=None)
