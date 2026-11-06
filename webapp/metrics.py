"""Server metrikalari: host (/proc), Docker, Postgres, Redis, bot statistikasi.

/proc ni o'qiydigan funksiyalar sof (matn -> son) qilib yozilgan, shuning uchun testlanadi.
"""

import asyncio
import logging
import os
import re
import shutil
import time

import aiohttp

logger = logging.getLogger(__name__)

_DISK_RE = re.compile(r"^(nvme\d+n\d+|xvd[a-z]+|sd[a-z]+|vd[a-z]+)$")
_VIRTUAL_NIC = ("lo", "docker", "br-", "veth")


# ---------- /proc parserlari ----------

def parse_cpu_stat(text: str) -> dict[str, tuple]:
    out = {}
    for line in text.splitlines():
        if line.startswith("cpu"):
            parts = line.split()
            out[parts[0]] = tuple(float(x) for x in parts[1:9])  # user nice system idle iowait irq softirq steal
    return out


def cpu_usage(prev: tuple, cur: tuple) -> dict | None:
    d = [c - p for c, p in zip(cur, prev)]
    total = sum(d)
    if total <= 0:
        return None
    pct = lambda v: round(100.0 * v / total, 1)
    return {
        "busy": round(100.0 - pct(d[3]) - pct(d[4]), 1),
        "user": pct(d[0] + d[1]),
        "system": pct(d[2] + d[5] + d[6]),
        "iowait": pct(d[4]),
        "steal": pct(d[7]),
    }


def parse_meminfo(text: str) -> dict[str, int]:
    info = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if rest:
            info[key] = int(rest.split()[0])  # kB
    return info


def mem_summary(info: dict) -> dict:
    mb = lambda kb: round(kb / 1024, 1)
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    swap_used = swap_total - info.get("SwapFree", 0)
    return {
        "total": mb(total),
        "used": mb(total - avail),
        "available": mb(avail),
        "cached": mb(info.get("Cached", 0) + info.get("Buffers", 0)),
        "pct": round(100.0 * (total - avail) / total, 1) if total else 0.0,
        "swap_total": mb(swap_total),
        "swap_used": mb(swap_used),
        "swap_pct": round(100.0 * swap_used / swap_total, 1) if swap_total else 0.0,
    }


def parse_net_dev(text: str) -> tuple[int, int]:
    """Tashqi tarmoq interfeyslari bo'yicha (qabul qilingan, yuborilgan) baytlar."""
    rx = tx = 0
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        name = name.strip()
        if not rest or name.startswith(_VIRTUAL_NIC):
            continue
        cols = rest.split()
        rx += int(cols[0])
        tx += int(cols[8])
    return rx, tx


def parse_diskstats(text: str) -> tuple[int, int]:
    """Butun disklar bo'yicha (o'qilgan, yozilgan) baytlar (sektor = 512 bayt)."""
    rd = wr = 0
    for line in text.splitlines():
        cols = line.split()
        if len(cols) >= 10 and _DISK_RE.match(cols[2]):
            rd += int(cols[5]) * 512
            wr += int(cols[9]) * 512
    return rd, wr


def parse_sockstat_tcp(text: str) -> int:
    for line in text.splitlines():
        if line.startswith("TCP:"):
            parts = line.split()
            return int(parts[parts.index("inuse") + 1])
    return 0


class HostSampler:
    """Host holati. Birinchi chaqiruvda (delta yo'q) cpu/tarmoq/disk tezliklari None bo'ladi."""

    def __init__(self, proc: str = "/proc", root: str = "/"):
        self.proc, self.root = proc, root
        self._prev = None  # (monotonic, cpu_stat, net, disk)

    def _read(self, name: str) -> str:
        with open(f"{self.proc}/{name}") as f:
            return f.read()

    def sample(self) -> dict:
        now = time.monotonic()
        cpu_now = parse_cpu_stat(self._read("stat"))
        net_now = parse_net_dev(self._read("net/dev"))
        disk_now = parse_diskstats(self._read("diskstats"))

        cpu = cores = net = dio = None
        if self._prev:
            t0, cpu0, net0, disk0 = self._prev
            dt = max(now - t0, 1e-6)
            cpu = cpu_usage(cpu0["cpu"], cpu_now["cpu"])
            cores = [
                (cpu_usage(cpu0[k], cpu_now[k]) or {}).get("busy")
                for k in sorted((k for k in cpu_now if k != "cpu"), key=lambda s: int(s[3:]))
            ]
            net = {"rx": max(net_now[0] - net0[0], 0) / dt, "tx": max(net_now[1] - net0[1], 0) / dt}
            dio = {"read": max(disk_now[0] - disk0[0], 0) / dt, "write": max(disk_now[1] - disk0[1], 0) / dt}
        self._prev = (now, cpu_now, net_now, disk_now)

        du = shutil.disk_usage(self.root)
        st = os.statvfs(self.root)
        load = self._read("loadavg").split()
        return {
            "cpu": cpu,
            "cores": cores,
            "ncpu": len([k for k in cpu_now if k != "cpu"]),
            "mem": mem_summary(parse_meminfo(self._read("meminfo"))),
            "load": [float(load[0]), float(load[1]), float(load[2])],
            "procs": int(load[3].split("/")[1]),
            "uptime": float(self._read("uptime").split()[0]),
            "net": net,
            "dio": dio,
            "disk": {
                "total_gb": round(du.total / 1e9, 1),
                "used_gb": round(du.used / 1e9, 1),
                "pct": round(100.0 * du.used / (du.used + du.free), 1),
                "inode_pct": round(100.0 * (st.f_files - st.f_ffree) / st.f_files, 1) if st.f_files else 0.0,
            },
            "tcp": parse_sockstat_tcp(self._read("net/sockstat")),
        }


