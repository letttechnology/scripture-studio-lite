#!/usr/bin/env python3
"""
export_pipeline_audit.py — Full pipeline audit JSON per lemma.

For every NT lemma shows the complete chain:
  corpus definitions → canonical word → morph code → English gloss output

Output: data/pipeline_audit.json

Structure per lemma:
  {
    "G599": {
      "lemma":          "ἀποθνήσκω",
      "transliteration":"apothnēskō",
      "corpus_gloss":   "to die; to be put to death; to renounce",
      "canonical_word": "die",
      "nt_occurrences": 111,
      "forms": [
        {
          "morph_code":  "V-AAI-3S",
          "tense":       "Aorist",
          "mood":        "Indicative",
          "voice":       "Active",
          "person":      "3rd",
          "number":      "Singular",
          "count":       32,
          "gloss":       "died",
          "verses":      ["Matt 9:24 ἀπέθανεν", "Mark 5:35 ἀπέθανεν"]
        },
        ...
      ]
    }
  }

Usage:
  python scripts/export_pipeline_audit.py                    # all 5,624 lemmas
  python scripts/export_pipeline_audit.py --strongs G599 G4160  # specific lemmas
  python scripts/export_pipeline_audit.py --top 100          # top 100 by NT frequency
  python scripts/export_pipeline_audit.py --verbs-only       # verbs only
  python scripts/export_pipeline_audit.py --verses 5         # include N sample verses per form (default 2)
"""

import os, sys, json, argparse
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

CANONICAL_FILE = Path(__file__).parent.parent / "data" / "canonical_words.json"
OUT_FILE       = Path(__file__).parent.parent / "data" / "pipeline_audit.json"

