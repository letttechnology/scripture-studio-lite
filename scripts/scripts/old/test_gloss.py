#!/usr/bin/env python3
"""
test_gloss.py — Diagnostic tool for inspecting LITE gloss quality per lemma.

Shows the lexeme sense entries, every distinct morphological form and its current
gloss, and sample NT verses — so you can spot incorrect glosses without scanning
all 138K rows manually.

Usage:
  python scripts/test_gloss.py G4160           # look up by Strong's ID
  python scripts/test_gloss.py G4160 --verses  # include sample verses (5 per form)
  python scripts/test_gloss.py poieo           # search by transliteration
  python scripts/test_gloss.py do              # search by English gloss keyword
  python scripts/test_gloss.py --top [N]       # list top N most frequent NT lemmas (default 50)
  python scripts/test_gloss.py --wrong         # show glosses that look suspicious

Requirements:
  pip install psycopg2-binary python-dotenv
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

BOOK_ABBREVS = {
    40: "Matt", 41: "Mark", 42: "Luke", 43: "John", 44: "Acts",
    45: "Rom",  46: "1Cor", 47: "2Cor", 48: "Gal",  49: "Eph",
    50: "Phil", 51: "Col",  52: "1Th",  53: "2Th",  54: "1Tim",
    55: "2Tim", 56: "Tit",  57: "Phm",  58: "Heb",  59: "Jas",
    60: "1Pet", 61: "2Pet", 62: "1Jn",  63: "2Jn",  64: "3Jn",
    65: "Jude", 66: "Rev",
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def gloss_set_id(cur):
    cur.execute("SELECT id FROM gloss_set WHERE name = 'lite_auto' LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("ERROR: 'lite_auto' gloss set not found. Run generate_lite_glosses.py first.")
        sys.exit(1)
    return row["id"]


# ── Lookup by Strong's ID ─────────────────────────────────────────────────────

def find_lexeme_by_strongs(cur, strongs_id):
    """Normalize input (e.g. g4160 → G4160) and fetch lexeme row."""
    sid = strongs_id.upper()
    if not sid.startswith("G"):
        sid = "G" + sid
    cur.execute("""
        SELECT id, strongs_id, lemma, transliteration, part_of_speech,
               frequency_nt, is_stative, is_deponent, is_polysemous
        FROM lexeme WHERE strongs_id = %s
    """, (sid,))
    return cur.fetchone()


def find_lexemes_by_transliteration(cur, query):
    """Search lexeme table by transliteration (ilike) or English gloss in lexeme_sense."""
    cur.execute("""
        SELECT DISTINCT l.id, l.strongs_id, l.lemma, l.transliteration,
               l.part_of_speech, l.frequency_nt, l.is_stative, l.is_deponent, l.is_polysemous,
               COUNT(vw.id) OVER (PARTITION BY l.id) AS token_count
        FROM lexeme l
        LEFT JOIN verse_word vw ON vw.lexeme_id = l.id
        WHERE l.transliteration ILIKE %s
        ORDER BY token_count DESC NULLS LAST
        LIMIT 10
    """, (f"%{query}%",))
    return cur.fetchall()


def find_lexemes_by_english(cur, query):
    """Search lexeme_sense.gloss for English keyword."""
    cur.execute("""
        SELECT DISTINCT l.id, l.strongs_id, l.lemma, l.transliteration,
               l.part_of_speech, l.frequency_nt, l.is_stative, l.is_deponent, l.is_polysemous,
               COUNT(vw.id) OVER (PARTITION BY l.id) AS token_count
        FROM lexeme l
        JOIN lexeme_sense ls ON ls.lexeme_id = l.id AND ls.sense_index = 0
        LEFT JOIN verse_word vw ON vw.lexeme_id = l.id
        WHERE ls.gloss ILIKE %s
        ORDER BY token_count DESC NULLS LAST
        LIMIT 10
    """, (f"%{query}%",))
    return cur.fetchall()


# ── Display helpers ───────────────────────────────────────────────────────────

def print_lexeme_header(lex):
    flags = []
    if lex["is_stative"]:   flags.append("stative")
    if lex["is_deponent"]:  flags.append("deponent")
    if lex["is_polysemous"]: flags.append("polysemous")
    flag_str = f"  [{', '.join(flags)}]" if flags else ""
    print(f"\n{'='*70}")
    print(f"  {lex['strongs_id']}  {lex['lemma']}  ({lex['transliteration'] or '—'})")
    print(f"  Part of speech: {lex['part_of_speech'] or '—'}   NT frequency: {lex['frequency_nt'] or '—'}{flag_str}")
    print(f"{'='*70}")


def print_senses(cur, lexeme_id):
    cur.execute("""
        SELECT sense_index, gloss, sense_type, nt_attested
        FROM lexeme_sense WHERE lexeme_id = %s ORDER BY sense_index
    """, (lexeme_id,))
    rows = cur.fetchall()
    if not rows:
        print("\n  [no lexeme_sense entries]")
        return
    print(f"\n  Senses (lexeme_sense):")
    for r in rows:
        marker = "●" if r["sense_index"] == 0 else " "
        attested = "" if r["nt_attested"] else " [not attested]"
        print(f"    {marker} [{r['sense_index']}] {r['gloss']}  ({r['sense_type']}){attested}")

    # Also show other source glosses for context
    cur.execute("""
        SELECT lm.source, lm.short_gloss
        FROM lexeme_meaning lm
        WHERE lm.lexeme_id = %s
          AND lm.source IN ('corpus','lsj','gk','dodson','mounce')
          AND lm.short_gloss IS NOT NULL AND lm.short_gloss <> ''
        ORDER BY CASE lm.source
            WHEN 'corpus' THEN 1 WHEN 'lsj' THEN 2 WHEN 'gk' THEN 3
            WHEN 'mounce' THEN 4 WHEN 'dodson' THEN 5 END
        LIMIT 5
    """, (lexeme_id,))
    src_rows = cur.fetchall()
    if src_rows:
        print(f"\n  Source glosses (for reference):")
        for r in src_rows:
            gloss_preview = (r["short_gloss"] or "")[:80]
            print(f"    {r['source']:<10} {gloss_preview}")


def print_gloss_table(cur, lexeme_id, gsid, show_verses=False):
    """Show every distinct morphological form and its current lite_gloss."""
    cur.execute("""
        SELECT
            vw.tense, vw.mood, vw.voice, vw.person, vw.number,
            gse.gloss,
            COUNT(*) AS token_count,
            MIN(vw.id) AS sample_token_id
        FROM verse_word vw
        LEFT JOIN gloss_set_entry gse
            ON gse.verse_word_id = vw.id AND gse.gloss_set_id = %s
        WHERE vw.lexeme_id = %s
        GROUP BY vw.tense, vw.mood, vw.voice, vw.person, vw.number, gse.gloss
        ORDER BY token_count DESC, vw.tense, vw.mood, vw.voice
    """, (gsid, lexeme_id))
    rows = cur.fetchall()

    if not rows:
        print("\n  [no tokens in NT]")
        return

    total = sum(r["token_count"] for r in rows)
    print(f"\n  Morphological forms ({total} total NT tokens):")
    print(f"  {'Tense':<12} {'Mood':<14} {'Voice':<28} {'P':<4} {'N':<10} {'Count':>5}  Gloss")
    print(f"  {'-'*12} {'-'*14} {'-'*28} {'-'*4} {'-'*10} {'-'*5}  {'-'*30}")

    for r in rows:
        tense  = r["tense"]  or "—"
        mood   = r["mood"]   or "—"
        voice  = r["voice"]  or "—"
        person = r["person"] or "—"
        number = r["number"] or "—"
        gloss  = r["gloss"]  or "[no gloss]"
        cnt    = r["token_count"]
        sample = r["sample_token_id"]

        # Flag glosses that look suspicious
        flag = ""
        low = gloss.lower()
        if any(low.endswith(s) for s in ["amed", "doed", "falled", "eated", "casted"]):
            flag = " ⚠"
        elif re.search(r'\b(am|is|are|was|were)\b$', low):
            flag = " ⚠"
        elif low in ("dos", "goes"):  # wrong 3rd singular
            flag = " ⚠"

        print(f"  {tense:<12} {mood:<14} {voice:<28} {person:<4} {number:<10} {cnt:>5}  {gloss}{flag}")

        if show_verses and sample:
            _print_sample_verses(cur, lexeme_id, gsid,
                                 r["tense"], r["mood"], r["voice"],
                                 r["person"], r["number"], limit=3)


def _print_sample_verses(cur, lexeme_id, gsid, tense, mood, voice, person, number, limit=3):
    """Print sample verse references and Greek text for a specific morphological form."""
    cur.execute("""
        SELECT
            b.abbreviation, v.chapter, v.verse_num,
            vw.surface_form, gse.gloss
        FROM verse_word vw
        JOIN verse v ON v.id = vw.verse_id
        JOIN book b ON b.id = v.book_id
        LEFT JOIN gloss_set_entry gse
            ON gse.verse_word_id = vw.id AND gse.gloss_set_id = %s
        WHERE vw.lexeme_id = %s
          AND (vw.tense IS NOT DISTINCT FROM %s)
          AND (vw.mood  IS NOT DISTINCT FROM %s)
          AND (vw.voice IS NOT DISTINCT FROM %s)
          AND (vw.person IS NOT DISTINCT FROM %s)
          AND (vw.number IS NOT DISTINCT FROM %s)
        ORDER BY v.book_id, v.chapter, v.verse_num
        LIMIT %s
    """, (gsid, lexeme_id, tense, mood, voice, person, number, limit))
    for vr in cur.fetchall():
        ref = f"{vr['abbreviation']} {vr['chapter']}:{vr['verse_num']}"
        print(f"            → {ref:<15} {vr['surface_form']:<20} → \"{vr['gloss']}\"")


# ── Top-N most frequent lemmas ────────────────────────────────────────────────

def show_top(cur, gsid, n=50):
    cur.execute("""
        SELECT
            l.strongs_id, l.lemma, l.transliteration,
            l.is_stative, l.is_deponent, l.is_polysemous,
            ls.gloss AS primary_sense,
            COUNT(vw.id) AS token_count,
            -- count of distinct gloss values (higher = more variation = more complex)
            COUNT(DISTINCT gse.gloss) AS distinct_glosses
        FROM lexeme l
        JOIN verse_word vw ON vw.lexeme_id = l.id
        LEFT JOIN lexeme_sense ls ON ls.lexeme_id = l.id AND ls.sense_index = 0
        LEFT JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id AND gse.gloss_set_id = %s
        GROUP BY l.strongs_id, l.lemma, l.transliteration,
                 l.is_stative, l.is_deponent, l.is_polysemous, ls.gloss
        ORDER BY token_count DESC
        LIMIT %s
    """, (gsid, n))
    rows = cur.fetchall()

    print(f"\n  Top {n} NT lemmas by frequency:\n")
    print(f"  {'#':<4} {'Strongs':<8} {'Lemma':<18} {'Translit':<18} {'Tokens':>6}  {'Forms':>5}  {'Primary sense':<30}  Flags")
    print(f"  {'-'*4} {'-'*8} {'-'*18} {'-'*18} {'-'*6}  {'-'*5}  {'-'*30}  -----")
    for i, r in enumerate(rows, 1):
        flags = ""
        if r["is_stative"]:    flags += "S"
        if r["is_deponent"]:   flags += "D"
        if r["is_polysemous"]: flags += "P"
        sense = (r["primary_sense"] or "—")[:30]
        print(f"  {i:<4} {r['strongs_id']:<8} {r['lemma']:<18} {(r['transliteration'] or ''):<18} {r['token_count']:>6}  {r['distinct_glosses']:>5}  {sense:<30}  {flags}")


# ── Suspicious gloss report ───────────────────────────────────────────────────

SUSPICIOUS_PATTERNS = [
    (r"amed$",        "base 'am' extracted — Dodson 'I am X' source priority issue"),
    (r"doed",         "base 'do' — missing irregular or wrong source"),
    (r"falled",       "base 'fall' — missing irregular"),
    (r"eated",        "base 'eat' — missing irregular"),
    (r"casted",       "base 'cast' — missing irregular"),
    (r"willed",       "base 'will' — θέλω-type: needs IRREGULAR_VERBS entry"),
    (r"may will",     "subjunctive 'will' — needs IRREGULAR_VERBS entry"),
    (r"might will",   "optative 'will' — needs IRREGULAR_VERBS entry"),
    (r"^dos$",        "3rd sg 'do' → 'dos' — missing irregular or IRREGULAR_VERBS"),
    (r"ed$",          None),  # generic -ed: may be fine, flag for inspection
]

def show_wrong(cur, gsid, min_count=1):
    """Find glosses that match suspicious patterns."""
    cur.execute("""
        SELECT gse.gloss, COUNT(*) AS cnt, l.strongs_id, l.lemma,
               ls.gloss AS base_sense
        FROM gloss_set_entry gse
        JOIN verse_word vw ON vw.id = gse.verse_word_id
        JOIN lexeme l ON l.id = vw.lexeme_id
        LEFT JOIN lexeme_sense ls ON ls.lexeme_id = l.id AND ls.sense_index = 0
        WHERE gse.gloss_set_id = %s
          AND (
            gse.gloss LIKE '%%amed%%'
            OR gse.gloss LIKE '%%doed%%'
            OR gse.gloss LIKE '%%falled%%'
            OR gse.gloss LIKE '%%eated%%'
            OR gse.gloss LIKE '%%casted%%'
            OR gse.gloss LIKE '%%willed%%'
            OR gse.gloss LIKE 'may will%%'
            OR gse.gloss LIKE 'might will%%'
            OR gse.gloss = 'dos'
          )
        GROUP BY gse.gloss, l.strongs_id, l.lemma, ls.gloss
        HAVING COUNT(*) >= %s
        ORDER BY cnt DESC
    """, (gsid, min_count))
    rows = cur.fetchall()
    if not rows:
        print("\n  No suspicious glosses found. Pipeline looks clean.")
        return
    print(f"\n  Suspicious glosses ({len(rows)} unique patterns):\n")
    print(f"  {'Gloss':<35} {'Count':>5}  {'Strongs':<8} {'Lemma':<18} Base sense")
    print(f"  {'-'*35} {'-'*5}  {'-'*8} {'-'*18} ----------")
    for r in rows:
        print(f"  {r['gloss']:<35} {r['cnt']:>5}  {r['strongs_id']:<8} {r['lemma']:<18} {r['base_sense'] or '—'}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inspect LITE gloss quality for any NT lemma",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", nargs="?",
                        help="Strong's ID (G4160), transliteration (poieo), or English keyword (do)")
    parser.add_argument("--verses", action="store_true",
                        help="Show sample NT verses for each morphological form")
    parser.add_argument("--top", nargs="?", const=50, type=int, metavar="N",
                        help="List top N most frequent NT lemmas (default 50)")
    parser.add_argument("--wrong", action="store_true",
                        help="Report all suspicious-looking glosses in the LITE set")
    args = parser.parse_args()

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    gsid = gloss_set_id(cur)

    if args.wrong:
        show_wrong(cur, gsid)
        conn.close()
        return

    if args.top is not None:
        show_top(cur, gsid, args.top)
        conn.close()
        return

    if not args.query:
        parser.print_help()
        conn.close()
        return

    query = args.query.strip()

    # ── Resolve to one or more lexemes ───────────────────────────────────────
    lexemes = []

    # Try Strong's ID first (G-prefixed or all-digits)
    if re.match(r'^[Gg]?\d+$', query):
        lex = find_lexeme_by_strongs(cur, query)
        if lex:
            lexemes = [lex]
        else:
            print(f"No lexeme found for strongs_id '{query.upper()}'")
            conn.close()
            return
    else:
        # Try transliteration search, then English gloss search
        rows = find_lexemes_by_transliteration(cur, query)
        if not rows:
            rows = find_lexemes_by_english(cur, query)
        if not rows:
            print(f"No lexeme found matching '{query}'")
            conn.close()
            return
        if len(rows) == 1:
            lexemes = [rows[0]]
        else:
            print(f"\n  {len(rows)} matches for '{query}' — showing all:\n")
            for i, r in enumerate(rows, 1):
                print(f"  [{i}] {r['strongs_id']}  {r['lemma']}  ({r['transliteration'] or '—'})"
                      f"  {r['token_count'] or 0} tokens")
            lexemes = rows

    # ── Display each lexeme ───────────────────────────────────────────────────
    for lex in lexemes:
        print_lexeme_header(lex)
        print_senses(cur, lex["id"])
        print_gloss_table(cur, lex["id"], gsid, show_verses=args.verses)

    conn.close()


if __name__ == "__main__":
    main()