# ---------- Docker (docker-socket-proxy orqali, faqat o'qish) ----------

class DockerStats:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self._prev: dict[str, tuple[float, int]] = {}

    async def collect(self, session: aiohttp.ClientSession) -> list[dict]:
        timeout = aiohttp.ClientTimeout(total=5)
        async with session.get(f"{self.base}/containers/json?all=1", timeout=timeout) as resp:
            resp.raise_for_status()
            containers = await resp.json()

        async def one(c: dict) -> dict:
            item = {
                "name": c["Names"][0].lstrip("/"),
                "image": c.get("Image", ""),
                "state": c.get("State", ""),
                "status": c.get("Status", ""),
                "cpu": None, "mem": None, "rx": None, "tx": None,
            }
            if item["state"] != "running":
                return item
            try:
                url = f"{self.base}/containers/{c['Id']}/stats?stream=false&one-shot=true"
                async with session.get(url, timeout=timeout) as resp:
                    resp.raise_for_status()
                    s = await resp.json()
            except Exception as e:
                logger.warning("Docker stats %s: %s", item["name"], e)
                return item

            now = time.monotonic()
            usage = s["cpu_stats"]["cpu_usage"]["total_usage"]  # nanosekund
            prev = self._prev.get(c["Id"])
            self._prev[c["Id"]] = (now, usage)
            ncpu = s["cpu_stats"].get("online_cpus") or os.cpu_count() or 1
            if prev and now > prev[0]:
                item["cpu"] = round(max(usage - prev[1], 0) / ((now - prev[0]) * 1e9 * ncpu) * 100, 2)
            mem = s.get("memory_stats", {})
            used = mem.get("usage", 0) - mem.get("stats", {}).get("inactive_file", 0)
            item["mem"] = round(max(used, 0) / 1048576, 1)
            nets = s.get("networks") or {}
            if nets:
                item["rx"] = sum(n["rx_bytes"] for n in nets.values())
                item["tx"] = sum(n["tx_bytes"] for n in nets.values())
            return item

        items = await asyncio.gather(*(one(c) for c in containers))
        live = {c["Id"] for c in containers}
        self._prev = {k: v for k, v in self._prev.items() if k in live}
        return sorted(items, key=lambda i: i["name"])


# ---------- Postgres ----------

_PG_SQL = """
SELECT (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()),
       (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'active'),
       (SELECT setting::int FROM pg_settings WHERE name = 'max_connections'),
       pg_database_size(current_database()),
       d.xact_commit + d.xact_rollback, d.blks_hit, d.blks_read
FROM pg_stat_database d WHERE d.datname = current_database()
"""
_BOT_SQL = """
SELECT (SELECT count(*) FROM "user"),
       (SELECT count(*) FROM movie),
       (SELECT count(*) FROM "user" WHERE created_at > now() - interval '24 hours'),
       (SELECT count(*) FROM usermoviehistory WHERE viewed_at > now() - interval '24 hours')
"""
BOT_STATS_EVERY = 60  # soniya


