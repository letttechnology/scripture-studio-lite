#!/usr/bin/env python3
"""
fix_sense_ordering.py — Correct short_gloss sense ordering for anomalous corpus entries.

Problem: 1,338 of 5,614 multi-sense corpus entries have sense 0 longer than at least one
other sense. The corpus-sense-design.md data contract requires sense 0 to be the shortest,
most common NT meaning. C1 contextual sense selection assumes sense 0 is the established
primary — if sense 0 is verbose, C1 will select the wrong sense.

Fix rule: for anomalous entries, sort all senses by ascending word count.

Safety tiers:
  ≥ 4 words (391 entries): SAFE to auto-fix. Sense 0 is clearly a definition, not a gloss.
    Examples: "one sent on a mission", "of or belonging to Galatia". These are never correct
    interlinear glosses; any shorter sense is better.
  2–3 words (947 entries): UNSAFE to auto-fix by length alone. The 2–3 word phrase may be
    the correct NT primary meaning (e.g. "fine linen" for βύσσος, "bunch of grapes" for βότρυς).
    Ascending sort would displace these in favour of a classical 1-word synonym. Leave these
    to C1 contextual sense selection.

Default: --min-s0 4 (only fix entries where sense 0 ≥ 4 words — the safe tier).

Usage:
  python scripts/fix_sense_ordering.py --dry-run           # show 4+ word entries (default 20)
  python scripts/fix_sense_ordering.py --dry-run --min-s0 2 # show all anomalous entries
  python scripts/fix_sense_ordering.py --dry-run --limit 0  # show all (no limit)
  python scripts/fix_sense_ordering.py --stats              # distribution report only
  python scripts/fix_sense_ordering.py --apply              # fix 4+ word entries (391 entries)
  python scripts/fix_sense_ordering.py --apply --min-s0 2   # fix all anomalous (UNSAFE — review first)
"""

import os, sys, re, argparse
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
    print("ERROR: pip install psycopg2-binary")
    sys.exit(1)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def word_count(s):
    return len(s.split())


def reorder_senses(short_gloss):
    """
    Sort senses by ascending word count (stable sort preserves relative order for ties).
    Returns (new_gloss, changed: bool).
    """
    senses = [s.strip() for s in short_gloss.split(';') if s.strip()]
    if len(senses) <= 1:
        return short_gloss, False
    sorted_senses = sorted(senses, key=word_count)
    new_gloss = '; '.join(sorted_senses)
    changed = (senses != sorted_senses)
    return new_gloss, changed


def is_anomalous(short_gloss):
    """True if sense 0 is longer than at least one other sense."""
    senses = [s.strip() for s in short_gloss.split(';') if s.strip()]
    if len(senses) <= 1:
        return False
    wc0 = word_count(senses[0])
    return any(word_count(s) < wc0 for s in senses[1:])


def fetch_corpus_entries(conn):
    """Return all multi-sense corpus entries from lexeme_meaning."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT lm.id, lm.short_gloss, l.strongs_id, l.lemma
            FROM lexeme_meaning lm
            JOIN lexeme l ON l.id = lm.lexeme_id
            WHERE lm.source = 'corpus'
              AND lm.short_gloss LIKE '%%;%%'
            ORDER BY l.strongs_id
        """)
        return [dict(r) for r in cur.fetchall()]


def cmd_stats(conn):
    entries = fetch_corpus_entries(conn)
    total = len(entries)
    anomalous = [e for e in entries if is_anomalous(e['short_gloss'])]

    print(f"Multi-sense corpus entries: {total}")
    print(f"Anomalous (sense 0 > min other sense): {len(anomalous)}")
    print()

    # Distribution of sense-0 word count among anomalous entries
    from collections import Counter
    dist = Counter()
    for e in anomalous:
        senses = [s.strip() for s in e['short_gloss'].split(';') if s.strip()]
        dist[word_count(senses[0])] += 1

    print("Sense-0 word count distribution (anomalous entries only):")
    for wc in sorted(dist):
        label = "auto-safe" if wc <= 3 else "needs review"
        print(f"  {wc:2d} words: {dist[wc]:4d} entries  [{label}]")

    auto = sum(v for k, v in dist.items() if k <= 3)
    review = sum(v for k, v in dist.items() if k > 3)
    print()
    print(f"Auto-sortable (sense 0 ≤ 3 words): {auto}")
    print(f"Manual review recommended (sense 0 ≥ 4 words): {review}")


