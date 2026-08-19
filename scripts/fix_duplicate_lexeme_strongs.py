"""
fix_duplicate_lexeme_strongs.py

Finds all lexeme rows sharing the same strongs_id, picks the best row to keep
(richest data: most meanings, non-zero frequency, has part_of_speech), migrates
all references from the gap rows to the keeper, then deletes the gap rows.

Run: python scripts/fix_duplicate_lexeme_strongs.py [--dry-run]

Dry-run (default): prints what would happen, makes no changes.
Live run:          pass --live to commit changes.
"""

import argparse
import os
import pathlib
import psycopg2

def load_dotenv(env_path):
    """Parse a .env file and load vars into os.environ (no dependencies needed)."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

# Load .env from project root (one level up from scripts/)
_project_root = pathlib.Path(__file__).parent.parent
load_dotenv(_project_root / ".env")

def _build_default_url():
    # Support common .env variable names — check most specific first
    if url := os.environ.get("DATABASE_URL"):
        return url

    # Spring Boot datasource URL — convert jdbc: to psycopg2 format
    jdbc = os.environ.get("SPRING_DATASOURCE_URL", "")
    if jdbc.startswith("jdbc:postgresql://"):
        jdbc_url = jdbc[len("jdbc:"):]
        user     = os.environ.get("SPRING_DATASOURCE_USERNAME", "postgres")
        password = os.environ.get("SPRING_DATASOURCE_PASSWORD", "postgres")
        # inject credentials into URL
        at = jdbc_url.find("@")
        host_part = jdbc_url[len("postgresql://"):] if at == -1 else jdbc_url[at+1:]
        return f"postgresql://{user}:{password}@{host_part}"

    host     = os.environ.get("DB_HOST",     os.environ.get("SPRING_DATASOURCE_HOST", "localhost"))
    port     = os.environ.get("DB_PORT",     "5432")
    name     = os.environ.get("DB_NAME",     os.environ.get("POSTGRES_DB",       "interlinear_bible"))
    user     = os.environ.get("DB_USER",     os.environ.get("POSTGRES_USER",     os.environ.get("SPRING_DATASOURCE_USERNAME", "postgres")))
    password = os.environ.get("DB_PASS",     os.environ.get("DB_PASSWORD",       os.environ.get("POSTGRES_PASSWORD", os.environ.get("SPRING_DATASOURCE_PASSWORD", "postgres"))))
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"

DEFAULT_DB_URL = _build_default_url()

def connect(db_url):
    return psycopg2.connect(db_url)

def find_duplicates(cur):
    cur.execute("""
        SELECT strongs_id, array_agg(id ORDER BY id) AS ids
        FROM lexeme
        WHERE strongs_id IS NOT NULL
        GROUP BY strongs_id
        HAVING COUNT(*) > 1
        ORDER BY strongs_id
    """)
    return cur.fetchall()

def score_row(row):
    """Higher score = better keeper candidate."""
    score = 0
    score += (row['meaning_count'] or 0) * 10
    score += (row['occurrence_count'] or 0)
    score += (row['verse_word_count'] or 0)
    if row['part_of_speech']:
        score += 5
    if row['frequency_nt'] and row['frequency_nt'] > 0:
        score += 3
    return score

def get_row_detail(cur, lexeme_id):
    cur.execute("""
        SELECT
            l.id, l.strongs_id, l.lemma, l.transliteration,
            l.part_of_speech, l.frequency_nt,
            (SELECT COUNT(*) FROM lexeme_meaning   WHERE lexeme_id = l.id) AS meaning_count,
            (SELECT COUNT(*) FROM lexeme_occurrence WHERE lexeme_id = l.id) AS occurrence_count,
            (SELECT COUNT(*) FROM verse_word        WHERE lexeme_id = l.id) AS verse_word_count
        FROM lexeme l
        WHERE l.id = %s
    """, (lexeme_id,))
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, cur.fetchone()))

def migrate_and_delete(cur, gap_id, keeper_id, dry_run):
    print(f"    Migrating lexeme {gap_id} → {keeper_id}")

    # Move verse_word references
    cur.execute("SELECT COUNT(*) FROM verse_word WHERE lexeme_id = %s", (gap_id,))
    vw_count = cur.fetchone()[0]
    if vw_count:
        print(f"      verse_word: {vw_count} rows")
        if not dry_run:
            cur.execute("UPDATE verse_word SET lexeme_id = %s WHERE lexeme_id = %s", (keeper_id, gap_id))

    # Move meanings (skip if keeper already has same source)
    cur.execute("SELECT source FROM lexeme_meaning WHERE lexeme_id = %s", (gap_id,))
    gap_sources = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT source FROM lexeme_meaning WHERE lexeme_id = %s", (keeper_id,))
    keeper_sources = {r[0] for r in cur.fetchall()}
    moveable = gap_sources - keeper_sources
    droppable = gap_sources & keeper_sources
    if moveable:
        print(f"      lexeme_meaning: move sources {moveable}")
        if not dry_run:
            cur.execute("""
                UPDATE lexeme_meaning SET lexeme_id = %s
                WHERE lexeme_id = %s AND source = ANY(%s)
            """, (keeper_id, gap_id, list(moveable)))
    if droppable:
        print(f"      lexeme_meaning: drop duplicate sources {droppable}")
        if not dry_run:
            cur.execute("""
                DELETE FROM lexeme_meaning
                WHERE lexeme_id = %s AND source = ANY(%s)
            """, (gap_id, list(droppable)))

    # Move occurrences (skip duplicates)
    cur.execute("SELECT verse_id FROM lexeme_occurrence WHERE lexeme_id = %s", (gap_id,))
    gap_verse_ids = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT verse_id FROM lexeme_occurrence WHERE lexeme_id = %s", (keeper_id,))
    keeper_verse_ids = {r[0] for r in cur.fetchall()}
    moveable_occ = gap_verse_ids - keeper_verse_ids
    if moveable_occ:
        print(f"      lexeme_occurrence: move {len(moveable_occ)} verses")
        if not dry_run:
            cur.execute("""
                UPDATE lexeme_occurrence SET lexeme_id = %s
                WHERE lexeme_id = %s AND verse_id = ANY(%s)
            """, (keeper_id, gap_id, list(moveable_occ)))
    dup_occ = gap_verse_ids & keeper_verse_ids
    if dup_occ:
        print(f"      lexeme_occurrence: drop {len(dup_occ)} duplicate verses")
        if not dry_run:
            cur.execute("""
                DELETE FROM lexeme_occurrence
                WHERE lexeme_id = %s AND verse_id = ANY(%s)
            """, (gap_id, list(dup_occ)))

    # Delete gap row
    print(f"      DELETE lexeme id={gap_id}")
    if not dry_run:
        cur.execute("DELETE FROM lexeme WHERE id = %s", (gap_id,))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Commit changes (default is dry-run)")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL,
                        help="PostgreSQL connection URL (default: %(default)s)")
    args = parser.parse_args()
    dry_run = not args.live

    import sys
    log_path = pathlib.Path(__file__).parent / "fix_duplicate_lexeme_strongs.log"
    log_file = open(log_path, "w", encoding="utf-8")
    _real_stdout = sys.stdout

    class Tee:
        def write(self, msg): _real_stdout.write(msg); log_file.write(msg)
        def flush(self): _real_stdout.flush(); log_file.flush()

    sys.stdout = Tee()

    print(f"{'DRY RUN' if dry_run else 'LIVE RUN'} — fix_duplicate_lexeme_strongs.py")
    print(f"DB: {args.db_url}\n")

    conn = connect(args.db_url)
    cur = conn.cursor()

    duplicates = find_duplicates(cur)
    if not duplicates:
        print("No duplicate strongs_ids found. Nothing to do.")
        return

    print(f"Found {len(duplicates)} strongs_id(s) with duplicate lexeme rows:\n")
    for strongs_id, ids in duplicates:
        print(f"  {strongs_id}: lexeme ids {ids}")
        rows = [get_row_detail(cur, lid) for lid in ids]
        for r in rows:
            print(f"    id={r['id']}  lemma={r['lemma']!r:30s}  "
                  f"pos={r['part_of_speech'] or '':12s}  freq={r['frequency_nt'] or 0:4d}  "
                  f"meanings={r['meaning_count']}  occ={r['occurrence_count']}  vw={r['verse_word_count']}")

        scored = sorted(rows, key=score_row, reverse=True)
        keeper = scored[0]
        gaps   = scored[1:]
        print(f"    → KEEP id={keeper['id']} ({keeper['lemma']!r})")
        for gap in gaps:
            print(f"    → DROP id={gap['id']} ({gap['lemma']!r})")
            migrate_and_delete(cur, gap['id'], keeper['id'], dry_run)
        print()

    if dry_run:
        print("Dry run complete. Run with --live to apply changes.")
        conn.rollback()
    else:
        conn.commit()
        print("Changes committed.")
    cur.close()
    conn.close()
    print(f"\nFull log written to: {log_path}")

if __name__ == "__main__":
    main()
