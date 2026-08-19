#!/usr/bin/env python3
"""
populate_lexeme_sense.py — Phase 2: Populate lexeme_sense table.

Two-pass operation:

Pass 1 — Auto-split (all 5,624 corpus lemmas):
  Splits lexeme_meaning.short_gloss on semicolons into individual sense rows.
  sense_index 0 is nt_primary; all others are secondary.
  Handles the ~10 lemmas that have no semicolons (single-sense words).

Pass 2 — Polysemous overrides (12 curated lemmas):
  Replaces auto-split rows for polysemous lemmas with hand-curated single-word
  senses. These are the options Handler C AI will choose between — they must be
  clean, concise, and semantically distinct. Multi-word auto-split senses like
  "word, saying, speech" are too noisy for AI classification.

Usage:
  python scripts/populate_lexeme_sense.py           # populate all
  python scripts/populate_lexeme_sense.py --dry-run # preview, no writes
  python scripts/populate_lexeme_sense.py --report  # show current row counts
  python scripts/populate_lexeme_sense.py --reset   # delete all and re-populate

Requirements:
  pip install psycopg2-binary python-dotenv
"""

import os, sys, argparse
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

# =============================================================================
# POLYSEMOUS SENSE OVERRIDES
#
# Hand-curated sense lists for the 13 polysemous lemmas.
# These replace auto-split rows for these lemmas.
#
# Rules for entries here:
#   - One word or short phrase per sense (clean enough for AI selection)
#   - Sense 0 must be the dominant NT meaning — not the classical or LXX meaning
#   - Senses must be semantically distinct — not synonyms of each other
#   - sense_type: 'nt_primary' for index 0, 'secondary' for the rest
#   - All NT-attested (nt_attested=True for all entries here)
# =============================================================================

