#!/usr/bin/env python3
"""
import_ult_alignment.py — Import word-level alignment data from the
unfoldingWord ULT (Literal Translation) USFM files into verse_word_trans_gloss.

Source: data/unfoldingWord/en_ult/  (USFM files with \zaln-s markers)
Greek base: SBLGNT (matched via Strong's ID + occurrence number)

Each \zaln-s marker provides:
  x-strong="G17220"    — Strong's ID (zero-padded 4-digit + trailing 0)
  x-occurrence="2"     — which occurrence of this lemma in the verse
  x-occurrences="3"    — total occurrences in this verse
  x-content="ἐν"       — Greek surface form (for verification)

Usage:
  python scripts/import_ult_alignment.py
  python scripts/import_ult_alignment.py --dry-run
  python scripts/import_ult_alignment.py --force
  python scripts/import_ult_alignment.py --book JHN   # single book

Requirements:
  pip install psycopg2-binary python-dotenv
"""

import os, sys, re, argparse
from pathlib import Path
from collections import defaultdict

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

ULT_DIR = Path(__file__).parent.parent / "data" / "unfoldingWord" / "en_ult"
TRANSLATION_CODE = "ULT"

# Paratext file number → DB book_id (Paratext starts at 41 for Matthew)
PARATEXT_TO_DB = {n: n - 1 for n in range(41, 68)}  # 41→40, 42→41, ..., 67→66

# Book abbreviation → Paratext number (from filenames like "41-MAT.usfm")
ABBREV_TO_PARATEXT = {
    "MAT": 41, "MRK": 42, "LUK": 43, "JHN": 44, "ACT": 45,
    "ROM": 46, "1CO": 47, "2CO": 48, "GAL": 49, "EPH": 50,
    "PHP": 51, "COL": 52, "1TH": 53, "2TH": 54, "1TI": 55,
    "2TI": 56, "TIT": 57, "PHM": 58, "HEB": 59, "JAS": 60,
    "1PE": 61, "2PE": 62, "1JN": 63, "2JN": 64, "3JN": 65,
    "JUD": 66, "REV": 67,
}

# Regex patterns (compiled for use with .search(string, pos))
ZALN_S_START = re.compile(r'\\zaln-s\b')
ZALN_S_HEADER = re.compile(
    r'\\zaln-s\s+\|'
    r'x-strong="([^"]+)"'
    r'[^|]*'
    r'x-occurrence="(\d+)"'
    r'[^|]*'
    r'x-occurrences="(\d+)"'
)
WORD_RE = re.compile(r'\\w ([^|]+)\|[^\\]*\\w\*')
CHAPTER_RE = re.compile(r'\\c\s+(\d+)')
VERSE_RE = re.compile(r'\\v\s+(\d+)')
ZALN_E_STR = '\\zaln-e\\*'


def normalize_strongs(raw: str) -> str:
    """
    Normalize ULT Strong's IDs to our DB format.
    'G17220' → 'G1722', 'G09760' → 'G976', 'G00110' → 'G11'
    H-prefixed are OT — skip.
    """
    if not raw or not raw.startswith("G"):
        return None
    try:
        digits = int(raw[1:5])  # take first 4 digits after 'G', strip leading zeros
        return f"G{digits}"
    except (ValueError, IndexError):
        return None


