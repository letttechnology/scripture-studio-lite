#!/usr/bin/env python3
"""Batch-fill insight / breakdown / morph-suffix content via the AI service.

Usage:
    python scripts/populate_ai_content.py insight [--limit N] [--delay-ms MS]
    python scripts/populate_ai_content.py breakdown [--limit N] [--delay-ms MS]
    python scripts/populate_ai_content.py morph-suffix [--limit N] [--delay-ms MS]
    python scripts/populate_ai_content.py all [--limit N] [--delay-ms MS]

Reads candidate keys from Lexis's DB (lexeme/token_morphology — the actual corpus data) and
calls the AI service directly (bypassing Lexis's Pro-auth gate on insight — appropriate for a
controlled backend batch job, not a user-facing bypass) so the round-robin provider pool built
for epic #17 does the actual generation and caching. "Already done" is checked against the AI
service's own DB (word_breakdown/morph_suffix_explanation/word_insight) — since #268, Lexis no
longer holds a copy of this content at all, so this is now the only place it can be checked.
Idempotent: the AI service's own retrieve-or-generate logic also skips regeneration for anything
already cached, so a resumed/rerun is always safe even if the exclusion check somehow missed one.

Defaults assume everything is running locally (Lexis DB + AI service both on localhost, no
port-forward). Pass --db-port/--ai-port/--ai-url to point at a port-forwarded k8s cluster instead.

Progress is appended to scripts/populate_ai_content.log as it runs — safe to Ctrl+C and resume;
already-cached items just return fast (cache hit) rather than re-generating.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

import psycopg2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "populate_ai_content.log")


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


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def post_json(url, body, timeout=60):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        return e.code, body_text
    except Exception as e:
        return None, str(e)


def fetch_done_insight_strongs_ids(ai_cur):
    ai_cur.execute("SELECT strongs_id FROM word_insight")
    return {row[0] for row in ai_cur.fetchall()}


def fetch_insight_targets(cur, ai_cur, limit):
    # Function words (article, pronoun, particle, conjunction, preposition, adverb, ...) get no
    # insight — same rule as LexemeRepository.findFunctionWordLexemeIds (#50): dominant POS across
    # a lexeme's token occurrences is grammatical rather than N/V/A. Word-study commentary on "the"
    # or "and" isn't useful; per-lexeme insight is meant for content words.
    done = fetch_done_insight_strongs_ids(ai_cur)
    cur.execute("""
        WITH dominant_pos AS (
            SELECT lexeme_id, pos_code,
                   ROW_NUMBER() OVER (PARTITION BY lexeme_id ORDER BY COUNT(*) DESC, pos_code) AS rn
            FROM token_morphology
            WHERE pos_code IS NOT NULL
            GROUP BY lexeme_id, pos_code
        ), function_words AS (
            SELECT lexeme_id FROM dominant_pos WHERE rn = 1 AND pos_code NOT IN ('N', 'V', 'A')
        )
        SELECT id, strongs_id, lemma, transliteration, part_of_speech, frequency_nt, etymology
        FROM lexeme
        WHERE id NOT IN (SELECT lexeme_id FROM function_words)
        ORDER BY frequency_nt DESC NULLS LAST
    """)
    targets = [row for row in cur.fetchall() if row[1] not in done]
    return targets[:limit]


def fetch_definitions(cur, lexeme_id):
    cur.execute("""
        SELECT source, full_definition, short_gloss
        FROM lexeme_meaning
        WHERE lexeme_id = %s
        ORDER BY CASE source
            WHEN 'corpus' THEN 1 WHEN 'lsj' THEN 2 WHEN 'gk' THEN 3
            WHEN 'ugl' THEN 4 WHEN 'abbottsmith' THEN 5 WHEN 'thayer' THEN 6 ELSE 10 END
        LIMIT 4
    """, (lexeme_id,))
    out = []
    for source, full_def, short_gloss in cur.fetchall():
        text = full_def or short_gloss or ""
        if text.strip():
            out.append({"source": source, "text": text})
    return out


def run_insight(cur, ai_cur, ai_url, limit, delay_ms):
    targets = fetch_insight_targets(cur, ai_cur, limit)
    log(f"[insight] {len(targets)} targets")
    done = failed = 0
    for lexeme_id, strongs_id, lemma, translit, pos, freq, etym in targets:
        body = {
            "strongsId": strongs_id, "lemma": lemma, "transliteration": translit,
            "partOfSpeech": pos, "frequencyNt": freq, "etymology": etym,
            "definitions": fetch_definitions(cur, lexeme_id),
        }
        status, resp = post_json(f"{ai_url}/insight", body)
        if status == 200:
            done += 1
            log(f"[insight] OK {strongs_id} ({lemma}) [{done}/{len(targets)}]")
        else:
            failed += 1
            log(f"[insight] FAIL {strongs_id}: {status} {resp}")
        time.sleep(delay_ms / 1000)
    log(f"[insight] done={done} failed={failed}")


def fetch_done_breakdown_keys(ai_cur):
    ai_cur.execute("SELECT strongs_id, morph_code FROM word_breakdown")
    return {(row[0], row[1]) for row in ai_cur.fetchall()}


def fetch_breakdown_targets(cur, ai_cur, limit):
    # DISTINCT ON picks one representative token_id per (lexeme, morph_code) combo — used to
    # look up a real surface form for prompt grounding, same context the live on-demand path
    # always has from the clicked token. Without it the model has nothing concrete to anchor
    # to and produces vaguer/less accurate output (observed directly on G1/N-NSN-T).
    done = fetch_done_breakdown_keys(ai_cur)
    cur.execute("""
        SELECT DISTINCT ON (l.strongs_id, tm.morphology_code)
            l.strongs_id, l.lemma, l.transliteration, tm.morphology_code,
            tm.pos_code, tm.tense, tm.voice, tm.mood, tm.person, tm.number,
            tm.grammatical_case, tm.gender, tm.token_id
        FROM token_morphology tm
        JOIN lexeme l ON l.id = tm.lexeme_id
        WHERE tm.morphology_code IS NOT NULL
    """)
    targets = [row for row in cur.fetchall() if (row[0], row[3]) not in done]
    return targets[:limit]


def fetch_surface_forms(content_cur, token_ids):
    """Batch-look-up surface_form/transliteration from Reader's content DB by verse_word id (#187 token id)."""
    if not token_ids:
        return {}
    content_cur.execute(
        "SELECT id, surface_form, transliteration FROM verse_word WHERE id = ANY(%s)",
        (list(token_ids),))
    return {row[0]: (row[1], row[2]) for row in content_cur.fetchall()}


