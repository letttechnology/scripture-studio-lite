#!/usr/bin/env python3
"""
extract_canonical_words.py — Build canonical_word JSON from existing gloss data.

Reverse-engineers the single best English word per lemma from what the rules
engine already produced. For verbs, the infinitive gloss ('to die') is the
clearest signal — strip 'to ' and you have 'die'. For nouns/adjectives/etc.,
the lexeme_sense[0] primary gloss is used directly.

Output: data/canonical_words.json
  {
    "G599": {
      "lemma": "ἀποθνήσκω",
      "transliteration": "apothnēskō",
      "corpus_gloss": "to die; to be put to death; to renounce",
      "canonical_word": "die",
      "source": "infinitive"   # how canonical_word was derived
    },
    ...
  }

source values:
  "infinitive"  — stripped from 'to X' infinitive gloss in gloss_set_entry
  "sense0"      — taken from lexeme_sense[0] primary gloss (nouns, adj, particles)
  "none"        — no data available (rare)

Usage:
  python scripts/extract_canonical_words.py           # build data/canonical_words.json
  python scripts/extract_canonical_words.py --report  # summary stats only
  python scripts/extract_canonical_words.py --sample G599 G4160 G2309  # spot-check specific words
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
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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

OUT_FILE = Path(__file__).parent.parent / "data" / "canonical_words.json"


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def strip_to(gloss):
    """Strip 'to ' prefix from infinitive gloss. 'to die' → 'die'."""
    if gloss and gloss.lower().startswith("to "):
        return gloss[3:].strip()
    return None


def clean_sense0(gloss):
    """
    Extract a single clean word from lexeme_sense[0] primary gloss.
    Handles:
      'to die'           → 'die'
      'die'              → 'die'
      'the north'        → 'north'
      'God, a god'       → 'God'
      'fullness'         → 'fullness'
    """
    if not gloss:
        return None
    g = gloss.strip()
    # Strip 'to '
    if g.lower().startswith("to "):
        g = g[3:].strip()
    # Strip 'the ', 'a ', 'an '
    for art in ("the ", "a ", "an "):
        if g.lower().startswith(art):
            g = g[len(art):].strip()
            break
    # Take first comma-separated phrase, then first word
    first = g.split(',')[0].strip()
    first_word = first.split()[0].strip() if first else ''
    # Strip trailing punctuation
    first_word = first_word.rstrip('.,;:')
    return first_word if first_word else None


def extract(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get gloss_set id
    cur.execute("SELECT id FROM gloss_set WHERE name = 'lite_auto' LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("ERROR: lite_auto gloss set not found")
        sys.exit(1)
    gsid = row["id"]

    # Main query: per lexeme, get lexeme_sense[0], corpus gloss,
    # and best active infinitive gloss from the generated gloss set.
    cur.execute("""
        SELECT
            l.strongs_id,
            l.lemma,
            l.transliteration,
            ls.gloss                                                    AS sense0,
            lm.short_gloss                                              AS corpus_gloss,
            MIN(gse.gloss) FILTER (
                WHERE vw.mood = 'Infinitive'
                  AND (vw.voice = 'Active' OR vw.voice IS NULL)
                  AND gse.gloss IS NOT NULL
                  AND gse.gloss <> ''
                  AND gse.gloss NOT LIKE '%%[%%'
            )                                                           AS inf_gloss,
            COUNT(vw.id)                                                AS token_count
        FROM lexeme l
        JOIN lexeme_sense ls
            ON ls.lexeme_id = l.id AND ls.sense_index = 0
        LEFT JOIN lexeme_meaning lm
            ON lm.lexeme_id = l.id AND lm.source = 'corpus'
        LEFT JOIN verse_word vw
            ON vw.lexeme_id = l.id
        LEFT JOIN gloss_set_entry gse
            ON gse.verse_word_id = vw.id AND gse.gloss_set_id = %s
        GROUP BY l.strongs_id, l.lemma, l.transliteration, ls.gloss, lm.short_gloss
        ORDER BY l.strongs_id
    """, (gsid,))

    rows = cur.fetchall()
    cur.close()
    return rows


def build_entry(row):
    """Derive canonical_word and source from a DB row."""
    # Prefer infinitive gloss — clearest signal for verbs
    inf = strip_to(row["inf_gloss"])
    if inf:
        return inf, "infinitive"

    # Fall back to lexeme_sense[0]
    w = clean_sense0(row["sense0"])
    if w:
        return w, "sense0"

    return None, "none"


def main():
    parser = argparse.ArgumentParser(description="Extract canonical_word per lemma from existing gloss data")
    parser.add_argument("--report", action="store_true", help="Summary stats only, no file write")
    parser.add_argument("--sample", nargs="+", metavar="STRONGS_ID",
                        help="Spot-check specific Strong's IDs (e.g. G599 G4160)")
    args = parser.parse_args()

    conn = get_conn()
    rows = extract(conn)
    conn.close()

    result = {}
    stats = {"infinitive": 0, "sense0": 0, "none": 0}

    for row in rows:
        word, source = build_entry(row)
        stats[source] += 1
        result[row["strongs_id"]] = {
            "lemma":          row["lemma"],
            "transliteration": row["transliteration"] or "",
            "corpus_gloss":   row["corpus_gloss"] or "",
            "canonical_word": word or "",
            "source":         source,
            "token_count":    row["token_count"] or 0,
        }

    if args.sample:
        print(f"\n{'='*70}")
        print(f"  Sample spot-check")
        print(f"{'='*70}")
        for sid in args.sample:
            sid = sid.upper()
            if not sid.startswith("G"):
                sid = "G" + sid
            e = result.get(sid)
            if not e:
                print(f"\n  {sid} — not found")
                continue
            print(f"\n  {sid}  {e['lemma']}  ({e['transliteration']})")
            print(f"  corpus:    {e['corpus_gloss'][:80]}")
            print(f"  canonical: \"{e['canonical_word']}\"  (via {e['source']})")
        return

    if args.report:
        total = len(result)
        print(f"\nCanonical word extraction summary ({total} lemmas):")
        print(f"  From infinitive gloss:  {stats['infinitive']:>5}  ({stats['infinitive']/total*100:.1f}%)")
        print(f"  From sense0 gloss:      {stats['sense0']:>5}  ({stats['sense0']/total*100:.1f}%)")
        print(f"  No data:                {stats['none']:>5}  ({stats['none']/total*100:.1f}%)")

        # Show a sample of each source type
        print(f"\n  Sample 'infinitive' derivations:")
        shown = 0
        for sid, e in result.items():
            if e["source"] == "infinitive" and e["token_count"] > 10 and shown < 8:
                print(f"    {sid:<8} {e['lemma']:<20} \"{e['canonical_word']}\"")
                shown += 1

        print(f"\n  Sample 'sense0' derivations:")
        shown = 0
        for sid, e in result.items():
            if e["source"] == "sense0" and e["token_count"] > 5 and shown < 8:
                print(f"    {sid:<8} {e['lemma']:<20} \"{e['canonical_word']}\"  ← {e['corpus_gloss'][:50]}")
                shown += 1

        print(f"\n  'none' entries (no canonical word derived):")
        for sid, e in result.items():
            if e["source"] == "none":
                print(f"    {sid:<8} {e['lemma']:<20} corpus: {e['corpus_gloss'][:50]}")
        return

    # Write file
    OUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = len(result)
    print(f"Written {total} entries to {OUT_FILE}")
    print(f"  {stats['infinitive']} from infinitive gloss  |  {stats['sense0']} from sense0  |  {stats['none']} empty")
    print(f"\nNext: review data/canonical_words.json, then run synthesize_canonical.py to verify via AI batch.")


if __name__ == "__main__":
    main()
