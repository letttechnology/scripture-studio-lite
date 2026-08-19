#!/usr/bin/env python3
"""
backfill_word_insights.py — pre-generate Word Insight for high-frequency lemmas (#33).

Word Insight is PRO content generated on first request and cached permanently. Without a
backfill the first user to open each word waits for a live generation. The top 1,091 lemmas
(frequency_nt >= 10) cover ~92% of NT text, so backfilling those removes the wait for
almost every real lookup.

WHY THIS REPLACES scripts/old/generate_word_insights.py

That script called the Anthropic Batch API directly, holding its own provider choice, its
own prompt, and its own idea of where results are stored. Since then the AI service
(interlinear-bible-ai) owns all three: POST /insight is retrieve-or-generate, backed by the
word_insight cache, routed through the configured provider chain.

So this driver generates nothing itself. It finds what is missing and asks the AI service
for it, one lemma at a time. Provider, prompt and rate limits stay the AI service's
concern — which is the point of #255 and #268.

STATE OF PLAY (measured 2026-08-14)

    AI cache (interlinear_bible_ai_dev.word_insight)   713
    target lemmas (frequency_nt >= 10)               1,091
    target covered                                     679   62%
    target MISSING                                     412
    cache entries below the target threshold            34

All 713 existing entries came from llama-3.1-8b-instant between 2026-07-31 and 08-06.

USAGE

    python scripts/backfill_word_insights.py --dry-run
    python scripts/backfill_word_insights.py --limit 20
    python scripts/backfill_word_insights.py                 # all missing
    python scripts/backfill_word_insights.py --min-frequency 25

Resumable by construction: it re-reads what is cached on every run, so an interrupted run
picks up where it stopped. Nothing is lost by killing it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Iterable

import psycopg2
import urllib.error
import urllib.request
import json as jsonlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUDIO_DB = "interlinear_bible_studio_dev"
AI_DB = "interlinear_bible_ai_dev"

# Lexis assembles the prompt context and calls the AI service, because it owns the lexicon
# data. Going through Lexis rather than straight to the AI service keeps one prompt-assembly
# path, so a backfilled insight is identical to one generated on demand.
DEFAULT_LEXIS_URL = "http://localhost:8082/lexis"

# Free-tier Groq allows roughly 30 requests/minute. 2.5s between calls leaves headroom for
# the generation itself and stays clear of the limit without needing burst logic.
DEFAULT_DELAY_S = 2.5


def env_creds() -> tuple[str, str]:
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


def query(database: str, sql: str) -> list[tuple]:
    user, password = env_creds()
    conn = psycopg2.connect(host="localhost", port=5432, dbname=database,
                            user=user, password=password, connect_timeout=10)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def missing_lemmas(min_frequency: int) -> list[tuple[str, str, int]]:
    """Target lemmas with no cached insight, highest frequency first.

    Ordered by frequency so an interrupted run has still covered the words users are most
    likely to open.
    """
    cached = {r[0] for r in query(AI_DB, "SELECT strongs_id FROM word_insight")}
    target = query(
        STUDIO_DB,
        "SELECT strongs_id, lemma, frequency_nt FROM lexeme "
        f"WHERE frequency_nt >= {int(min_frequency)} "
        "ORDER BY frequency_nt DESC",
    )
    return [(sid, lemma, freq) for sid, lemma, freq in target if sid not in cached]


def request_insight(base_url: str, strongs_id: str, token: str | None, timeout: int) -> tuple[bool, str]:
    """Ask Lexis for the insight, which generates and caches it if absent.

    Returns (ok, detail). A 403 means the caller is not PRO — the endpoint is PRO-gated,
    so a backfill needs a token with ROLE_PRO or ROLE_ADMIN.
    """
    url = f"{base_url.rstrip('/')}/lexicon/{strongs_id}/insight"
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                text = jsonlib.loads(body).get("insightText") or ""
            except Exception:
                text = body
            return True, f"{len(text)} chars"
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return False, "403 not PRO — pass --token with a PRO/ADMIN JWT"
        if e.code == 404:
            return False, "404 unknown lemma or generation failed"
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — network shapes vary, all are retryable by re-running
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lexis-url", default=os.environ.get("LEXIS_URL", DEFAULT_LEXIS_URL))
    ap.add_argument("--token", default=os.environ.get("PRO_JWT"),
                    help="JWT with ROLE_PRO or ROLE_ADMIN; the endpoint is PRO-gated")
    ap.add_argument("--min-frequency", type=int, default=10,
                    help="lemma frequency floor (default 10 — the top 1,091, ~92%% of NT text)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N lemmas (0 = all)")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY_S,
                    help=f"seconds between calls (default {DEFAULT_DELAY_S}, ~24 req/min)")
    ap.add_argument("--timeout", type=int, default=120, help="per-request timeout in seconds")
    ap.add_argument("--dry-run", action="store_true", help="report the gap and exit")
    args = ap.parse_args()

    try:
        pending = missing_lemmas(args.min_frequency)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not read databases: {e}", file=sys.stderr)
        return 2

    cached_total = len(query(AI_DB, "SELECT strongs_id FROM word_insight"))
    target_total = len(query(
        STUDIO_DB,
        f"SELECT strongs_id FROM lexeme WHERE frequency_nt >= {int(args.min_frequency)}"))

    print("=" * 70)
    print("WORD INSIGHT BACKFILL (#33)")
    print(f"  AI cache entries            : {cached_total:,}")
    print(f"  target lemmas (freq >= {args.min_frequency:<3})  : {target_total:,}")
    print(f"  already covered             : {target_total - len(pending):,}")
    print(f"  missing                     : {len(pending):,}")
    print("=" * 70)

    if args.dry_run:
        print("\nHighest-frequency missing lemmas:")
        for sid, lemma, freq in pending[:25]:
            print(f"  {sid:<8} {lemma:<18} freq {freq}")
        if len(pending) > 25:
            print(f"  ... and {len(pending) - 25:,} more")
        return 0

    if not pending:
        print("\nNothing to do.")
        return 0

    if not args.token:
        print("\nWARNING: no --token given. /lexicon/{id}/insight is PRO-gated and will "
              "return 403 for an anonymous caller.\n", file=sys.stderr)

    work = pending[: args.limit] if args.limit > 0 else pending
    est_min = (len(work) * args.delay) / 60
    print(f"\nGenerating {len(work):,} insights at {args.delay}s intervals "
          f"(~{est_min:.0f} min). Ctrl-C is safe — rerun resumes.\n")

    ok = failed = 0
    for i, (sid, lemma, freq) in enumerate(work, start=1):
        success, detail = request_insight(args.lexis_url, sid, args.token, args.timeout)
        if success:
            ok += 1
            print(f"  [{i}/{len(work)}] {sid:<8} {lemma:<18} freq {freq:<5} ok  ({detail})")
        else:
            failed += 1
            print(f"  [{i}/{len(work)}] {sid:<8} {lemma:<18} freq {freq:<5} FAILED — {detail}")
            # A 403 will fail identically for every remaining lemma; stop rather than
            # emitting hundreds of identical errors.
            if detail.startswith("403"):
                print("\nStopping: every remaining call would fail the same way.", file=sys.stderr)
                break
        if i < len(work):
            time.sleep(args.delay)

    print(f"\nDone — {ok:,} generated, {failed:,} failed.")
    if failed:
        print("Re-run to retry the failures; cached entries are skipped automatically.")
    return 1 if failed and ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