def run_breakdown(cur, ai_cur, content_cur, ai_url, limit, delay_ms):
    targets = fetch_breakdown_targets(cur, ai_cur, limit)
    log(f"[breakdown] {len(targets)} targets")
    surfaces = fetch_surface_forms(content_cur, [t[12] for t in targets])
    done = failed = 0
    for sid, lemma, translit, morph_code, pos, tense, voice, mood, person, number, case, gender, token_id in targets:
        surface, token_translit = surfaces.get(token_id, (None, None))
        body = {
            "strongsId": sid, "morphCode": morph_code, "lemma": lemma, "transliteration": translit,
            "surface": surface, "translit": token_translit,
            "pos": pos, "tense": tense, "voice": voice, "mood": mood, "person": person,
            "number": number, "grammaticalCase": case, "gender": gender,
        }
        status, resp = post_json(f"{ai_url}/breakdown", body)
        if status == 200:
            done += 1
            log(f"[breakdown] OK {sid}/{morph_code} (surface={surface}) [{done}/{len(targets)}]")
        else:
            failed += 1
            log(f"[breakdown] FAIL {sid}/{morph_code}: {status} {resp}")
        time.sleep(delay_ms / 1000)
    log(f"[breakdown] done={done} failed={failed}")


def fetch_done_morph_suffix_codes(ai_cur):
    ai_cur.execute("SELECT morph_code FROM morph_suffix_explanation")
    return {row[0] for row in ai_cur.fetchall()}


def fetch_morph_suffix_targets(cur, ai_cur, limit):
    done = fetch_done_morph_suffix_codes(ai_cur)
    cur.execute("""
        SELECT DISTINCT ON (tm.morphology_code)
            tm.morphology_code, tm.pos_code, tm.tense, tm.voice, tm.mood,
            tm.person, tm.number, tm.grammatical_case, tm.gender, tm.token_id
        FROM token_morphology tm
        WHERE tm.morphology_code IS NOT NULL
    """)
    targets = [row for row in cur.fetchall() if row[0] not in done]
    return targets[:limit]


