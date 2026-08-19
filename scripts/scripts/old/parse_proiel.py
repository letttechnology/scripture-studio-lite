#!/usr/bin/env python3
"""
parse_proiel.py — Parse PROIEL NT treebank XML and load syntactic dependency
relations into the verse_word table (dep_head_id, dep_relation).

Source: https://github.com/proiel/proiel-treebank
File:   data/proiel-treebank-master/greek-nt.xml  (or proiel-treebank/greek-nt.xml)

License: CC-BY-SA

Usage:
  # Parse only (inspect without writing to DB):
  python scripts/parse_proiel.py --dry-run

  # Load relations into DB:
  python scripts/parse_proiel.py --load

  # Inspect a specific verse:
  python scripts/parse_proiel.py --inspect "John 1:1"

Requirements:
  pip install psycopg2-binary python-dotenv
"""

import os, sys, re, argparse, unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET
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

# ── Book name mapping: PROIEL citation-part prefix → NT book_id ──────────────
# PROIEL token citation-part format: "BOOK CHAPTER.VERSE" e.g. "JOHN 1.1"
# Book prefixes are uppercase as they appear in the actual XML.
# Our DB uses book_id 40 (Matthew) … 66 (Revelation).
PROIEL_BOOK_ID = {
    "MATT":   40, "MARK":   41, "LUKE":   42, "JOHN":   43, "ACTS":   44,
    "ROM":    45, "1COR":   46, "2COR":   47, "GAL":    48, "EPH":    49,
    "PHIL":   50, "COL":    51, "1THESS": 52, "2THESS": 53, "1TIM":   54,
    "2TIM":   55, "TIT":    56, "PHILEM": 57, "HEB":    58, "JAS":    59,
    "1PET":   60, "2PET":   61, "1JOHN":  62, "2JOHN":  63, "3JOHN":  64,
    "JUDE":   65, "REV":    66,
}

# ── Locate the PROIEL NT XML file ─────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"

CANDIDATE_PATHS = [
    DATA_DIR / "proiel-treebank-master" / "greek-nt.xml",
    DATA_DIR / "proiel-treebank" / "greek-nt.xml",
    DATA_DIR / "greek-nt.xml",
    # Sometimes the repo unzips with a version tag
    *list(DATA_DIR.glob("proiel-treebank-*/greek-nt.xml")),
    *list(DATA_DIR.glob("proiel*/greek-nt.xml")),
]


def find_xml():
    for p in CANDIDATE_PATHS:
        if p.exists():
            return p
    return None


# ── Citation parsing ──────────────────────────────────────────────────────────
# PROIEL token @citation-part format: "BOOK CHAPTER.VERSE" e.g. "JOHN 1.1"

CITATION_PART_RE = re.compile(r"^([A-Z0-9]+)\s+(\d+)\.(\d+)$")


def parse_citation_part(cp):
    """
    Parse a PROIEL citation-part string like "JOHN 1.1".
    Returns (book_id, chapter, verse) or None.
    """
    m = CITATION_PART_RE.match((cp or "").strip())
    if not m:
        return None
    book_id = PROIEL_BOOK_ID.get(m.group(1))
    if book_id is None:
        return None
    return (book_id, int(m.group(2)), int(m.group(3)))


# ── PROIEL XML parse ──────────────────────────────────────────────────────────

class ProielToken:
    __slots__ = ("proiel_id", "form", "lemma", "relation",
                 "head_proiel_id", "book_id", "chapter", "verse", "position")

    def __init__(self, proiel_id, form, lemma, relation, head_proiel_id,
                 book_id, chapter, verse, position):
        self.proiel_id      = proiel_id
        self.form           = form
        self.lemma          = lemma
        self.relation       = relation
        self.head_proiel_id = head_proiel_id
        self.book_id        = book_id
        self.chapter        = chapter
        self.verse          = verse
        self.position       = position


def nfc(s):
    return unicodedata.normalize("NFC", s) if s else ""


