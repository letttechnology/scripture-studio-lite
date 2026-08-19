#!/usr/bin/env python3
"""
populate_lexeme_flags.py — Populate exception flags on the lexeme table.

Sets three flags required by the Handler chain:
  is_stative    — verb describes a state; imperfect → simple past, not progressive
  is_deponent   — middle/passive form in Greek carries active meaning in English
  is_polysemous — word has multiple NT senses that vary significantly by verse context
                  (routes token to AI classification in Handler C)

Also links irregular_verb and irregular_noun rows to their lexeme_id.

Usage:
  python scripts/populate_lexeme_flags.py           # apply all flags
  python scripts/populate_lexeme_flags.py --dry-run # preview changes, no DB writes
  python scripts/populate_lexeme_flags.py --report  # show current flag counts

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
# STATIVE VERBS
# Verbs that describe a state rather than an action.
# In English, stative verbs do not use progressive form naturally:
#   "was believing" ✗   "believed" ✓
#   "was knowing"   ✗   "knew"     ✓
# Imperfect active of these verbs → simple past, not "was [verb]ing"
# =============================================================================

STATIVE_VERBS = {
    # strongs_id: English base (for documentation)
    "G1510": "be",
    "G5225": "exist/be",
    "G2192": "have",
    "G4100": "believe",
    "G1492": "know (perfect form)",
    "G1097": "know",
    "G25":   "love",
    "G3404": "hate",
    "G5399": "fear",
    "G2309": "want/will",
    "G1014": "wish/want",
    "G1410": "be able/can",
    "G1380": "seem/think",
    "G3049": "reckon/consider",
    "G5426": "think/set mind on",
    "G2233": "consider/think",
    "G3543": "suppose/think",
    "G1679": "hope",
    "G3708": "see (perception)",
    "G4920": "understand",
    "G191":  "hear (understanding)",
    "G3306": "remain/abide",
}

# =============================================================================
# DEPONENT VERBS
# Verbs that appear in middle or passive morphological form in Greek
# but carry active meaning in English.
# Without this flag, Handler D would incorrectly render these as passive.
#   ἔρχομαι V-PNI-3S → "comes" ✓  (not "is come" ✗)
# =============================================================================

DEPONENT_VERBS = {
    "G2064": "come (ἔρχομαι)",
    "G4198": "go/travel (πορεύομαι)",
    "G611": "answer (ἀποκρίνομαι)",
    "G1096": "become/happen (γίνομαι)",
    "G4336": "pray (προσεύχομαι)",
    "G2038": "work (ἐργάζομαι)",
    "G756": "begin (ἄρχομαι)",
    "G3868": "refuse (παραιτέομαι)",
    "G142": "take up/begin (αἴρομαι — middle forms)",
    "G1011": "plan/deliberate (βουλεύομαι)",
    "G3811": "be disciplined (παιδεύομαι — passive deponent)",
}

# =============================================================================
# POLYSEMOUS LEMMAS
# Words where the sense shifts significantly by verse context.
# These tokens are routed to Handler C AI classification.
# The AI selects from the sense options in lexeme_sense table.
# =============================================================================

POLYSEMOUS_LEMMAS = {
    "G4151": "πνεῦμα — spirit / Spirit (divine) / wind / breath",
    "G3056": "λόγος — word / message / reason / the Word (Logos)",
    "G4102": "πίστις — faith / faithfulness / trust",
    "G3551": "νόμος — law / the Law (Mosaic) / principle",
    "G4561": "σάρξ — flesh / sinful nature / physical body",
    "G26":   "ἀγάπη — love / charity",
    "G2889": "κόσμος — world / humanity / universe / order",
    "G165":  "αἰών — age / eternity / this world",
    "G5590": "ψυχή — soul / life / self / person",
    "G1343": "δικαιοσύνη — righteousness / justice / justification",
    "G5485": "χάρις — grace / favor / gift",
    "G3056": "λόγος — word / message / reason / the Word",
    "G1391": "δόξα — glory / honor / reputation / splendor",
    "G4982": "σώζω — save / heal / rescue",
    "G2476": "ἵστημι — stand (intransitive) / place (transitive)",
    "G2523": "καθίζω — sit (intransitive) / seat (transitive)",
    "G1453": "ἐγείρω — raise / resurrect",
}

# =============================================================================
# MAIN
# =============================================================================

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def report(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT
            SUM(CASE WHEN is_stative    THEN 1 ELSE 0 END) AS stative,
            SUM(CASE WHEN is_deponent   THEN 1 ELSE 0 END) AS deponent,
            SUM(CASE WHEN is_polysemous THEN 1 ELSE 0 END) AS polysemous
        FROM lexeme
    """)
    row = cur.fetchone()
    print(f"Current flags: is_stative={row[0]}  is_deponent={row[1]}  is_polysemous={row[2]}")
    cur.close()