def filter_by_min_s0(anomalous, min_s0):
    return [e for e in anomalous
            if word_count(e['short_gloss'].split(';')[0].strip()) >= min_s0]


def cmd_dry_run(conn, limit=20, min_s0=4):
    entries = fetch_corpus_entries(conn)
    anomalous = filter_by_min_s0([e for e in entries if is_anomalous(e['short_gloss'])], min_s0)

    shown = anomalous if limit == 0 else anomalous[:limit]
    label = f"sense 0 ≥ {min_s0} words"
    print(f"Anomalous entries ({label}): {len(anomalous)}"
          + (f" (showing first {len(shown)})" if limit and len(anomalous) > limit else ""))
    print()

    for e in shown:
        senses = [s.strip() for s in e['short_gloss'].split(';') if s.strip()]
        wcs = [word_count(s) for s in senses]
        new_gloss, changed = reorder_senses(e['short_gloss'])
        new_senses = [s.strip() for s in new_gloss.split(';') if s.strip()]
        print(f"{e['strongs_id']}  {e['lemma']}")
        print(f"  BEFORE: {' | '.join('%s(%dw)' % (s, wc) for s, wc in zip(senses, wcs))}")
        new_wcs = [word_count(s) for s in new_senses]
        print(f"  AFTER:  {' | '.join('%s(%dw)' % (s, wc) for s, wc in zip(new_senses, new_wcs))}")
        print()


def cmd_apply(conn, min_s0=4):
    entries = fetch_corpus_entries(conn)
    anomalous = filter_by_min_s0([e for e in entries if is_anomalous(e['short_gloss'])], min_s0)
    print(f"Applying fix to entries where sense 0 ≥ {min_s0} words ({len(anomalous)} entries)")

    updates = []
    for e in anomalous:
        new_gloss, changed = reorder_senses(e['short_gloss'])
        if changed:
            updates.append((new_gloss, e['id']))

    if not updates:
        print("Nothing to update.")
        return

    print(f"Writing {len(updates)} updates to DB...")
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "UPDATE lexeme_meaning SET short_gloss = data.gloss FROM (VALUES %s) AS data(gloss, id) WHERE lexeme_meaning.id = data.id",
            updates
        )
    conn.commit()
    print(f"Done. {len(updates)} entries updated.")
    print()
    print("Next steps:")
    print("  1. Regenerate LITE glosses: python scripts/generate_lite_glosses.py --reset")
    print("  2. Re-run C1 for 1 Peter:  python scripts/run_c1.py --reset && python scripts/run_c1.py --submit")


def main():
    parser = argparse.ArgumentParser(
        description="Fix corpus short_gloss sense ordering — put shortest (primary) sense first"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change (default: first 20 entries)")
    parser.add_argument("--stats",   action="store_true",
                        help="Distribution report only")
    parser.add_argument("--apply",   action="store_true",
                        help="Write changes to DB")
    parser.add_argument("--limit",   type=int, default=20,
                        help="Rows to show in --dry-run (0 = all, default 20)")
    parser.add_argument("--min-s0",  type=int, default=4, metavar="N",
                        help="Only fix entries where sense 0 has ≥ N words (default 4 — safe tier)")
    args = parser.parse_args()

    print(f"Connecting to {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = get_conn()

    min_s0 = args.min_s0

    if args.stats:
        cmd_stats(conn)
    elif args.apply:
        cmd_apply(conn, min_s0=min_s0)
    else:
        # Default: dry-run
        cmd_dry_run(conn, limit=args.limit, min_s0=min_s0)

    conn.close()


if __name__ == "__main__":
    main()