def parse_proiel_xml(xml_path):
    """
    Parse the PROIEL NT XML file.
    Returns list[ProielToken] in verse order.

    Each token has a @citation-part attribute like "JOHN 1.1".
    Position within the verse is counted as we encounter tokens — counters
    reset whenever (book_id, chapter, verse) changes within a sentence.
    Empty tokens (no @form) and punctuation-only tokens are skipped.
    """
    print(f"Parsing {xml_path} ...")
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    tokens = []

    # Per-verse position counters — shared across all sentences
    # (book_id, chapter, verse) → count of tokens seen so far
    verse_pos_counter = {}

    for sentence in root.iter("sentence"):
        for tok in sentence.findall("token"):
            tok_id   = tok.get("id")
            form     = nfc(tok.get("form", "").strip())
            lemma    = nfc(tok.get("lemma", "").strip())
            # Relations are lowercase in PROIEL (pred, sub, obj, xobj, atr, adv …)
            relation = (tok.get("relation") or "").strip()
            head_id  = tok.get("head-id") or "0"

            # Skip empty tokens (null copula, traces) — no @form
            if not form or not tok_id:
                continue

            # Parse citation-part: "JOHN 1.1", "MATT 5.3", etc.
            cp  = tok.get("citation-part", "")
            loc = parse_citation_part(cp)
            if loc is None:
                continue  # OT or unrecognised book

            book_id, chapter, verse = loc

            # Per-verse 1-based position
            key = (book_id, chapter, verse)
            pos = verse_pos_counter.get(key, 0) + 1
            verse_pos_counter[key] = pos

            tokens.append(ProielToken(
                proiel_id      = int(tok_id),
                form           = form,
                lemma          = lemma,
                relation       = relation or None,
                head_proiel_id = int(head_id) if head_id and head_id != "0" else None,
                book_id        = book_id,
                chapter        = chapter,
                verse          = verse,
                position       = pos,
            ))

    print(f"  Parsed {len(tokens):,} tokens from {xml_path.name}")
    return tokens


# ── DB matching ───────────────────────────────────────────────────────────────

def load_verse_words(conn, book_id):
    """
    Load all verse_word rows for one book.
    Returns {(chapter, verse, position): verse_word_id}
    """
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT vw.id, v.chapter, v.verse_num, vw.position
            FROM verse_word vw
            JOIN verse v ON v.id = vw.verse_id
            JOIN book  b ON b.id = v.book_id
            WHERE b.id = %s
            ORDER BY v.chapter, v.verse_num, vw.position
        """, (book_id,))
        result = {}
        for row in cur.fetchall():
            key = (row["chapter"], row["verse_num"], row["position"])
            result[key] = row["id"]
    return result


def match_tokens_to_db(proiel_tokens, vw_map):
    """
    For each PROIEL token, find the matching verse_word id by
    (chapter, verse, position).

    Returns {proiel_id: verse_word_id}
    """
    mapping = {}
    unmatched = 0

    for tok in proiel_tokens:
        key = (tok.chapter, tok.verse, tok.position)
        vw_id = vw_map.get(key)
        if vw_id is not None:
            mapping[tok.proiel_id] = vw_id
        else:
            unmatched += 1

    if unmatched:
        print(f"  ⚠  {unmatched} PROIEL tokens had no matching verse_word row")

    return mapping


# ── DB load ───────────────────────────────────────────────────────────────────

def load_into_db(conn, all_tokens):
    """
    Write dep_head_id and dep_relation into verse_word.
    Processes one book at a time.
    """
    # Group by book_id
    by_book = defaultdict(list)
    for tok in all_tokens:
        by_book[tok.book_id].append(tok)

    total_updated = 0

    for book_id in sorted(by_book.keys()):
        book_tokens = by_book[book_id]
        print(f"  Loading book {book_id} ({len(book_tokens):,} tokens)...")

        vw_map = load_verse_words(conn, book_id)

        # Build proiel_id → verse_word_id for this book
        pid_to_vwid = match_tokens_to_db(book_tokens, vw_map)

        # Build update rows: (dep_head_vw_id, dep_relation, verse_word_id)
        updates = []
        for tok in book_tokens:
            vw_id = pid_to_vwid.get(tok.proiel_id)
            if vw_id is None:
                continue

            # Resolve head to verse_word_id (may be in same book only — cross-sentence
            # heads are extremely rare and would map to None safely)
            head_vw_id = None
            if tok.head_proiel_id is not None:
                head_vw_id = pid_to_vwid.get(tok.head_proiel_id)

            updates.append((head_vw_id, tok.relation, vw_id))

        if not updates:
            continue

        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE verse_word
                   SET dep_head_id  = %s,
                       dep_relation = %s
                 WHERE id = %s
                """,
                updates,
                page_size=2000,
            )
        conn.commit()
        total_updated += len(updates)
        print(f"    ✓  {len(updates):,} rows updated")

    print(f"\nTotal verse_word rows updated: {total_updated:,}")


# ── Inspect helper ────────────────────────────────────────────────────────────