def build_db_lookup(conn, book_ids):
    """
    Build {(book_id, chapter, verse_num, strongs_id, occurrence): vw_id}
    where occurrence is 1-based index of that strongs_id within the verse by position order.
    """
    print("  Querying verse_word positions and Strong's IDs...")

    placeholders = ",".join(["%s"] * len(book_ids))
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"""
            SELECT vw.id, b.id AS book_id, v.chapter, v.verse_num, vw.position, l.strongs_id
            FROM verse_word vw
            JOIN verse v ON v.id = vw.verse_id
            JOIN book b ON b.id = v.book_id
            JOIN lexeme l ON l.id = vw.lexeme_id
            WHERE b.id IN ({placeholders})
              AND l.strongs_id IS NOT NULL
            ORDER BY b.id, v.chapter, v.verse_num, vw.position
        """, book_ids)
        rows = cur.fetchall()

    print(f"  {len(rows):,} verse_word rows fetched")

    # Group by verse, then build occurrence-based lookup
    # verse_strongs[(book_id, chapter, verse_num, strongs_id)] = [vw_id, vw_id, ...]
    verse_strongs = defaultdict(list)
    for row in rows:
        key = (row["book_id"], row["chapter"], row["verse_num"], row["strongs_id"])
        verse_strongs[key].append(row["id"])

    # Now flatten to occurrence-keyed lookup
    lookup = {}
    for (book_id, chapter, verse_num, strongs_id), vw_ids in verse_strongs.items():
        for idx, vw_id in enumerate(vw_ids, start=1):
            lookup[(book_id, chapter, verse_num, strongs_id, idx)] = vw_id

    print(f"  {len(lookup):,} occurrence-keyed lookup entries")
    return lookup


def parse_usfm_file(usfm_path: Path, db_book_id: int, lookup: dict):
    """
    Parse a single USFM file and extract (vw_id, english_phrase) pairs.
    Returns (entries, skipped_no_strongs, skipped_no_match).
    """
    content = usfm_path.read_text(encoding="utf-8")

    entries = []
    skipped_no_strongs = 0
    skipped_no_match = 0

    current_chapter = 0
    current_verse = 0
    pos = 0
    n = len(content)

    while pos < n:
        # Find next interesting marker (compiled patterns support search(string, pos))
        ch_m = CHAPTER_RE.search(content, pos)
        v_m  = VERSE_RE.search(content, pos)
        z_m  = ZALN_S_START.search(content, pos)

        # Pick the earliest
        candidates = [(m.start(), m, t) for m, t in [
            (ch_m, 'c'), (v_m, 'v'), (z_m, 'z')
        ] if m is not None]

        if not candidates:
            break

        candidates.sort()
        nxt_start, nxt_m, nxt_type = candidates[0]

        if nxt_type == 'c':
            current_chapter = int(nxt_m.group(1))
            current_verse = 0
            pos = nxt_m.end()
            continue

        if nxt_type == 'v':
            current_verse = int(nxt_m.group(1))
            pos = nxt_m.end()
            continue

        # nxt_type == 'z': process a \zaln-s...\zaln-e\* block
        block_start = nxt_m.start()

        # For nested zaln blocks, count depth to find the outermost end
        zaln_end_idx = content.find(ZALN_E_STR, block_start)
        if zaln_end_idx == -1:
            pos = block_start + 7
            continue

        block_end = zaln_end_idx + len(ZALN_E_STR)
        block = content[block_start:block_end]

        # Parse the zaln-s header attributes
        hdr = ZALN_S_HEADER.match(block)
        if not hdr:
            pos = block_end
            continue

        raw_strong = hdr.group(1)
        occurrence = int(hdr.group(2))

        strongs_id = normalize_strongs(raw_strong)
        if strongs_id is None:
            skipped_no_strongs += 1
            pos = block_end
            continue

        # Extract English words from \w word|...\w* tags in this block
        words = [wm.group(1).strip() for wm in WORD_RE.finditer(block) if wm.group(1).strip()]
        phrase = " ".join(words)
        if not phrase:
            pos = block_end
            continue

        # Look up the verse_word_id by (book, chapter, verse, strongs, occurrence)
        vw_id = lookup.get((db_book_id, current_chapter, current_verse, strongs_id, occurrence))
        if vw_id is None:
            skipped_no_match += 1
            pos = block_end
            continue

        entries.append((vw_id, TRANSLATION_CODE, phrase))
        pos = block_end

    return entries, skipped_no_strongs, skipped_no_match