POLYSEMOUS_OVERRIDES = {
    # πνεῦμα — the most contextually variable word in the NT
    # Spirit (divine) vs human spirit vs atmospheric wind
    "G4151": [
        "spirit",         # 0: human spirit / spiritual dimension (default)
        "Spirit",         # 1: the Holy Spirit / divine Spirit (capitalize)
        "wind",           # 2: literal wind (John 3:8)
        "breath",         # 3: breath of life (Rev 11:11)
    ],

    # λόγος — from mundane speech to the cosmic Logos of John 1
    "G3056": [
        "word",           # 0: spoken word, statement (most common)
        "message",        # 1: gospel message, proclamation
        "reason",         # 2: account, explanation (Acts 19:40)
        "Word",           # 3: the divine Logos (John 1 usage — capitalize)
    ],

    # πίστις — faith as act vs faith as content vs faithfulness as character
    "G4102": [
        "faith",          # 0: trust, belief (most common)
        "faithfulness",   # 1: steadfast loyalty (Gal 5:22 fruit of Spirit)
        "trust",          # 2: relational trust/confidence
    ],

    # νόμος — Mosaic Law vs general principle vs written law
    "G3551": [
        "law",            # 0: general law, code
        "the Law",        # 1: the Mosaic Law / Torah (with article in Greek)
        "principle",      # 2: a controlling principle (Rom 7:23 "law of sin")
    ],

    # σάρξ — one of the most theologically loaded words in Paul
    "G4561": [
        "flesh",          # 0: physical body substance (most literal)
        "sinful nature",  # 1: Pauline ethical sense (Rom 8, Gal 5)
        "body",           # 2: physical human body (less evaluative)
    ],

    # ἀγάπη — love is relatively straightforward but has range
    "G26": [
        "love",           # 0: the dominant NT meaning
        "charity",        # 1: KJV tradition / love as beneficent action (1 Cor 13)
    ],

    # κόσμος — from physical universe to fallen humanity to "this age"
    "G2889": [
        "world",          # 0: the created world / the present world system
        "humanity",       # 1: human society, mankind (John 3:16)
        "universe",       # 2: the physical cosmos / ordered creation
    ],

    # αἰών — from lifetime to eschatological age to eternity
    "G165": [
        "age",            # 0: a period of time, an era (most common)
        "eternity",       # 1: endless duration (εἰς τὸν αἰῶνα — forever)
        "world",          # 2: this present world / this era (ὁ αἰὼν οὗτος)
    ],

    # ψυχή — from physical life-breath to immaterial soul to self/person
    "G5590": [
        "soul",           # 0: the immaterial inner self (most common NT sense)
        "life",           # 1: physical life, vitality (John 10:11 lay down life)
        "self",           # 2: reflexive — whole person (Matt 16:26)
        "person",         # 3: counting heads (Acts 2:41 — 3,000 persons)
    ],

    # δικαιοσύνη — righteousness as status vs ethical quality vs justice
    "G1343": [
        "righteousness",  # 0: right standing before God / ethical rightness
        "justice",        # 1: distributive justice, fairness
        "justification",  # 2: the act of being declared righteous (Pauline)
    ],

    # χάρις — grace as unmerited favor vs gratitude vs gift
    "G5485": [
        "grace",          # 0: unmerited divine favor (dominant Pauline sense)
        "favor",          # 1: approval, goodwill (Luke 2:52)
        "gift",           # 2: a gracious gift (2 Cor 8:4)
    ],

    # δόξα — the corpus got this wrong (sense 0 was "expectation" — classical)
    # NT δόξα is overwhelmingly "glory" — majesty, radiance, honor
    "G1391": [
        "glory",          # 0: divine radiance / magnificent honor (dominant NT)
        "honor",          # 1: recognition, reputation
        "splendor",       # 2: visible radiance, brightness (Transfiguration)
        "praise",         # 3: ascription of glory (doxology contexts)
    ],

    # σώζω — save is the default but healing miracles use the same verb
    # ~20-25 of 106 NT occurrences are physical healing, not eschatological salvation
    # Examples: Matt 9:21 ("if I touch his garment I will be healed"),
    #           Mark 5:34 ("your faith has healed you"),
    #           Luke 17:19, 18:42, Acts 4:9, 14:9
    "G4982": [
        "save",           # 0: deliver from sin/judgment (dominant NT sense)
        "heal",           # 1: restore physical health (healing miracle narratives)
        "rescue",         # 2: deliver from physical danger (Acts 27:20, 43)
    ],

    # μέσος — noun/adjective used in NT overwhelmingly as "midst" (ἐν μέσῳ = among)
    "G3319": [
        "midst",          # 0: in the midst of, among (dominant NT usage)
        "middle",         # 1: middle, central (positional adjective)
    ],

    # ἵστημι — transitive (aorist: place/set) vs intransitive (perfect: stand)
    "G2476": [
        "stand",          # 0: intransitive — to stand, be standing (dominant NT)
        "place",          # 1: transitive — to set, place, establish
    ],

    # καθίζω — intransitive (sit down) vs transitive (seat someone)
    "G2523": [
        "sit",            # 0: intransitive — to sit down (dominant NT)
        "seat",           # 1: transitive — to cause to sit, enthrone
    ],

    # ἐγείρω — raise up (general) vs resurrect (from death)
    "G1453": [
        "raise",          # 0: lift up, help up, raise (general — covers most uses)
        "resurrect",      # 1: raise from the dead (theological resurrection context)
    ],
}