def inspect_verse(conn, verse_ref):
    """
    Print syntactic annotation for a verse, e.g. "John 1:1".
    """
    # Parse "John 1:1" or "43 1 1"
    m = re.match(r"(\w+)\s+(\d+):(\d+)", verse_ref)
    if not m:
        print(f"Cannot parse verse ref: {verse_ref!r}")
        return

    book_name, chapter, verse = m.group(1), int(m.group(2)), int(m.group(3))
    # Resolve book name to book_id
    name_map = {v: k for k, v in {
        "Matthew": 40, "Mark": 41, "Luke": 42, "John": 43, "Acts": 44,
        "Romans": 45, "1Corinthians": 46, "2Corinthians": 47,
        "Galatians": 48, "Ephesians": 49, "Philippians": 50,
        "Colossians": 51, "1Thessalonians": 52, "2Thessalonians": 53,
        "1Timothy": 54, "2Timothy": 55, "Titus": 56, "Philemon": 57,
        "Hebrews": 58, "James": 59, "1Peter": 60, "2Peter": 61,
        "1John": 62, "2John": 63, "3John": 64, "Jude": 65, "Revelation": 66,
    }.items()}
    # Also accept "John" → 43
    short_map = {
        "Matt": 40, "Mark": 41, "Luke": 42, "John": 43, "Acts": 44,
        "Rom": 45, "Rev": 66, "Jas": 59, "Jude": 65,
    }
    book_id = short_map.get(book_name)
    if book_id is None:
        for name, bid in name_map.items():
            if name.lower().startswith(book_name.lower()):
                book_id = bid
                break
    if book_id is None:
        print(f"Unknown book: {book_name!r}")
        return

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT vw.id, vw.surface_form, vw.pos_code, vw.tense, vw.mood, vw.voice,
                   vw.dep_relation, vw.dep_head_id, vw.position,
                   l.strongs_id,
                   head.surface_form AS head_form
            FROM verse_word vw
            JOIN verse v ON v.id = vw.verse_id
            JOIN book  b ON b.id = v.book_id
            LEFT JOIN lexeme l ON l.id = vw.lexeme_id
            LEFT JOIN verse_word head ON head.id = vw.dep_head_id
            WHERE b.id = %s AND v.chapter = %s AND v.verse_num = %s
            ORDER BY vw.position
        """, (book_id, chapter, verse))
        rows = cur.fetchall()

    if not rows:
        print(f"No data for {verse_ref} (book_id={book_id})")
        return

    print(f"\n{verse_ref}:")
    print(f"  {'pos':>3}  {'form':20} {'strongs':8} {'relation':12} {'head':20} {'tense/mood/voice'}")
    print(f"  {'-'*3}  {'-'*20} {'-'*8} {'-'*12} {'-'*20} {'-'*20}")
    for r in rows:
        morph = " ".join(filter(None, [r["tense"], r["mood"], r["voice"]]))
        head  = r["head_form"] or "—"
        rel   = r["dep_relation"] or "—"
        form  = (r["surface_form"] or "").encode("utf-8", "replace").decode("utf-8")
        print(f"  {r['position']:>3}  {form:20} {r['strongs_id'] or '?':8} {rel:12} {head:20} {morph}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Parse PROIEL NT treebank and load syntactic dependency relations"
    )
    parser.add_argument("--dry-run",  action="store_true",
                        help="Parse XML and report stats, no DB writes")
    parser.add_argument("--load",     action="store_true",
                        help="Write dep_head_id/dep_relation to verse_word")
    parser.add_argument("--inspect",  type=str, default="",
                        help='Show relations for a verse, e.g. --inspect "John 1:1"')
    parser.add_argument("--xml",      type=str, default="",
                        help="Path to PROIEL NT XML (auto-detected if omitted)")
    args = parser.parse_args()

    # ── Inspect mode (needs DB, no XML) ─────────────────────────────────────
    if args.inspect:
        conn = psycopg2.connect(**DB_CONFIG)
        inspect_verse(conn, args.inspect)
        conn.close()
        return

    # ── Locate XML ───────────────────────────────────────────────────────────
    xml_path = Path(args.xml) if args.xml else find_xml()
    if xml_path is None or not xml_path.exists():
        print("ERROR: PROIEL NT XML not found.")
        print("Expected location: data/proiel-treebank-master/greek-nt.xml")
        print("Download from: https://github.com/proiel/proiel-treebank")
        print("  → Code → Download ZIP → unzip into data/")
        print("Then re-run this script.")
        sys.exit(1)

    # ── Parse ────────────────────────────────────────────────────────────────
    all_tokens = parse_proiel_xml(xml_path)

    if args.dry_run:
        # Report stats by book
        from collections import Counter
        book_counts = Counter(t.book_id for t in all_tokens)
        rel_counts  = Counter(t.relation for t in all_tokens if t.relation)
        print(f"\nToken count by book:")
        for bid in sorted(book_counts):
            print(f"  book {bid}: {book_counts[bid]:,}")
        print(f"\nTop 20 relations:")
        for rel, cnt in rel_counts.most_common(20):
            print(f"  {rel:12} {cnt:,}")
        print("\n(dry-run: no DB writes)")
        return

    if not args.load:
        parser.print_help()
        return

    # ── Load into DB ─────────────────────────────────────────────────────────
    print(f"\nConnecting to DB {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)
    load_into_db(conn, all_tokens)
    conn.close()
    print("\nDone. Run: python scripts/parse_proiel.py --inspect \"John 1:1\"")


if __name__ == "__main__":
    main()
