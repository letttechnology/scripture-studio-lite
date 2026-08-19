#!/usr/bin/env python3
"""
export_gloss_set.py — Export a named gloss set to a reviewable file.

Usage:
  python scripts/export_gloss_set.py --name lite_auto            # export LITE (default)
  python scripts/export_gloss_set.py --name lite_auto --fmt csv  # CSV spreadsheet
  python scripts/export_gloss_set.py --name lite_auto --fmt json # JSON indexed by verse_word_id

Output (default TSV, opens in Excel/Sheets):
  data/gloss-set-{name}.tsv

Columns:
  strongs_id | lemma | book | chapter | verse | position | surface_form
  tense | voice | mood | person | number | gender | case | lite_gloss | corpus_gloss

Sorted by strongs_id then book/chapter/verse so you can scan all occurrences of one word.
"""

import os, sys, csv, json, argparse
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

QUERY = """
SELECT
    l.strongs_id,
    l.lemma,
    b.name        AS book_name,
    b.abbreviation AS book_abbrev,
    v.chapter      AS chapter,
    v.verse_num    AS verse,
    vw.position,
    vw.surface_form,
    vw.tense,
    vw.voice,
    vw.mood,
    vw.person,
    vw.number,
    vw.gender,
    vw.grammatical_case,
    gse.gloss     AS lite_gloss,
    COALESCE(
        (SELECT lm.short_gloss FROM lexeme_meaning lm
         WHERE lm.lexeme_id = vw.lexeme_id AND lm.source = 'corpus' LIMIT 1),
        vw.english_gloss
    ) AS corpus_gloss
FROM gloss_set_entry gse
JOIN gloss_set gs      ON gs.id = gse.gloss_set_id
JOIN verse_word vw     ON vw.id = gse.verse_word_id
JOIN verse v           ON v.id  = vw.verse_id
JOIN book b            ON b.id  = v.book_id
LEFT JOIN lexeme l     ON l.id  = vw.lexeme_id
WHERE gs.name = %(name)s
ORDER BY l.strongs_id NULLS LAST, b.display_order, v.chapter, v.verse_num, vw.position
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="lite_auto", help="Gloss set name")
    parser.add_argument("--fmt",  default="tsv", choices=["tsv", "csv", "json"])
    parser.add_argument("--out",  default=None, help="Output file (default: data/gloss-set-{name}.{fmt})")
    args = parser.parse_args()

    out_path = args.out or str(Path(__file__).parent.parent / "data" / f"gloss-set-{args.name}.{args.fmt}")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to DB {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True

    print(f"Fetching gloss set '{args.name}'...")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(QUERY, {"name": args.name})
        rows = cur.fetchall()

    conn.close()
    print(f"  {len(rows):,} rows fetched")

    if args.fmt == "json":
        # Index by verse_word_id equivalent (book+ch+v+pos) for easy lookup
        data = {}
        for row in rows:
            key = f"{row['book_abbrev']}{row['chapter']}:{row['verse']}#{row['position']}"
            data[key] = {
                "strongs":    row["strongs_id"],
                "lemma":      row["lemma"],
                "surface":    row["surface_form"],
                "tense":      row["tense"],
                "voice":      row["voice"],
                "mood":       row["mood"],
                "person":     row["person"],
                "number":     row["number"],
                "gender":     row["gender"],
                "case":       row["grammatical_case"],
                "liteGloss":  row["lite_gloss"],
                "corpusGloss": row["corpus_gloss"],
            }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    else:
        delim = "\t" if args.fmt == "tsv" else ","
        fields = [
            "strongs_id", "lemma", "book_abbrev", "chapter", "verse", "position",
            "surface_form", "tense", "voice", "mood", "person", "number", "gender",
            "grammatical_case", "lite_gloss", "corpus_gloss",
        ]
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter=delim, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    print(f"  Written to: {out_path}")
    print()
    print("Open the TSV in Excel or Google Sheets to review all LITE glosses.")
    print("Sort by 'strongs_id' to see all forms of one word together.")

if __name__ == "__main__":
    main()
