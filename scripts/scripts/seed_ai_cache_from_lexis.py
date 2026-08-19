#!/usr/bin/env python3
"""One-time backfill: copy Lexis's word_breakdown/morph_suffix_explanation/lexeme_insight into
the AI service's own DB (word_breakdown/morph_suffix_explanation/word_insight) before Lexis
drops those tables (#268 — AI service becomes the sole store for this content).

Reverse direction of harvest_ai_cache.py (which pulls ai_dev -> Lexis). Run this once per
environment, before the Importer migration that drops the tables (V4__drop_ai_generated_
content_tables.sql) reaches that environment's Lexis DB, or the data is lost.

Usage:
    python scripts/seed_ai_cache_from_lexis.py --lexis-port 5432 --ai-port 5432
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


def seed_word_breakdown(lexis_cur, ai_cur):
    lexis_cur.execute("SELECT strongs_id, morph_code, breakdown_text, model_used, generation_ms FROM word_breakdown")
    rows = lexis_cur.fetchall()
    inserted = 0
    for strongs_id, morph_code, text, model, ms in rows:
        ai_cur.execute(
            "INSERT INTO word_breakdown (strongs_id, morph_code, breakdown_text, model_used, generation_ms) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (strongs_id, morph_code) DO NOTHING",
            (strongs_id, morph_code, text, model, ms))
        inserted += ai_cur.rowcount
    return len(rows), inserted


def seed_morph_suffix(lexis_cur, ai_cur):
    lexis_cur.execute("SELECT morph_code, explanation, model_used, generation_ms FROM morph_suffix_explanation")
    rows = lexis_cur.fetchall()
    inserted = 0
    for morph_code, explanation, model, ms in rows:
        ai_cur.execute(
            "INSERT INTO morph_suffix_explanation (morph_code, explanation, model_used, generation_ms) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (morph_code) DO NOTHING",
            (morph_code, explanation, model, ms))
        inserted += ai_cur.rowcount
    return len(rows), inserted


def seed_word_insight(lexis_cur, ai_cur):
    lexis_cur.execute("""
        SELECT l.strongs_id, li.insight_text, li.model_used, li.generation_ms
        FROM lexeme_insight li JOIN lexeme l ON l.id = li.lexeme_id
    """)
    rows = lexis_cur.fetchall()
    inserted = 0
    for strongs_id, text, model, ms in rows:
        ai_cur.execute(
            "INSERT INTO word_insight (strongs_id, insight_text, model_used, generation_ms) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (strongs_id) DO NOTHING",
            (strongs_id, text, model, ms))
        inserted += ai_cur.rowcount
    return len(rows), inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexis-host", default="localhost")
    parser.add_argument("--lexis-port", default=5432, type=int)
    parser.add_argument("--lexis-db", default="interlinear_bible_lexis_dev")
    parser.add_argument("--ai-host", default="localhost")
    parser.add_argument("--ai-port", default=5432, type=int)
    parser.add_argument("--ai-db", default="interlinear_bible_ai_dev")
    args = parser.parse_args()

    load_env_file()
    user, password = db_creds()

    lexis_conn = connect(args.lexis_host, args.lexis_port, args.lexis_db, user, password)
    lexis_cur = lexis_conn.cursor()
    ai_conn = connect(args.ai_host, args.ai_port, args.ai_db, user, password)
    ai_cur = ai_conn.cursor()

    seen, added = seed_word_breakdown(lexis_cur, ai_cur)
    print(f"word_breakdown: {seen} in Lexis, {added} new in ai_dev")

    seen, added = seed_morph_suffix(lexis_cur, ai_cur)
    print(f"morph_suffix_explanation: {seen} in Lexis, {added} new in ai_dev")

    seen, added = seed_word_insight(lexis_cur, ai_cur)
    print(f"word_insight: {seen} in Lexis, {added} new in ai_dev")

    ai_conn.commit()
    lexis_cur.close()
    lexis_conn.close()
    ai_cur.close()
    ai_conn.close()
    print("=== done ===")


if __name__ == "__main__":
    main()
