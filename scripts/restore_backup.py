#!/usr/bin/env python3
"""Kino-bot zaxira nusxasini (backup) tiklash vositasi.

Ikki formatni qo'llab-quvvatlaydi:
  • .sql.gz / .sql   — pg_dump natijasi. To'g'ridan-to'g'ri psql ga quyiladi.
  • .json.gz / .json — zaxira usul. Jadvallarga qatorlab INSERT qilinadi.

DIQQAT (JSON uchun):
  JSON faqat MA'LUMOTNI saqlaydi, jadval tuzilmasini (schema) emas. Shuning uchun
  avval bo'sh bazada jadvallar mavjud bo'lishi kerak:  `aerich upgrade`  ni ishlating,
  keyin shu skriptni `--yes` bilan chaqiring (mavjud ma'lumotlar TRUNCATE qilinadi).

Foydalanish:
  python scripts/restore_backup.py kino_backup_YYYYMMDD_HHMMSS.json.gz --yes
  python scripts/restore_backup.py kino_backup_YYYYMMDD_HHMMSS.sql.gz

DB ulanish ma'lumotlari .env dan olinadi (DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT).
"""
import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_DOCKER_CONTAINER = os.environ.get("DB_DOCKER_CONTAINER")

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_db_env():
    missing = [n for n, v in {
        "DB_NAME": DB_NAME, "DB_USER": DB_USER, "DB_PASSWORD": DB_PASSWORD,
        "DB_HOST": DB_HOST, "DB_PORT": DB_PORT,
    }.items() if not v]
    if missing:
        sys.exit(f"❌ .env da quyidagilar yo'q: {', '.join(missing)}")


def _read_bytes(path: Path) -> bytes:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            return f.read()
    return path.read_bytes()


def _find_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in ("/opt/homebrew/opt/libpq/bin", "/usr/local/opt/libpq/bin",
                 "/usr/bin", "/usr/local/bin",
                 "/usr/lib/postgresql/17/bin", "/usr/lib/postgresql/16/bin",
                 "/usr/lib/postgresql/15/bin"):
        cand = os.path.join(base, name)
        if os.path.exists(cand):
            return cand
    return None


# ----------------------------- SQL (pg_dump) -----------------------------

def restore_sql(path: Path) -> None:
    data = _read_bytes(path)
    psql = _find_bin("psql")

    if psql:
        env = dict(os.environ)
        if DB_PASSWORD:
            env["PGPASSWORD"] = DB_PASSWORD
        cmd = [psql, "-h", DB_HOST, "-p", str(DB_PORT), "-U", DB_USER, "-d", DB_NAME, "-v", "ON_ERROR_STOP=0"]
        print(f"▶️  psql orqali tiklanmoqda: {' '.join(cmd)}")
        proc = subprocess.run(cmd, input=data, env=env)
        sys.exit(proc.returncode)

    docker = shutil.which("docker")
    if DB_DOCKER_CONTAINER and docker:
        cmd = [docker, "exec", "-i"]
        if DB_PASSWORD:
            cmd += ["-e", f"PGPASSWORD={DB_PASSWORD}"]
        cmd += [DB_DOCKER_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME]
        print(f"▶️  docker orqali tiklanmoqda: {' '.join(cmd)}")
        proc = subprocess.run(cmd, input=data)
        sys.exit(proc.returncode)

    # psql topilmadi — qo'lda tiklash uchun .sql ni chiqaramiz
    out = path.with_suffix("") if path.suffix == ".gz" else path
    out = Path(str(out))
    out.write_bytes(data)
    print(
        "⚠️  psql topilmadi. SQL fayl ochildi:\n"
        f"   {out}\n\n"
        "Qo'lda tiklash uchun (host'da):\n"
        f"   psql -h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME} -f {out}\n"
        "yoki docker bilan:\n"
        f"   cat {out} | docker exec -i {DB_DOCKER_CONTAINER or '<konteyner>'} psql -U {DB_USER} -d {DB_NAME}"
    )
    sys.exit(1)


# ------------------------------- JSON ------------------------------------

