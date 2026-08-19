#!/usr/bin/env python3
"""
export_lexicon_json.py — Export all free lexicon data to a pre-cleaned JSON file.

This replaces per-request API calls for word detail with a single static file
that the frontend loads once and caches. All text cleaning happens here, in
Python, once — never in the TypeScript UI.

Output: interlinear-bible-ui/public/data/lexicons.json

Cleaning rules applied:
  - Strong's: strip leading ":--", ":", "–", "—", "-" and trailing punctuation
  - Thayer / LSJ short_gloss: strip leading punctuation; keep semicolons inline
  - Thayer / LSJ full_definition: strip leading punctuation; convert semicolons to newlines
  - All sources: normalise consecutive whitespace; strip blank lines

Excluded (served by API, gated or dynamic):
  - lsj: PRO-gated, stays behind API
  - userGloss: user-specific, stays behind API

Usage:
  python scripts/export_lexicon_json.py
  python scripts/export_lexicon_json.py --out path/to/output.json
"""

import os, sys, re, json, argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary"); sys.exit(1)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

# Sources to include in the static file.  Order determines display order in UI.
FREE_SOURCES = ["corpus", "mounce", "abbottsmith", "thayer", "strongs", "wiktionary", "gk"]

# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_leading(text: str) -> str:
    """Strip leading punctuation/dashes used as list markers in old lexicons."""
    return re.sub(r'^[\s:;–—\-]+', '', text).strip()

def clean_short(text: str, source: str) -> str | None:
    """Clean short_gloss for display as the always-visible one-liner."""
    if not text:
        return None
    t = clean_leading(text).strip()
    # Normalise internal whitespace
    t = re.sub(r'[ \t]+', ' ', t)
    # Strip trailing sentence-ending punctuation (periods only, not colons/semicolons)
    t = t.rstrip('.')
    return t or None

def clean_full(text: str, source: str) -> str | None:
    """
    Clean full_definition for display in the expanded 'show more' view.
    For Thayer and LSJ: semicolons are sense dividers — convert to newlines so
    the UI can render each sense as its own line without any JavaScript parsing.
    For all other sources: preserve text as-is (just normalise whitespace).
    """
    if not text:
        return None
    t = clean_leading(text).strip()
    t = re.sub(r'[ \t]+', ' ', t)

    if source in ("thayer", "lsj"):
        # Each semicolon-separated sense becomes a paragraph
        senses = [s.strip().rstrip('.') for s in t.split(';') if s.strip()]
        t = '\n'.join(senses)

    # Remove runs of blank lines
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip() or None

# ── Main query ────────────────────────────────────────────────────────────────

LEXEME_QUERY = """
SELECT
    l.strongs_id,
    l.lemma,
    l.transliteration,
    l.part_of_speech,
    l.frequency_nt,
    l.etymology
FROM lexeme l
WHERE l.strongs_id IS NOT NULL
ORDER BY l.strongs_id
"""

MEANING_QUERY = """
SELECT
    l.strongs_id,
    lm.source,
    lm.short_gloss,
    lm.full_definition
FROM lexeme_meaning lm
JOIN lexeme l ON l.id = lm.lexeme_id
WHERE lm.source = ANY(%(sources)s)
  AND l.strongs_id IS NOT NULL
ORDER BY l.strongs_id, lm.source
"""

ETYMOLOGY_REFS_QUERY = None  # etymology_refs column not yet in schema

def main():
    parser = argparse.ArgumentParser()
    default_out = str(
        Path(__file__).parent.parent.parent /
        "interlinear-bible-ui" / "public" / "data" / "lexicons.json"
    )
    parser.add_argument("--out", default=default_out)
    args = parser.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to DB {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)

    # ── Load lexeme base data ──────────────────────────────────────────────────
    print("Loading lexemes...")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(LEXEME_QUERY)
        lexeme_rows = cur.fetchall()
    print(f"  {len(lexeme_rows):,} lexemes")

    # ── Load meanings ─────────────────────────────────────────────────────────
    print("Loading meanings...")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(MEANING_QUERY, {"sources": FREE_SOURCES})
        meaning_rows = cur.fetchall()
    print(f"  {len(meaning_rows):,} meaning rows across {len(FREE_SOURCES)} sources")

    etym_refs: dict[str, list] = {}  # not yet in schema

    conn.close()

    # ── Index meanings by strongs_id ──────────────────────────────────────────
    meanings_by_strongs: dict[str, dict] = {}
    for row in meaning_rows:
        sid = row["strongs_id"]
        src = row["source"]
        short = clean_short(row["short_gloss"], src)
        full  = clean_full(row["full_definition"], src)
        if not short and not full:
            continue
        meanings_by_strongs.setdefault(sid, {})[src] = {
            k: v for k, v in {"short": short, "full": full}.items() if v
        }

    # ── Build output ──────────────────────────────────────────────────────────
    output: dict[str, dict] = {}
    skipped = 0
    for row in lexeme_rows:
        sid = row["strongs_id"]
        meanings = meanings_by_strongs.get(sid, {})
        if not meanings:
            skipped += 1
            continue

        entry: dict = {
            "lemma":           row["lemma"],
            "partOfSpeech":    row["part_of_speech"],
            "frequencyNt":     row["frequency_nt"],
        }
        if row["transliteration"]:
            entry["transliteration"] = row["transliteration"]
        if row["etymology"]:
            entry["etymology"] = row["etymology"]

        # Preserve source order as defined in FREE_SOURCES
        entry["meanings"] = {
            src: meanings[src]
            for src in FREE_SOURCES
            if src in meanings
        }

        output[sid] = entry

    print(f"  {len(output):,} lexemes exported  ({skipped} had no free meanings)")

    # ── Write ─────────────────────────────────────────────────────────────────
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    size_kb = Path(args.out).stat().st_size / 1024
    print(f"  Written to: {args.out}  ({size_kb:.0f} KB)")
    print()
    print("Next: npm run dev — the frontend will load this file on first word click.")

if __name__ == "__main__":
    main()
