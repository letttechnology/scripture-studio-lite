#!/usr/bin/env python3
"""
import_biblionexus_alignment.py — Import word-level alignment data from the
BiblioNexus Alignments project into verse_word_trans_gloss.

Source: data/Alignments-main  (github.com/Clear-Bible/Alignments)
Greek base: SBLGNT (matches our verse_word table exactly)

Supports any English translation present under data/eng/:
  YLT  — Young's Literal Translation  (127,902 records)
  BSB  — Berean Standard Bible        (115,008 records, already in DB from OpenGNT)

Usage:
  python scripts/import_biblionexus_alignment.py --translation YLT
  python scripts/import_biblionexus_alignment.py --translation BSB --force
  python scripts/import_biblionexus_alignment.py --dry-run --translation YLT

Requirements:
  pip install psycopg2-binary python-dotenv
"""

import os, sys, re, json, argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary")
    sys.exit(1)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

DATA_DIR    = Path(__file__).parent.parent / "data" / "Alignments-main" / "data"
SOURCE_TSV  = DATA_DIR / "sources" / "SBLGNT.tsv"


# ── Parse source ID ───────────────────────────────────────────────────────────
# Format: n{book:02d}{chapter:03d}{verse:03d}{word:03d}
# e.g.    n43001001001  → John 1:1 word 1

def parse_source_id(sid):
    """Return (book_id, chapter, verse_num, word_position) or None."""
    if not sid or not sid.startswith("n") or len(sid) != 12:
        return None
    try:
        return (int(sid[1:3]), int(sid[3:6]), int(sid[6:9]), int(sid[9:12]))
    except ValueError:
        return None


# ── Load target words ─────────────────────────────────────────────────────────

def load_target_words(translation):
    """
    Returns {target_id: (text, is_punc)} for NT words of the translation.
    Handles both BSB format (source_verse col) and YLT format (altId col).
    """
    tsv_path = DATA_DIR / "eng" / "targets" / translation / f"nt_{translation}.tsv"
    if not tsv_path.exists():
        print(f"ERROR: Target file not found: {tsv_path}")
        sys.exit(1)

    words = {}
    with open(tsv_path, encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        # Detect format by second column name
        is_ylt_format = header[1] == "altId"

        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            tid  = cols[0].strip()
            text = cols[2].strip() if is_ylt_format else cols[2].strip()

            # isPunc column: YLT col[4], BSB col[3] (skip_space_after is empty for BSB punc)
            is_punc = False
            if is_ylt_format and len(cols) > 4:
                is_punc = cols[4].strip().lower() == "true"
            # Skip excluded words (BSB exclude col[4])
            if not is_ylt_format and len(cols) > 4 and cols[4].strip().lower() == "true":
                continue

            words[tid] = (text, is_punc)

    print(f"  Loaded {len(words):,} {translation} target words from {tsv_path.name}")
    return words


# ── Load alignment records ────────────────────────────────────────────────────

def load_alignment_records(translation):
    """Returns list of {source_ids: [...], target_ids: [...]} dicts."""
    json_path = DATA_DIR / "eng" / "alignments" / translation / f"SBLGNT-{translation}-manual.json"
    if not json_path.exists():
        print(f"ERROR: Alignment file not found: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    print(f"  Loaded {len(records):,} alignment records from {json_path.name}")
    return records


# ── Build verse_word lookup ───────────────────────────────────────────────────

def build_vw_lookup(conn):
    """
    Returns {(book_id, chapter, verse_num, position): verse_word_id}.
    Fetches all NT verse_word rows (book_id 40-66).
    """
    print("  Building verse_word position lookup...")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT vw.id, v.book_id, v.chapter, v.verse_num, vw.position
            FROM verse_word vw
            JOIN verse v ON v.id = vw.verse_id
            WHERE v.book_id BETWEEN 40 AND 66
        """)
        lookup = {}
        for row in cur.fetchall():
            key = (row["book_id"], row["chapter"], row["verse_num"], row["position"])
            lookup[key] = row["id"]
    print(f"  {len(lookup):,} verse_word rows indexed")
    return lookup


# ── Main import ───────────────────────────────────────────────────────────────

def already_imported(conn, translation):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM verse_word_trans_gloss WHERE translation_code = %s",
            (translation,)
        )
        return cur.fetchone()[0] > 0


def run_import(conn, translation, dry_run=False):
    target_words = load_target_words(translation)
    records      = load_alignment_records(translation)
    vw_lookup    = build_vw_lookup(conn)

    entries = []   # (verse_word_id, translation_code, gloss)
    skipped_no_source = 0
    skipped_no_vw     = 0
    multi_source      = 0

    for rec in records:
        source_ids = rec.get("source", [])
        target_ids = rec.get("target", [])

        if not source_ids:
            skipped_no_source += 1
            continue

        # Build English phrase from target IDs (in order, skip punctuation-only)
        phrase_parts = []
        for tid in target_ids:
            entry = target_words.get(tid)
            if entry:
                text, is_punc = entry
                if text and not is_punc:
                    phrase_parts.append(text)
        phrase = " ".join(phrase_parts).strip()
        if not phrase:
            continue

        # For multi-source alignments, assign phrase to first source token only
        if len(source_ids) > 1:
            multi_source += 1
        primary_sid = source_ids[0]

        loc = parse_source_id(primary_sid)
        if loc is None:
            skipped_no_source += 1
            continue

        book_id, chapter, verse_num, word_pos = loc
        vw_id = vw_lookup.get((book_id, chapter, verse_num, word_pos))
        if vw_id is None:
            skipped_no_vw += 1
            continue

        entries.append((vw_id, translation, phrase))

    print(f"\n  Alignment stats:")
    print(f"    Matched:          {len(entries):,}")
    print(f"    No verse_word:    {skipped_no_vw:,}")
    print(f"    No source:        {skipped_no_source:,}")
    print(f"    Multi-source:     {multi_source:,}")

    if dry_run:
        print("\n  Dry-run — sample entries:")
        for vw_id, code, gloss in entries[:20]:
            print(f"    verse_word {vw_id:>7}  {code}  {gloss!r}")
        return

    print(f"\n  Writing {len(entries):,} rows to verse_word_trans_gloss...")
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO verse_word_trans_gloss (verse_word_id, translation_code, gloss)
            VALUES %s
            ON CONFLICT (verse_word_id, translation_code) DO UPDATE SET gloss = EXCLUDED.gloss
            """,
            entries,
            page_size=5000,
        )
    conn.commit()
    print(f"  Done — {len(entries):,} rows upserted for {translation}.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import BiblioNexus SBLGNT alignment into verse_word_trans_gloss"
    )
    parser.add_argument("--translation", required=True,
                        help="Translation code, e.g. YLT or BSB")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Parse and report without writing to DB")
    parser.add_argument("--force",     action="store_true",
                        help="Re-import even if rows already exist (upserts)")
    args = parser.parse_args()

    translation = args.translation.upper()

    print(f"BiblioNexus alignment importer — {translation}")
    print(f"Connecting to {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)

    if not args.dry_run and not args.force and already_imported(conn, translation):
        print(f"  {translation} alignment already in DB. Use --force to re-import.")
        conn.close()
        return

    run_import(conn, translation, dry_run=args.dry_run)
    conn.close()


if __name__ == "__main__":
    main()