def restore_json(path: Path, assume_yes: bool) -> None:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError:
        sys.exit("❌ psycopg o'rnatilmagan: pip install psycopg")

    def _adapt(v):
        # JSON/JSONB ustunlar dict/list ko'rinishida keladi — Jsonb bilan o'raymiz
        if isinstance(v, (dict, list)):
            return Jsonb(v)
        return v

    raw = _read_bytes(path)
    dump = json.loads(raw)
    tables = [t for t in dump.keys() if t != "_meta"]

    for t in tables:
        if not _IDENT_RE.match(t):
            sys.exit(f"❌ Shubhali jadval nomi: {t!r} — to'xtatildi")

    total_rows = sum(len(dump[t]) for t in tables if isinstance(dump[t], list))
    print(f"📦 Backup: {path.name}")
    print(f"   Jadvallar: {len(tables)} | Jami qatorlar: {total_rows}")
    meta = dump.get("_meta", {})
    if meta:
        print(f"   Olingan vaqt: {meta.get('generated_at')} | baza: {meta.get('database')}")

    if not assume_yes:
        print("\n⚠️  Bu mavjud ma'lumotlarni O'CHIRADI (TRUNCATE) va backupdan tiklaydi.")
        print("   Tasdiqlash uchun qaytadan --yes bilan ishga tushiring.")
        sys.exit(2)

    conn = psycopg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )
    try:
        with conn.cursor() as cur:
            # FK/triggerlarni vaqtincha o'chirib turamiz — istalgan tartibda insert qilish uchun
            cur.execute("SET session_replication_role = replica")

            quoted = ", ".join(f'"{t}"' for t in tables)
            cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")

            for t in tables:
                rows = dump[t]
                if not isinstance(rows, list) or not rows:
                    continue
                cols = list(rows[0].keys())
                for c in cols:
                    if not _IDENT_RE.match(c):
                        sys.exit(f"❌ Shubhali ustun nomi: {t}.{c!r} — to'xtatildi")
                collist = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                sql = f'INSERT INTO "{t}" ({collist}) VALUES ({placeholders})'
                values = [[_adapt(row.get(c)) for c in cols] for row in rows]
                cur.executemany(sql, values)
                print(f"   ✓ {t}: {len(rows)} qator")

            # auto-increment ketma-ketliklarni (sequence) eng katta qiymatga tiklash
            for t in tables:
                rows = dump[t]
                if not isinstance(rows, list) or not rows:
                    continue
                for c in rows[0].keys():
                    cur.execute("SELECT pg_get_serial_sequence(%s, %s)", (t, c))
                    seq = cur.fetchone()[0]
                    if seq:
                        # GREATEST(..., 1): channel_id kabi manfiy qiymatli ustunlar
                        # sequence chegarasidan (min 1) chiqib ketmasligi uchun.
                        cur.execute(
                            f'SELECT setval(%s, GREATEST(COALESCE((SELECT MAX("{c}") FROM "{t}"), 1), 1))',
                            (seq,),
                        )

            cur.execute("SET session_replication_role = DEFAULT")
        conn.commit()
        print(f"\n✅ Tiklash yakunlandi: {total_rows} qator tiklandi.")
    except Exception as e:
        conn.rollback()
        sys.exit(f"❌ Tiklashda xato (o'zgarishlar bekor qilindi): {e}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Kino-bot backup tiklash vositasi")
    parser.add_argument("backup_file", help="Backup fayli (.sql.gz / .sql / .json.gz / .json)")
    parser.add_argument("--yes", action="store_true", help="JSON tiklashni tasdiqlash (TRUNCATE qiladi)")
    args = parser.parse_args()

    _check_db_env()

    path = Path(args.backup_file)
    if not path.exists():
        sys.exit(f"❌ Fayl topilmadi: {path}")

    name = path.name.lower()
    if name.endswith(".sql.gz") or name.endswith(".sql"):
        restore_sql(path)
    elif name.endswith(".json.gz") or name.endswith(".json"):
        restore_json(path, args.yes)
    else:
        sys.exit("❌ Noma'lum format. Kutilgan: .sql.gz, .sql, .json.gz yoki .json")


if __name__ == "__main__":
    main()