# =============================================================================
# MAIN LOGIC
# =============================================================================

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def report(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(DISTINCT lexeme_id) AS lemmas_with_senses,
            COUNT(*) AS total_sense_rows,
            COUNT(CASE WHEN sense_type = 'nt_primary' THEN 1 END) AS nt_primary,
            COUNT(CASE WHEN sense_type = 'secondary' THEN 1 END) AS secondary
        FROM lexeme_sense
    """)
    row = cur.fetchone()
    print(f"lexeme_sense: {row[0]} lemmas, {row[1]} total rows "
          f"({row[2]} nt_primary, {row[3]} secondary)")
    cur.close()


def populate(conn, dry_run=False, reset=False):
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if reset:
        if dry_run:
            print("  [dry-run] Would DELETE all rows from lexeme_sense")
        else:
            cur.execute("DELETE FROM lexeme_sense")
            print(f"  Cleared lexeme_sense table")

    # ── Fetch best available short_gloss per lexeme using source priority ────────
    # Priority: corpus → lsj → gk → mounce → dodson → wiktionary → strongs
    #
    # Corpus covers all 5,624 NT lemmas in "to X; to Y" semicolon format — the
    # primary source for the rules engine. LSJ and GK are clean fallbacks using
    # the same "to X" infinitive format. Dodson uses "I X" first-person format
    # and is kept as a last resort only; in practice it should never fire since
    # corpus + LSJ + GK cover all NT lemmas.
    cur.execute("""
        SELECT DISTINCT ON (l.id)
            l.id AS lexeme_id, l.strongs_id, lm.short_gloss, lm.source
        FROM lexeme l
        JOIN lexeme_meaning lm ON lm.lexeme_id = l.id
        WHERE lm.source IN ('corpus','lsj','dodson','gk','wiktionary','mounce','strongs')
          AND lm.short_gloss IS NOT NULL AND lm.short_gloss <> ''
        ORDER BY l.id,
            CASE lm.source
                WHEN 'corpus'     THEN 1
                WHEN 'lsj'        THEN 2
                WHEN 'gk'         THEN 3
                WHEN 'mounce'     THEN 4
                WHEN 'dodson'     THEN 5
                WHEN 'wiktionary' THEN 6
                WHEN 'strongs'    THEN 7
            END
    """)
    rows = cur.fetchall()
    print(f"  Processing {len(rows)} entries (corpus + fallbacks)...")

    # ── Build insert batch ────────────────────────────────────────────────────
    inserts = []
    skipped = 0
    overridden = 0
    auto_split = 0

    for row in rows:
        lexeme_id  = row["lexeme_id"]
        strongs_id = row["strongs_id"]
        gloss_str  = (row["short_gloss"] or "").strip()

        if not gloss_str:
            skipped += 1
            continue

        if strongs_id in POLYSEMOUS_OVERRIDES:
            # Use curated sense list — replaces auto-split entirely
            senses = POLYSEMOUS_OVERRIDES[strongs_id]
            overridden += 1
        else:
            # Auto-split on semicolons
            senses = [s.strip() for s in gloss_str.split(';') if s.strip()]

        for idx, sense in enumerate(senses):
            sense_type = 'nt_primary' if idx == 0 else 'secondary'
            inserts.append((lexeme_id, idx, sense, sense_type, True))

        if strongs_id not in POLYSEMOUS_OVERRIDES:
            auto_split += 1

    print(f"  Auto-split:  {auto_split} lemmas")
    print(f"  Curated:     {overridden} polysemous lemmas (overridden)")
    print(f"  Skipped:     {skipped} empty glosses")
    print(f"  Total rows:  {len(inserts)}")

    if dry_run:
        # Print curated entries so they can be reviewed
        print()
        print("  Curated sense lists (polysemous overrides):")
        for sid, senses in sorted(POLYSEMOUS_OVERRIDES.items()):
            print(f"    {sid}:")
            for i, s in enumerate(senses):
                marker = "●" if i == 0 else " "
                print(f"      {marker} [{i}] {s}")
        return

    # ── Bulk insert with ON CONFLICT DO NOTHING ───────────────────────────────
    # (safe to re-run: won't duplicate if already populated)
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO lexeme_sense (lexeme_id, sense_index, gloss, sense_type, nt_attested)
        VALUES %s
        ON CONFLICT (lexeme_id, sense_index) DO UPDATE
            SET gloss      = EXCLUDED.gloss,
                sense_type = EXCLUDED.sense_type
        """,
        inserts,
        page_size=500
    )
    print(f"  Inserted/updated {cur.rowcount} sense rows")
    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Populate lexeme_sense from corpus glosses")
    parser.add_argument("--dry-run", action="store_true", help="Preview — no DB writes")
    parser.add_argument("--reset",   action="store_true", help="Delete existing rows before populating")
    parser.add_argument("--report",  action="store_true", help="Show current counts and exit")
    args = parser.parse_args()

    conn = get_conn()
    try:
        if args.report:
            report(conn)
            return

        print("Populating lexeme_sense...")
        if args.dry_run:
            print("  (dry-run mode — no changes will be written)\n")

        populate(conn, dry_run=args.dry_run, reset=args.reset)

        if not args.dry_run:
            conn.commit()
            print("\nDone. Current state:")
            report(conn)
        else:
            conn.rollback()

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