def get_nt_usfm_files(book_filter=None):
    """Return list of (paratext_num, db_book_id, path) for NT books."""
    files = []
    for usfm_file in sorted(ULT_DIR.glob("*.usfm")):
        # Parse filename like "41-MAT.usfm"
        m = re.match(r"^(\d+)-([A-Z0-9]+)\.usfm$", usfm_file.name)
        if not m:
            continue
        paratext_num = int(m.group(1))
        abbrev = m.group(2)

        if paratext_num not in PARATEXT_TO_DB:
            continue  # OT

        if book_filter and abbrev.upper() != book_filter.upper():
            continue

        db_book_id = PARATEXT_TO_DB[paratext_num]
        files.append((paratext_num, abbrev, db_book_id, usfm_file))
    return files


def already_imported(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM verse_word_trans_gloss WHERE translation_code = %s",
            (TRANSLATION_CODE,)
        )
        return cur.fetchone()[0] > 0


def main():
    parser = argparse.ArgumentParser(
        description="Import ULT USFM alignment data into verse_word_trans_gloss"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and report without writing to DB")
    parser.add_argument("--force", action="store_true",
                        help="Re-import even if rows already exist (upserts)")
    parser.add_argument("--book", metavar="ABB",
                        help="Import only one book (e.g. JHN, ROM)")
    args = parser.parse_args()

    nt_files = get_nt_usfm_files(args.book)
    if not nt_files:
        print(f"No NT USFM files found in {ULT_DIR}")
        sys.exit(1)

    print(f"ULT alignment importer")
    print(f"Connecting to {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)

    if not args.dry_run and not args.force and already_imported(conn):
        print(f"  ULT alignment already in DB. Use --force to re-import.")
        conn.close()
        return

    book_ids = [db_book_id for _, _, db_book_id, _ in nt_files]
    lookup = build_db_lookup(conn, book_ids)

    all_entries = []
    total_skipped_strongs = 0
    total_skipped_match = 0

    for paratext_num, abbrev, db_book_id, usfm_path in nt_files:
        print(f"  Parsing {usfm_path.name} (book_id={db_book_id})...")
        entries, s_strongs, s_match = parse_usfm_file(usfm_path, db_book_id, lookup)
        print(f"    Matched: {len(entries):,}  "
              f"No-Strongs: {s_strongs}  "
              f"No-match: {s_match}")
        all_entries.extend(entries)
        total_skipped_strongs += s_strongs
        total_skipped_match += s_match

    # Deduplicate — nested zaln blocks can produce two entries for the same (vw_id, code).
    # Keep the last entry seen (outermost block tends to give the fuller phrase).
    raw_count = len(all_entries)
    deduped: dict = {}
    for vw_id, code, phrase in all_entries:
        deduped[(vw_id, code)] = phrase
    all_entries = [(vw_id, code, phrase) for (vw_id, code), phrase in deduped.items()]

    print(f"\nTotal entries: {len(all_entries):,}  (raw={raw_count:,}, deduped={raw_count - len(all_entries):,})")
    print(f"Total skipped (no Strong's): {total_skipped_strongs}")
    print(f"Total skipped (no DB match): {total_skipped_match}")

    if args.dry_run:
        print("\nDry-run — sample entries:")
        for vw_id, code, phrase in all_entries[:20]:
            print(f"  verse_word {vw_id:>7}  {code}  {phrase!r}")
        conn.close()
        return

    print(f"\nWriting {len(all_entries):,} rows to verse_word_trans_gloss...")
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO verse_word_trans_gloss (verse_word_id, translation_code, gloss)
            VALUES %s
            ON CONFLICT (verse_word_id, translation_code) DO UPDATE SET gloss = EXCLUDED.gloss
            """,
            all_entries,
            page_size=5000,
        )
    conn.commit()
    print(f"Done — {len(all_entries):,} rows upserted for {TRANSLATION_CODE}.")
    conn.close()


if __name__ == "__main__":
    main()