def run_morph_suffix(cur, ai_cur, content_cur, ai_url, limit, delay_ms):
    targets = fetch_morph_suffix_targets(cur, ai_cur, limit)
    log(f"[morph-suffix] {len(targets)} targets")
    surfaces = fetch_surface_forms(content_cur, [t[9] for t in targets])
    done = failed = 0
    for morph_code, pos, tense, voice, mood, person, number, case, gender, token_id in targets:
        surface, _ = surfaces.get(token_id, (None, None))
        body = {
            "morphCode": morph_code, "pos": pos, "tense": tense, "voice": voice, "mood": mood,
            "person": person, "number": number, "grammaticalCase": case, "gender": gender,
            "surface": surface,
        }
        status, resp = post_json(f"{ai_url}/morph-suffix", body)
        if status == 200:
            done += 1
            log(f"[morph-suffix] OK {morph_code} (surface={surface}) [{done}/{len(targets)}]")
        else:
            failed += 1
            log(f"[morph-suffix] FAIL {morph_code}: {status} {resp}")
        time.sleep(delay_ms / 1000)
    log(f"[morph-suffix] done={done} failed={failed}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["insight", "breakdown", "morph-suffix", "all"])
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--delay-ms", type=int, default=1200,
                         help="Pause between calls (default 1200ms — ~50/min combined across a 2-provider round-robin pool, conservative for Groq's 30/min single-key limit).")
    parser.add_argument("--ai-url", default="http://localhost:8083/ai")
    parser.add_argument("--db-port", type=int, default=5432,
                         help="Port for Lexis/content DBs (default 5432 — local Postgres, no port-forward needed).")
    parser.add_argument("--ai-db-port", type=int, default=None,
                         help="Port for the AI service's own DB, where 'already done' is checked "
                              "(default: same as --db-port, since it's normally the same local Postgres instance).")
    args = parser.parse_args()
    ai_db_port = args.ai_db_port if args.ai_db_port is not None else args.db_port

    load_env_file()
    user, password = db_creds()
    conn = psycopg2.connect(host="localhost", port=args.db_port, dbname="interlinear_bible_lexis_dev",
                             user=user, password=password, connect_timeout=10)
    cur = conn.cursor()
    # Second connection: surface-form grounding for breakdown/morph-suffix lives in Reader's
    # content DB (verse_word), not Lexis's — separate databases, same postgres instance/port.
    content_conn = psycopg2.connect(host="localhost", port=args.db_port, dbname="interlinear_bible_reader_content_dev",
                                     user=user, password=password, connect_timeout=10)
    content_cur = content_conn.cursor()
    # Third connection: "already done" now lives only in the AI service's own DB (#268) —
    # Lexis no longer holds word_breakdown/morph_suffix_explanation/word_insight at all.
    ai_conn = psycopg2.connect(host="localhost", port=ai_db_port, dbname="interlinear_bible_ai_dev",
                               user=user, password=password, connect_timeout=10)
    ai_cur = ai_conn.cursor()

    log(f"=== populate_ai_content.py kind={args.kind} limit={args.limit} delay_ms={args.delay_ms} ===")

    # "all" runs smallest/shortest-output first: morph-suffix (~80 words, 1,064 targets) before
    # breakdown (3-5 sentences, ~18.5k targets) before insight (~200-250 words, ~4.9k targets) —
    # shorter output generates faster per call, so this order clears the smallest space quickest
    # rather than spending the first hours on the slowest content type.
    if args.kind in ("morph-suffix", "all"):
        run_morph_suffix(cur, ai_cur, content_cur, args.ai_url, args.limit, args.delay_ms)
    if args.kind in ("breakdown", "all"):
        run_breakdown(cur, ai_cur, content_cur, args.ai_url, args.limit, args.delay_ms)
    if args.kind in ("insight", "all"):
        run_insight(cur, ai_cur, args.ai_url, args.limit, args.delay_ms)

    cur.close()
    conn.close()
    content_cur.close()
    content_conn.close()
    ai_cur.close()
    ai_conn.close()
    log("=== complete ===")


if __name__ == "__main__":
    main()
