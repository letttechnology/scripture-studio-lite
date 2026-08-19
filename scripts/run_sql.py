#!/usr/bin/env python3
"""Read-only SQL runner for local dev DBs (no psql, no permission prompts).

Usage:
    python scripts/run_sql.py <database> "<SELECT ...>" ["<SELECT ...>" ...]

Reads DB_PASS/DB_USER from the repo-root .env (resolved from this file's
location, not a fixed path). Falls back to postgres/postgres if absent.
SELECT/WITH/SHOW/EXPLAIN only — anything else is refused (DB writes stay behind
explicit user approval, per workspace DB rules).
"""
import os
import sys

import psycopg2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_creds():
    user, password = "postgres", "postgres"
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("DB_USER="):
                user = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("DB_PASS="):
                password = line.split("=", 1)[1].strip().strip('"').strip("'")
    return user, password


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    database, queries = sys.argv[1], sys.argv[2:]

    for q in queries:
        head = q.lstrip().split(None, 1)[0].upper() if q.strip() else ""
        if head not in ("SELECT", "WITH", "SHOW", "EXPLAIN"):
            print(f"REFUSED (read-only runner): {q[:60]}")
            sys.exit(2)

    user, password = env_creds()
    conn = psycopg2.connect(host="localhost", port=5432, dbname=database,
                            user=user, password=password, connect_timeout=10)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            for q in queries:
                cur.execute(q)
                for row in cur.fetchall():
                    print("\t".join("" if v is None else str(v) for v in row))
                print("--")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
