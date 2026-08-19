#!/usr/bin/env python3
"""Merge one ai_dev instance's cache into another ai_dev instance (e.g. k8s dev cluster -> local).

Since #268, the AI service's own DB (word_breakdown / morph_suffix_explanation / word_insight)
is the sole store for this content — Lexis no longer holds a copy at all, so there is nothing
left to harvest INTO Lexis (see git history for the old ai_dev -> Lexis version of this script,
superseded by #268). This version merges ai_dev directly into ai_dev: useful for pulling
whatever a k8s cluster already generated into your local instance before generating more,
without re-paying for LLM calls on combos someone already ran.

Handles the pre/post-#268 table rename automatically: the insight table is `word_insight` on
an instance that's had the rename migration applied, `lexeme_insight` on one that hasn't yet
(e.g. the k8s dev cluster, until that migration ships there) — this script detects which name
exists on each side and reads/writes accordingly.

Usage:
    python scripts/harvest_ai_cache.py --source-port 5433 --target-port 5432
    python scripts/harvest_ai_cache.py --source-port 5433 --source-port 5434 --target-port 5432

Each --source-port is an ai_dev to merge FROM (same host, different port-forwards/instances).
Conflicts (same key already present in the target) are left as-is — first writer wins, nothing
is overwritten silently.
"""
import argparse
import os
import sys

import psycopg2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASS")
    if not user or not password:
        print("Error: DB_USER/DB_PASS not found in .env or environment.", file=sys.stderr)
        sys.exit(1)
    return user, password


def connect(host, port, dbname, user, password):
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password,
                             connect_timeout=10)


def insight_table_name(cur):
    cur.execute("SELECT to_regclass('word_insight')")
    if cur.fetchone()[0]:
        return "word_insight"
    cur.execute("SELECT to_regclass('lexeme_insight')")
    if cur.fetchone()[0]:
        return "lexeme_insight"
    raise RuntimeError("Neither word_insight nor lexeme_insight found — is this really an ai_dev DB?")


def merge_word_breakdown(source_cur, target_cur):
    source_cur.execute("SELECT strongs_id, morph_code, breakdown_text, model_used, generation_ms FROM word_breakdown")
    rows = source_cur.fetchall()
    inserted = 0
    for strongs_id, morph_code, text, model, ms in rows:
        target_cur.execute(
            "INSERT INTO word_breakdown (strongs_id, morph_code, breakdown_text, model_used, generation_ms) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (strongs_id, morph_code) DO NOTHING",
            (strongs_id, morph_code, text, model, ms))
        inserted += target_cur.rowcount
    return len(rows), inserted


def merge_morph_suffix(source_cur, target_cur):
    source_cur.execute("SELECT morph_code, explanation, model_used, generation_ms FROM morph_suffix_explanation")
    rows = source_cur.fetchall()
    inserted = 0
    for morph_code, explanation, model, ms in rows:
        target_cur.execute(
            "INSERT INTO morph_suffix_explanation (morph_code, explanation, model_used, generation_ms) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (morph_code) DO NOTHING",
            (morph_code, explanation, model, ms))
        inserted += target_cur.rowcount
    return len(rows), inserted


def merge_insight(source_cur, target_cur):
    source_table = insight_table_name(source_cur)
    target_table = insight_table_name(target_cur)
    source_cur.execute(f"SELECT strongs_id, insight_text, model_used, generation_ms FROM {source_table}")
    rows = source_cur.fetchall()
    inserted = 0
    for strongs_id, text, model, ms in rows:
        target_cur.execute(
            f"INSERT INTO {target_table} (strongs_id, insight_text, model_used, generation_ms) "
            f"VALUES (%s, %s, %s, %s) ON CONFLICT (strongs_id) DO NOTHING",
            (strongs_id, text, model, ms))
        inserted += target_cur.rowcount
    return source_table, target_table, len(rows), inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-host", default="localhost")
    parser.add_argument("--source-port", action="append", required=True, type=int,
                         help="Port to an ai_dev source (repeatable — one per port-forward/instance)")
    parser.add_argument("--source-db", default="interlinear_bible_ai_dev")
    parser.add_argument("--target-host", default="localhost")
    parser.add_argument("--target-port", default=5432, type=int)
    parser.add_argument("--target-db", default="interlinear_bible_ai_dev")
    args = parser.parse_args()

    load_env_file()
    user, password = db_creds()

    target_conn = connect(args.target_host, args.target_port, args.target_db, user, password)
    target_cur = target_conn.cursor()

    for port in args.source_port:
        print(f"=== merging ai_dev @ {args.source_host}:{port} -> {args.target_host}:{args.target_port} ===")
        source_conn = connect(args.source_host, port, args.source_db, user, password)
        source_cur = source_conn.cursor()

        seen, added = merge_word_breakdown(source_cur, target_cur)
        print(f"word_breakdown: {seen} in source, {added} new")

        seen, added = merge_morph_suffix(source_cur, target_cur)
        print(f"morph_suffix_explanation: {seen} in source, {added} new")

        source_table, target_table, seen, added = merge_insight(source_cur, target_cur)
        name_note = f" ({source_table} -> {target_table})" if source_table != target_table else ""
        print(f"insight{name_note}: {seen} in source, {added} new")

        target_conn.commit()
        source_cur.close()
        source_conn.close()

    target_cur.close()
    target_conn.close()
    print("=== done ===")


if __name__ == "__main__":
    main()