class PgStats:
    def __init__(self, **conn_kwargs):
        self._kw = conn_kwargs
        self._conn = None
        self._prev = None
        self._bot = None
        self._bot_at = 0.0

    async def _connect(self):
        import psycopg
        if self._conn is None or self._conn.closed:
            self._conn = await psycopg.AsyncConnection.connect(autocommit=True, connect_timeout=3, **self._kw)
        return self._conn

    async def close(self):
        if self._conn is not None and not self._conn.closed:
            await self._conn.close()

    async def collect(self) -> tuple[dict, dict | None]:
        """(postgres, bot) statistikasi. Ulanish xatosida istisno ko'tariladi (panelda 'ishlamayapti')."""
        try:
            conn = await self._connect()
            async with conn.cursor() as cur:
                await cur.execute(_PG_SQL)
                conns, active, max_conns, size, xacts, hit, read = await cur.fetchone()
                now = time.monotonic()
                tps = None
                if self._prev and now > self._prev[0]:
                    tps = round(max(xacts - self._prev[1], 0) / (now - self._prev[0]), 2)
                self._prev = (now, xacts)
                if self._bot is None or now - self._bot_at >= BOT_STATS_EVERY:
                    await cur.execute(_BOT_SQL)
                    users, movies, new_users, views = await cur.fetchone()
                    self._bot = {"users": users, "movies": movies, "new_users_24h": new_users, "views_24h": views}
                    self._bot_at = now
        except Exception:
            await self.close()
            self._conn = None
            raise
        pg = {
            "conns": conns, "active": active, "max_conns": max_conns,
            "size_mb": round(size / 1048576, 1), "tps": tps,
            "hit_pct": round(100.0 * hit / (hit + read), 2) if hit + read else None,
        }
        return pg, self._bot


# ---------- Redis ----------

class RedisStats:
    def __init__(self, url: str, queue_name: str = "bot_queue"):
        import redis.asyncio as aioredis
        self._r = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
        self.queue_name = queue_name

    async def collect(self) -> dict:
        info = await self._r.info()
        queue = await self._r.llen(self.queue_name)
        hits, misses = info.get("keyspace_hits", 0), info.get("keyspace_misses", 0)
        return {
            "queue": queue,
            "mem_mb": round(info["used_memory"] / 1048576, 2),
            "max_mb": round(info.get("maxmemory", 0) / 1048576, 1),
            "clients": info.get("connected_clients"),
            "ops": info.get("instantaneous_ops_per_sec"),
            "hit_pct": round(100.0 * hits / (hits + misses), 1) if hits + misses else None,
            "evicted": info.get("evicted_keys", 0),
            "keys": await self._r.dbsize(),
            "uptime": info.get("uptime_in_seconds"),
        }

    async def close(self):
        await self._r.aclose()


# ---------- AWS (mavjud monitor keshidan) ----------

async def aws_status() -> dict | None:
    from utils.settings import AWS_CREDIT_TOTAL_USD, AWS_MONITOR_ENABLED
    if not AWS_MONITOR_ENABLED:
        return None
    from services.server_monitor import credit_is_low, fetch_aws_status
    s = await fetch_aws_status()
    return {**s, "total": AWS_CREDIT_TOTAL_USD or None, "low": credit_is_low(s)}


# ---------- Ogohlantirishlar ----------

DISK_WARN, MEM_MIN_MB, SWAP_WARN, CPU_WARN, STEAL_WARN, QUEUE_WARN = 85, 150, 50, 90, 20, 500


def evaluate_alerts(host: dict, svc: dict, aws: dict | None) -> list[str]:
    out = []
    if host["disk"]["pct"] >= DISK_WARN:
        out.append(f"💽 Disk {host['disk']['pct']}% to'lgan")
    if host["mem"]["available"] < MEM_MIN_MB:
        out.append(f"🧠 Bo'sh xotira {host['mem']['available']:.0f} MB qoldi")
    if host["mem"]["swap_pct"] > SWAP_WARN:
        out.append(f"🧠 Swap {host['mem']['swap_pct']}% ishlatilmoqda")
    if host["cpu"] and host["cpu"]["busy"] > CPU_WARN:
        out.append(f"🔥 CPU {host['cpu']['busy']}%")
    if host["cpu"] and host["cpu"]["steal"] > STEAL_WARN:
        out.append(f"⚠️ CPU steal {host['cpu']['steal']}% (burst kredit tugayotgan bo'lishi mumkin)")
    for name in ("postgres", "redis", "docker"):
        if svc.get(name) is None:
            out.append(f"❌ {name} ma'lumotini olib bo'lmadi")
    if svc.get("redis") and svc["redis"]["queue"] > QUEUE_WARN:
        out.append(f"📨 Redis navbati {svc['redis']['queue']} ta")
    for c in svc.get("docker") or []:
        if c["state"] != "running":
            out.append(f"🐳 {c['name']}: {c['state']}")
    if aws and aws.get("low"):
        left = aws.get("days_left")
        out.append("💳 AWS kredit kam" + (f" (~{left:.0f} kun)" if left is not None else ""))
    return out