def populate_flags(conn, dry_run=False):
    cur = conn.cursor()

    # ── is_stative ────────────────────────────────────────────────────────────
    stative_ids = list(STATIVE_VERBS.keys())
    cur.execute(
        "SELECT strongs_id FROM lexeme WHERE strongs_id = ANY(%s)",
        (stative_ids,)
    )
    found_stative = {r[0] for r in cur.fetchall()}
    missing = set(stative_ids) - found_stative
    if missing:
        print(f"  WARNING: stative strongs_ids not found in lexeme: {sorted(missing)}")

    if dry_run:
        print(f"  [dry-run] Would set is_stative=true for {len(found_stative)} lemmas")
    else:
        cur.execute(
            "UPDATE lexeme SET is_stative = true WHERE strongs_id = ANY(%s)",
            (list(found_stative),)
        )
        print(f"  Set is_stative=true for {cur.rowcount} lemmas")

    # ── is_deponent ───────────────────────────────────────────────────────────
    deponent_ids = list(DEPONENT_VERBS.keys())
    cur.execute(
        "SELECT strongs_id FROM lexeme WHERE strongs_id = ANY(%s)",
        (deponent_ids,)
    )
    found_deponent = {r[0] for r in cur.fetchall()}
    missing = set(deponent_ids) - found_deponent
    if missing:
        print(f"  WARNING: deponent strongs_ids not found in lexeme: {sorted(missing)}")

    if dry_run:
        print(f"  [dry-run] Would set is_deponent=true for {len(found_deponent)} lemmas")
    else:
        cur.execute(
            "UPDATE lexeme SET is_deponent = true WHERE strongs_id = ANY(%s)",
            (list(found_deponent),)
        )
        print(f"  Set is_deponent=true for {cur.rowcount} lemmas")

    # ── is_polysemous ─────────────────────────────────────────────────────────
    polysemous_ids = list(POLYSEMOUS_LEMMAS.keys())
    cur.execute(
        "SELECT strongs_id FROM lexeme WHERE strongs_id = ANY(%s)",
        (polysemous_ids,)
    )
    found_polysemous = {r[0] for r in cur.fetchall()}
    missing = set(polysemous_ids) - found_polysemous
    if missing:
        print(f"  WARNING: polysemous strongs_ids not found in lexeme: {sorted(missing)}")

    if dry_run:
        print(f"  [dry-run] Would set is_polysemous=true for {len(found_polysemous)} lemmas")
    else:
        cur.execute(
            "UPDATE lexeme SET is_polysemous = true WHERE strongs_id = ANY(%s)",
            (list(found_polysemous),)
        )
        print(f"  Set is_polysemous=true for {cur.rowcount} lemmas")

    # ── link irregular_verb.lexeme_id ─────────────────────────────────────────
    # Normalize both sides to NFC — lexeme and irregular_verb use different
    # Unicode compositions for the same Greek characters.
    cur.execute("""
        UPDATE irregular_verb iv
        SET lexeme_id = l.id
        FROM lexeme l
        WHERE normalize(l.lemma, NFC) = normalize(iv.lemma, NFC)
          AND iv.lexeme_id IS NULL
    """)
    linked_verbs = cur.rowcount
    if dry_run:
        conn.rollback()
        print(f"  [dry-run] Would link {linked_verbs} irregular_verb rows to lexeme_id")
    else:
        print(f"  Linked {linked_verbs} irregular_verb rows to lexeme_id")

    # ── link irregular_noun.lexeme_id ─────────────────────────────────────────
    cur.execute("""
        UPDATE irregular_noun irn
        SET lexeme_id = l.id
        FROM lexeme l
        WHERE normalize(l.lemma, NFC) = normalize(irn.lemma, NFC)
          AND irn.lexeme_id IS NULL
    """)
    linked_nouns = cur.rowcount
    if dry_run:
        conn.rollback()
        print(f"  [dry-run] Would link {linked_nouns} irregular_noun rows to lexeme_id")
    else:
        print(f"  Linked {linked_nouns} irregular_noun rows to lexeme_id")

    cur.close()

def main():
    parser = argparse.ArgumentParser(description="Populate lexeme exception flags")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--report",  action="store_true", help="Show current flag counts and exit")
    args = parser.parse_args()

    conn = get_conn()
    try:
        if args.report:
            report(conn)
            return

        print("Populating lexeme flags...")
        if args.dry_run:
            print("  (dry-run mode — no changes will be written)\n")

        populate_flags(conn, dry_run=args.dry_run)

        if not args.dry_run:
            conn.commit()
            print("\nDone. Verifying:")
            report(conn)
        else:
            conn.rollback()

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
