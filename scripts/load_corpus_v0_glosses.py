#!/usr/bin/env python3
"""
load_corpus_v0_glosses.py — Replace lexeme_meaning.short_gloss (corpus) with
shortGloss_v0 from corpus-LITE.json.

shortGloss_v0 is the first synthesis run — cleaner, shorter senses without
the definitions, parentheticals, and grammatical labels that were added in v1.

Usage:
  python scripts/load_corpus_v0_glosses.py --dry-run   # preview changes, no DB writes
  python scripts/load_corpus_v0_glosses.py             # apply to DB

After running successfully:
  python scripts/old/populate_lexeme_sense.py --reset  # rebuild lexeme_sense from clean data
"""

import json, os, sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print('ERROR: pip install psycopg2-binary')
    sys.exit(1)

DB_CONFIG = {
    'host':     os.environ.get('DB_HOST', 'localhost'),
    'port':     int(os.environ.get('DB_PORT', 5432)),
    'dbname':   os.environ.get('DB_NAME', 'interlinear_bible_dev'),
    'user':     os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASS', 'letttech'),
}

CORPUS_JSON = Path(__file__).parent.parent / 'data' / 'corpus-LITE.json'


def load_json():
    with open(CORPUS_JSON, encoding='utf-8') as f:
        return json.load(f)


def run(dry_run: bool):
    data = load_json()
    print(f'Loaded {len(data)} entries from corpus-LITE.json')

    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Load current DB state keyed by strongs_id
    cur.execute("""
        SELECT l.strongs_id, m.id AS meaning_id, m.short_gloss AS current_gloss
        FROM lexeme_meaning m
        JOIN lexeme l ON l.id = m.lexeme_id
        WHERE m.source = 'corpus'
    """)
    db_rows = {r['strongs_id']: r for r in cur.fetchall()}
    print(f'Found {len(db_rows)} corpus rows in DB')

    updates      = []
    skipped_same = 0
    missing_v0   = 0
    missing_db   = 0

    for strongs_id, entry in data.items():
        v0 = (entry.get('shortGloss_v0') or '').strip()

        if not v0:
            missing_v0 += 1
            continue

        db_row = db_rows.get(strongs_id)
        if not db_row:
            missing_db += 1
            continue

        current = (db_row['current_gloss'] or '').strip()
        if current == v0:
            skipped_same += 1
            continue

        updates.append((v0, db_row['meaning_id'], strongs_id, current))

    print(f'\nSummary:')
    print(f'  To update:    {len(updates)}')
    print(f'  Already same: {skipped_same}')
    print(f'  Missing v0:   {missing_v0}')
    print(f'  Not in DB:    {missing_db}')

    if dry_run:
        print(f'\n[DRY RUN] First 30 changes:')
        print(f'  {"Strongs":<8} {"Current short_gloss":<55} {"v0 (new)":<55}')
        print('  ' + '-'*120)
        for v0, mid, sid, current in updates[:30]:
            print(f'  {sid:<8} {current[:53]:<55} {v0[:53]}')
        if len(updates) > 30:
            print(f'  ... and {len(updates)-30} more')
        print('\n[DRY RUN] No changes written.')
        conn.close()
        return

    # Apply updates
    psycopg2.extras.execute_values(
        cur,
        """
        UPDATE lexeme_meaning m
        SET short_gloss = data.v0
        FROM (VALUES %s) AS data(v0, meaning_id)
        WHERE m.id = data.meaning_id
        """,
        [(v0, mid) for v0, mid, sid, current in updates],
        page_size=500
    )
    conn.commit()
    print(f'\nUpdated {cur.rowcount} rows.')
    print('\nNext step: python scripts/old/populate_lexeme_sense.py --reset')
    cur.close()
    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Load shortGloss_v0 into lexeme_meaning.short_gloss')
    parser.add_argument('--dry-run', action='store_true', help='Preview — no DB writes')
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
