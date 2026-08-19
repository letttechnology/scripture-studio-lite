#!/usr/bin/env python3
"""Dump ALL four project databases into a portable, self-describing bundle.

Runs on the machine that HOLDS the data (currently the Windows box). The
cross-machine counterpart to populate_dev_db_dump_restore.py, which can only
dump from localhost and only covers content/Lexis.

Unlike interlinear-bible-importer/scripts/dump.sh this covers all four
databases, not just content/Lexis:

  interlinear_bible_reader_content_dev  read-only corpus (Importer-owned)
  interlinear_bible_lexis_dev           read-only lexicon (Importer-owned)
  interlinear_bible_ai_dev              LLM cache -- real money to regenerate
  interlinear_bible_reader_user_dev     accounts, notes, highlights (Reader/Flyway-owned)

The bundle carries a manifest with server version and SHA-256 per file so the
restore side can verify integrity and refuse an incompatible Postgres.

Usage:
    python scripts/dump_all_dbs.py [out_dir]          # default ./dist

Env (or .env at repo root):
    DB_USER, DB_PASS        credentials (DB_PASS required)
    PGHOST, PGPORT          source server (default localhost:5432)
    PG_BIN                  folder holding pg_dump, if not on PATH
"""
import glob
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ordered so the read-only corpus lands first; restore replays this order.
DATABASES = [
    ("interlinear_bible_reader_content_dev", "content"),
    ("interlinear_bible_lexis_dev", "lexis"),
    ("interlinear_bible_ai_dev", "ai"),
    ("interlinear_bible_reader_user_dev", "user"),
]


def load_env_file():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def db_creds():
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASS")
    if not password:
        print("Error: DB_PASS not found in .env or environment.", file=sys.stderr)
        sys.exit(1)
    return user, password


def find_tool(name):
    """Locate a Postgres client binary.

    Windows installs land in C:\\Program Files\\PostgreSQL\\<ver>\\bin and are
    routinely absent from PATH, so fall back to a newest-version-first glob
    rather than making the user edit their PATH.
    """
    explicit = os.environ.get("PG_BIN")
    if explicit:
        candidate = os.path.join(explicit, name + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(candidate):
            return candidate
        print(f"Error: PG_BIN is set but {candidate} does not exist.", file=sys.stderr)
        sys.exit(1)

    found = shutil.which(name)
    if found:
        return found

    if os.name == "nt":
        pattern = r"C:\Program Files\PostgreSQL\*\bin\{}.exe".format(name)
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]

    print(
        f"Error: '{name}' not found. Install the PostgreSQL client tools, or set\n"
        f"       PG_BIN to the folder containing them.",
        file=sys.stderr,
    )
    sys.exit(1)


def tool_version(tool_path):
    out = subprocess.run([tool_path, "--version"], capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def server_version(psql_path, env, host, port, user):
    result = subprocess.run(
        [psql_path, "-h", host, "-p", port, "-U", user, "-d", "postgres",
         "-tAc", "show server_version"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print("Error: could not connect to the source Postgres.", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def database_exists(psql_path, env, host, port, user, dbname):
    result = subprocess.run(
        [psql_path, "-h", host, "-p", port, "-U", user, "-d", "postgres",
         "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{dbname}'"],
        capture_output=True, text=True, env=env,
    )
    return result.stdout.strip() == "1"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    load_env_file()
    user, password = db_creds()
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")

    pg_dump = find_tool("pg_dump")
    psql = find_tool("psql")

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    version = server_version(psql, env, host, port, user)
    print(f"Source: {host}:{port} (Postgres {version})")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
    bundle = os.path.join(out_root, f"db-bundle-{stamp}")
    os.makedirs(bundle, exist_ok=True)

    files = []
    skipped = []
    for dbname, role in DATABASES:
        if not database_exists(psql, env, host, port, user, dbname):
            print(f"  ! {dbname} does not exist on this server -- skipping")
            skipped.append(dbname)
            continue

        filename = f"{role}.dump"
        target = os.path.join(bundle, filename)
        print(f"  > {dbname} -> {filename}")
        result = subprocess.run(
            [pg_dump, "-h", host, "-p", port, "-U", user,
             "--format=custom", "--no-owner", "--no-privileges",
             "--dbname", dbname, "--file", target],
            env=env,
        )
        if result.returncode != 0:
            print(f"Error: pg_dump failed for {dbname} (exit {result.returncode})", file=sys.stderr)
            sys.exit(result.returncode)

        files.append({
            "database": dbname,
            "role": role,
            "file": filename,
            "bytes": os.path.getsize(target),
            "sha256": sha256(target),
        })

    if not files:
        print("Error: nothing was dumped -- no matching databases on this server.", file=sys.stderr)
        sys.exit(1)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_host": platform.node(),
        "source_platform": platform.platform(),
        "server_version": version,
        "pg_dump_version": tool_version(pg_dump),
        "format": "custom",
        "files": files,
        "skipped": skipped,
    }
    with open(os.path.join(bundle, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    total = sum(f["bytes"] for f in files)
    print()
    print(f"Bundle ready: {bundle}")
    print(f"  {len(files)} database(s), {total / 1024 / 1024:.1f} MB total")
    if skipped:
        print(f"  skipped (absent): {', '.join(skipped)}")
    print()
    print("Copy the whole folder to the target machine, then run there:")
    print("  python3 scripts/restore_all_dbs.py <bundle-folder>")


if __name__ == "__main__":
    main()