BOOK_ABBREV = {
    40:"Matt", 41:"Mark", 42:"Luke", 43:"John", 44:"Acts",
    45:"Rom",  46:"1Cor", 47:"2Cor", 48:"Gal",  49:"Eph",
    50:"Phil", 51:"Col",  52:"1Th",  53:"2Th",  54:"1Tim",
    55:"2Tim", 56:"Tit",  57:"Phm",  58:"Heb",  59:"Jas",
    60:"1Pet", 61:"2Pet", 62:"1Jn",  63:"2Jn",  64:"3Jn",
    65:"Jude", 66:"Rev",
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def load_canonical():
    if not CANONICAL_FILE.exists():
        print("WARNING: canonical_words.json not found — canonical_word will be empty.")
        return {}
    with open(CANONICAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def morph_code_from_row(row):
    """
    Reconstruct a readable morph code string from the parsed fields.
    Not the raw MorphGNT code — a readable label: 'Aorist Indicative Active 3rd Sg'
    """
    parts = []
    for col in ("tense", "mood", "voice", "person", "number", "grammatical_case", "gender"):
        val = row.get(col)
        if val:
            parts.append(val)
    return " ".join(parts) if parts else row.get("pos_code") or "—"


def build_audit(conn, canonical, strongs_filter=None, top_n=None,
                verbs_only=False, max_verses=2):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get gloss_set id
    cur.execute("SELECT id FROM gloss_set WHERE name = 'lite_auto' LIMIT 1")
    gsid = cur.fetchone()["id"]

    # ── Step 1: get all matching lexemes ─────────────────────────────────────
    where_clauses = ["1=1"]
    params = []

    if strongs_filter:
        where_clauses.append("l.strongs_id = ANY(%s)")
        params.append(strongs_filter)

    order = "COUNT(vw.id) DESC" if top_n else "l.strongs_id"
    limit = f"LIMIT {top_n}" if top_n else ""

    cur.execute(f"""
        SELECT
            l.id            AS lexeme_id,
            l.strongs_id,
            l.lemma,
            l.transliteration,
            l.is_stative,
            l.is_deponent,
            l.is_polysemous,
            lm_corp.short_gloss  AS corpus_gloss,
            ls.gloss             AS sense0,
            COUNT(vw.id)         AS nt_occurrences
        FROM lexeme l
        LEFT JOIN lexeme_meaning lm_corp
            ON lm_corp.lexeme_id = l.id AND lm_corp.source = 'corpus'
        LEFT JOIN lexeme_sense ls
            ON ls.lexeme_id = l.id AND ls.sense_index = 0
        LEFT JOIN verse_word vw ON vw.lexeme_id = l.id
        WHERE {' AND '.join(where_clauses)}
        GROUP BY l.id, l.strongs_id, l.lemma, l.transliteration,
                 l.is_stative, l.is_deponent, l.is_polysemous,
                 lm_corp.short_gloss, ls.gloss
        ORDER BY {order}
        {limit}
    """, params or None)
    lexemes = cur.fetchall()

    if verbs_only:
        # filter: only lexemes that have at least one verb token in NT
        verb_ids = set()
        cur.execute("""
            SELECT DISTINCT vw.lexeme_id FROM verse_word vw
            WHERE vw.tense IS NOT NULL OR vw.mood IS NOT NULL
        """)
        verb_ids = {r["lexeme_id"] for r in cur.fetchall()}
        lexemes = [l for l in lexemes if l["lexeme_id"] in verb_ids]

    result = {}
    total = len(lexemes)
    print(f"Processing {total} lemmas...")

    for i, lex in enumerate(lexemes, 1):
        sid = lex["strongs_id"]
        lid = lex["lexeme_id"]

        if i % 500 == 0:
            print(f"  {i}/{total}...")

        # ── Step 2: get all distinct morph forms + gloss for this lexeme ─────
        cur.execute("""
            SELECT
                vw.pos_code,
                vw.tense,
                vw.mood,
                vw.voice,
                vw.person,
                vw.number,
                vw.grammatical_case,
                vw.gender,
                vw.morphology_code,
                gse.gloss,
                COUNT(*)          AS count,
                -- collect up to N sample verse references
                array_agg(
                    b.abbreviation || ' ' || v.chapter || ':' || v.verse_num
                    || ' ' || vw.surface_form
                    ORDER BY v.book_id, v.chapter, v.verse_num
                ) FILTER (WHERE gse.gloss IS NOT NULL)  AS verse_samples
            FROM verse_word vw
            JOIN verse v   ON v.id  = vw.verse_id
            JOIN book  b   ON b.id  = v.book_id
            LEFT JOIN gloss_set_entry gse
                ON gse.verse_word_id = vw.id AND gse.gloss_set_id = %s
            WHERE vw.lexeme_id = %s
            GROUP BY vw.pos_code, vw.tense, vw.mood, vw.voice,
                     vw.person, vw.number, vw.grammatical_case,
                     vw.gender, vw.morphology_code, gse.gloss
            ORDER BY COUNT(*) DESC
        """, (gsid, lid))
        form_rows = cur.fetchall()

        # ── Step 3: assemble forms list ───────────────────────────────────────
        forms = []
        for fr in form_rows:
            morph_label = morph_code_from_row(fr)
            verses = []
            if fr["verse_samples"]:
                # deduplicate and take first max_verses
                seen = []
                for v in fr["verse_samples"]:
                    if v not in seen:
                        seen.append(v)
                    if len(seen) >= max_verses:
                        break
                verses = seen

            forms.append({
                "morph_code":       fr["morphology_code"] or "",
                "parsed":           morph_label,
                "pos":              fr["pos_code"] or "",
                "tense":            fr["tense"]            or "",
                "mood":             fr["mood"]             or "",
                "voice":            fr["voice"]            or "",
                "person":           fr["person"]           or "",
                "number":           fr["number"]           or "",
                "case":             fr["grammatical_case"] or "",
                "gender":           fr["gender"]           or "",
                "count":            fr["count"],
                "gloss":            fr["gloss"]            or "",
                "verses":           verses,
            })

        # ── Step 4: canonical word ────────────────────────────────────────────
        canon = canonical.get(sid, {})
        canonical_word = canon.get("canonical_word", "")
        canon_source   = canon.get("source", "")

        # ── Step 5: flags ─────────────────────────────────────────────────────
        flags = []
        if lex["is_stative"]:    flags.append("stative")
        if lex["is_deponent"]:   flags.append("deponent")
        if lex["is_polysemous"]: flags.append("polysemous")

        result[sid] = {
            "lemma":          lex["lemma"],
            "transliteration": lex["transliteration"] or "",
            "flags":          flags,
            "corpus_gloss":   lex["corpus_gloss"]  or "",
            "sense0":         lex["sense0"]         or "",
            "canonical_word": canonical_word,
            "canonical_source": canon_source,
            "nt_occurrences": lex["nt_occurrences"] or 0,
            "forms":          forms,
        }

    cur.close()
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Export full pipeline audit JSON: corpus → canonical → morph → gloss"
    )
    parser.add_argument("--strongs",     nargs="+", metavar="ID",
                        help="Only these Strong's IDs (e.g. G599 G4160)")
    parser.add_argument("--top",         type=int, metavar="N",
                        help="Top N lemmas by NT frequency")
    parser.add_argument("--verbs-only",  action="store_true",
                        help="Verbs only")
    parser.add_argument("--verses",      type=int, default=2, metavar="N",
                        help="Sample verses per form (default 2)")
    parser.add_argument("--output",      type=str,
                        help=f"Output file path (default: {OUT_FILE})")
    args = parser.parse_args()

    out = Path(args.output) if args.output else OUT_FILE
    canonical = load_canonical()
    conn = get_conn()

    strongs_filter = None
    if args.strongs:
        strongs_filter = [s.upper() if s.upper().startswith("G") else "G"+s.upper()
                          for s in args.strongs]

    audit = build_audit(
        conn, canonical,
        strongs_filter=strongs_filter,
        top_n=args.top,
        verbs_only=args.verbs_only,
        max_verses=args.verses,
    )
    conn.close()

    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    total_forms = sum(len(e["forms"]) for e in audit.values())
    print(f"\nWritten {len(audit)} lemmas / {total_forms} morphological forms → {out}")


if __name__ == "__main__":
    main()
