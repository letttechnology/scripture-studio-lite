#!/usr/bin/env python3
"""
run_c1_1peter.py — C1 Contextual Sense Selection (1 Peter or full NT).

For each polysemous content-word token in the target scope, asks Claude which
of the semicolon-separated corpus senses best fits the Greek verse context.
Results stored as sense_index in gloss_set_entry; B1 is then re-run for
those tokens using the selected sense → updates gloss.

The whole script is idempotent: re-running --collect applies only new results.

Usage:
  python scripts/run_c1_1peter.py --dry-run                   # preview 10 prompts (1 Peter)
  python scripts/run_c1_1peter.py --submit                    # submit 1 Peter batch (~$0.10)
  python scripts/run_c1_1peter.py --submit --all              # submit full NT batch (~$10)
  python scripts/run_c1_1peter.py --submit --book 45          # submit one book by book_id
  python scripts/run_c1_1peter.py --status                    # check batch status
  python scripts/run_c1_1peter.py --collect                   # apply results, re-run B1
  python scripts/run_c1_1peter.py --reset                     # clear C1 for current scope
  python scripts/run_c1_1peter.py --reset --all               # clear C1 for full NT

Requirements:
  pip install psycopg2-binary python-dotenv anthropic
"""

import os, sys, re, json, argparse
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

BOOK_ID_1PETER = 60   # default scope

# NT book_id → abbreviation (for state file naming)
BOOK_ABBREV = {
    40:'Matt',41:'Mark',42:'Luke',43:'John',44:'Acts',
    45:'Rom',46:'1Cor',47:'2Cor',48:'Gal',49:'Eph',
    50:'Phil',51:'Col',52:'1Thess',53:'2Thess',54:'1Tim',
    55:'2Tim',56:'Titus',57:'Phlm',58:'Heb',59:'Jas',
    60:'1Pet',61:'2Pet',62:'1Jn',63:'2Jn',64:'3Jn',
    65:'Jude',66:'Rev',
}

def batch_state_file(book_id=None):
    """Return path to batch state JSON for the given scope."""
    scope = 'NT' if book_id is None else BOOK_ABBREV.get(book_id, str(book_id))
    return Path(__file__).parent.parent / "data" / f"c1-{scope}-batch.json"

COST_INPUT_PER_M  = 0.40   # Haiku batch pricing per 1M input tokens
COST_OUTPUT_PER_M = 2.00   # Haiku batch pricing per 1M output tokens

# ── B1 logic (mirror of generate_lite_glosses.py — kept in sync manually) ─────
# Imported here so this script can re-run B1 for updated tokens without
# needing to shell out to the generate script.

def _mk(tense, mood, voice, person=None, number=None):
    return (tense, mood, voice, person, number)

IRREGULAR_VERBS = {
    "G1510": {
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "am",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "are",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "is",
        _mk("Present",   "Indicative", "act", "1st", "Plural"):    "are",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "are",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "are",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was",
        _mk("Imperfect", "Indicative", "act", "3rd", "Plural"):    "were",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will be",
        _mk("Present",   "Infinitive", "act"):                     "to be",
        _mk("Present",   "Participle", "act"):                     "being",
        _mk("Present",   "Subjunctive","act", "3rd", "Singular"):  "may be",
    },
    "G2064": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "comes",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "came",
        _mk("Aorist",    "Participle", "act"):                     "having come",
        _mk("Present",   "Participle", "act"):                     "coming",
        _mk("Present",   "Infinitive", "act"):                     "to come",
    },
    "G3004": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "says",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "said",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "said",
        _mk("Present",   "Participle", "act"):                     "saying",
    },
    "G1096": {
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "became",
        _mk("Present",   "Infinitive", "act"):                     "to become",
        _mk("Present",   "Participle", "act"):                     "becoming",
    },
    "G1097": {
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "knew",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "knew",
        _mk("Aorist",    "Participle", "act"):                     "having known",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "knows",
        _mk("Present",   "Participle", "act"):                     "knowing",
    },
}

FUNCTION_WORD_OVERRIDES = {
    "G2532": "and", "G1161": "but", "G3756": "not", "G3361": "not",
    "G1722": "in",  "G1537": "from","G1519": "into","G3754": "that",
    "G1063": "for", "G1223": "through","G2443": "so that","G3779": "thus",
    "G0235": "but", "G3767": "therefore","G2596": "according to",
    "G3326": "with","G4314": "to",  "G5228": "above","G1909": "upon",
    "G3844": "beside","G4012": "about","G0575": "from","G5259": "under",
    "G1065": "indeed","G0686": "then","G2089": "still","G3765": "no longer",
    "G3568": "now", "G5119": "then","G3699": "where","G3753": "when",
    "G5613": "as",  "G2531": "just as","G1437": "if","G1487": "if",
    "G3761": "nor", "G3366": "nor","G2228": "or",
    "G1473": "I",   "G2249": "we", "G4771": "you",
    "G1438": "himself","G0846": "he",
    "G3739": "who", "G3748": "whoever","G5101": "who","G5100": "someone",
    "G3778": "this","G1565": "that","G3592": "this",
}


def needs_c1(corpus_gloss):
    """
    Layer 2 pre-filter: return True only when C1 contextual disambiguation would
    actually improve on always picking sense 0.

    Tokens that return False are deterministically served by sense 0 — no AI call needed.

    Rules (from corpus-sense-design.md §3.3 Layer 2):
      - Single sense: no choice to make → False
      - All senses ≤ 2 words: near-synonyms; sense 0 is fine → False
      - Sense 0 ≤ 2 words AND all other senses longer: sense 0 is the clear primary form → False
      - Otherwise: genuine contextual ambiguity, C1 should decide → True
    """
    senses = [s.strip() for s in corpus_gloss.split(';') if s.strip()]
    if len(senses) <= 1:
        return False
    word_counts = [len(s.split()) for s in senses]
    if all(wc <= 2 for wc in word_counts):
        return False
    if word_counts[0] <= 2 and all(word_counts[i] > 2 for i in range(1, len(senses))):
        return False
    return True


def voice_class(voice):
    if voice in ("Active", "Deponent", "Middle", "Middle/Passive Deponent",
                 "Middle/Passive", "Middle or Passive"):
        return "act"
    return "pass"


def get_base(corpus_gloss, sense_index=None):
    if not corpus_gloss:
        return None
    senses = [s.strip() for s in corpus_gloss.split(';') if s.strip()]
    if not senses:
        return None
    idx = 0 if sense_index is None else max(0, min(sense_index, len(senses) - 1))
    chosen = senses[idx]
    first = chosen.split(',')[0].strip()
    if first.lower().startswith("to "):
        first = first[3:].strip()
    first = re.split(r'/', first)[0].strip()
    first_word = first.split()[0].strip() if first else ''
    return first_word if first_word else None


def _past_ed(b):
    if b.endswith("e") and not b.endswith("ee"): return b + "d"
    if b.endswith("y") and len(b) > 1 and b[-2] not in "aeiou": return b[:-1] + "ied"
    return b + "ed"

def _ing_form(b):
    if b.endswith("e") and not b.endswith("ee"): return b[:-1] + "ing"
    return b + "ing"


def apply_verb_rules(strongs_id, tense, mood, voice, person, number,
                     corpus_gloss, sense_index=None):
    vc = voice_class(voice or "")
    mk = _mk(tense, mood, vc, person, number)
    mk_no_pn = _mk(tense, mood, vc)
    irr = IRREGULAR_VERBS.get(strongs_id, {})
    if mk in irr: return irr[mk]
    if mk_no_pn in irr: return irr[mk_no_pn]
    base = get_base(corpus_gloss, sense_index=sense_index)
    if not base: return corpus_gloss or ""
    b = base.lower()
    if mood == "Infinitive": return f"to {b}"
    if mood == "Participle":
        if tense in ("Aorist", "Perfect"):
            return f"having been {_past_ed(b)}" if vc == "pass" else f"having {_past_ed(b)}"
        if tense == "Future": return f"about to {b}"
        return f"being {_past_ed(b)}" if vc == "pass" else _ing_form(b)
    if mood == "Imperative":
        return f"be {_past_ed(b)}" if vc == "pass" else b
    if mood == "Subjunctive": return f"may {b}"
    if mood == "Optative":    return f"might {b}"
    pl = number == "Plural"
    if tense == "Present":
        if vc == "pass": return f"are {_past_ed(b)}" if pl else f"is {_past_ed(b)}"
        if person == "3rd" and not pl:
            if b.endswith(("s","sh","ch","x","z")): return b + "es"
            if b.endswith("y") and len(b) > 1 and b[-2] not in "aeiou": return b[:-1] + "ies"
            return b + "s"
        return b
    if tense == "Imperfect":
        if vc == "pass": return f"were being {_past_ed(b)}" if pl else f"was being {_past_ed(b)}"
        return f"were {_ing_form(b)}" if pl else f"was {_ing_form(b)}"
    if tense == "Future":
        return f"will be {_past_ed(b)}" if vc == "pass" else f"will {b}"
    if tense == "Aorist":
        return (f"were {_past_ed(b)}" if pl else f"was {_past_ed(b)}") if vc == "pass" else _past_ed(b)
    if tense == "Perfect":
        if vc == "pass": return f"have been {_past_ed(b)}" if pl else f"has been {_past_ed(b)}"
        return f"have {_past_ed(b)}" if pl else f"has {_past_ed(b)}"
    if tense == "Pluperfect":
        return f"had been {_past_ed(b)}" if vc == "pass" else f"had {_past_ed(b)}"
    return b


def derive_gloss(token, corpus_gloss, sense_index=None):
    pos    = token["pos_code"]
    sid    = token["strongs_id"]
    tense  = token["tense"]
    voice  = token["voice"]
    mood   = token["mood"]
    person = token["person"]
    number = token["number"]
    if sid and sid in FUNCTION_WORD_OVERRIDES:
        return FUNCTION_WORD_OVERRIDES[sid]
    if pos == "T":
        return "the"
    if pos == "V" and tense:
        return apply_verb_rules(sid, tense, mood, voice, person, number, corpus_gloss,
                                sense_index=sense_index)
    if corpus_gloss:
        senses = [s.strip() for s in corpus_gloss.split(';') if s.strip()]
        idx = 0 if sense_index is None else max(0, min(sense_index, len(senses) - 1))
        first = senses[idx].split(',')[0].strip() if senses else corpus_gloss
        if first.lower().startswith("to ") and pos != "V":
            first = first[3:].strip()
        return first
    return token.get("english_gloss") or ""


# ── Database helpers ──────────────────────────────────────────────────────────

def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    # Ensure sense_index column exists (V19 migration may not have run yet)
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE gloss_set_entry
            ADD COLUMN IF NOT EXISTS sense_index SMALLINT
        """)
    conn.commit()
    return conn


def get_gloss_set_id(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM gloss_set WHERE name = 'lite_auto'")
        row = cur.fetchone()
        if not row:
            print("ERROR: gloss_set 'lite_auto' not found. Run B1 first.")
            sys.exit(1)
        return row[0]


def get_polysemous_tokens(conn, book_id=BOOK_ID_1PETER):
    """
    Return polysemous content-word tokens for the given scope.
    book_id=None → full NT (books 40–66).
    """
    book_filter = "AND v.book_id = %s" if book_id is not None else "AND v.book_id BETWEEN 40 AND 66"
    params = (book_id,) if book_id is not None else ()

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"""
            SELECT
                vw.id           AS verse_word_id,
                vw.verse_id,
                vw.pos_code,
                vw.tense,
                vw.voice,
                vw.mood,
                vw.person,
                vw.number,
                vw.grammatical_case,
                vw.english_gloss,
                vw.surface_form,
                vw.morphology_code,
                l.strongs_id,
                l.lemma,
                m.short_gloss   AS corpus_gloss,
                gse.gloss       AS lite_gloss,
                gse.sense_index AS current_sense_index,
                STRING_AGG(vw2.surface_form, ' ' ORDER BY vw2.position) AS verse_greek
            FROM verse_word vw
            JOIN verse v ON v.id = vw.verse_id
            JOIN lexeme l ON vw.lexeme_id = l.id
            JOIN lexeme_meaning m ON m.lexeme_id = l.id AND m.source = 'corpus'
            LEFT JOIN gloss_set gs ON gs.name = 'lite_auto'
            LEFT JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id AND gse.gloss_set_id = gs.id
            JOIN verse_word vw2 ON vw2.verse_id = vw.verse_id
            WHERE vw.content_word = TRUE
              AND vw.pos_code NOT IN ('T', 'P', 'D', 'C', 'X')
              AND m.short_gloss LIKE '%%;%%'
              AND vw.morphology_code NOT LIKE 'N-%%-P'
              AND vw.morphology_code NOT LIKE 'N-%%-L'
              {book_filter}
            GROUP BY vw.id, vw.verse_id, vw.pos_code, vw.tense, vw.voice, vw.mood,
                     vw.person, vw.number, vw.grammatical_case, vw.english_gloss,
                     vw.surface_form, vw.morphology_code,
                     l.strongs_id, l.lemma, m.short_gloss,
                     gse.gloss, gse.sense_index
            ORDER BY vw.id
        """, params)
        return [dict(r) for r in cur.fetchall()]


# ── Prompt builder ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Greek New Testament scholar selecting the best sense for a Greek word in context.

You will be given:
- The Greek lemma and its corpus definition (semicolon-separated senses)
- The morphological form (tense/mood/voice if a verb)
- The full Greek verse text as context

Your task: identify which sense index (0-based) best fits this specific occurrence.

Rules:
- Reply with ONLY a single integer: 0, 1, 2, etc.
- 0 = first sense (before first semicolon), 1 = second sense, etc.
- Sense 0 is the established primary NT meaning for this word. Select sense 0 unless the Greek verse context makes it clearly wrong for this specific occurrence.
- Do not select a different sense merely because another sense is shorter or seems more scholarly.
- Do not explain. No punctuation. Just the integer."""


def build_prompt(token):
    senses = [s.strip() for s in token["corpus_gloss"].split(';')]
    sense_list = '\n'.join(f"  {i}: {s}" for i, s in enumerate(senses))
    morph_parts = []
    for field in ["tense", "mood", "voice", "person", "number", "grammatical_case"]:
        val = token.get(field)
        if val:
            morph_parts.append(f"{field.replace('_', ' ').title()}: {val}")
    morph = ', '.join(morph_parts) if morph_parts else 'N/A'
    lemma = token.get("lemma") or token["strongs_id"]
    verse_greek = token.get("verse_greek") or ""

    return (
        f"Lemma: {lemma} ({token['strongs_id']})\n"
        f"Morphology: {morph}\n"
        f"Corpus senses:\n{sense_list}\n"
        f"Greek verse: {verse_greek}\n\n"
        f"Which sense index (0-based) best fits this occurrence?"
    )


# ── Submit ─────────────────────────────────────────────────────────────────────

def cmd_submit(conn, dry_run=False, limit=0, book_id=BOOK_ID_1PETER):
    scope_label = 'full NT' if book_id is None else BOOK_ABBREV.get(book_id, f'book {book_id}')
    tokens = get_polysemous_tokens(conn, book_id=book_id)
    print(f"Found {len(tokens)} polysemous content tokens in {scope_label}")

    # Layer 2 pre-filter: skip tokens where sense 0 is deterministically correct
    before = len(tokens)
    tokens = [t for t in tokens if needs_c1(t['corpus_gloss'])]
    filtered = before - len(tokens)
    print(f"  Layer 2 filter: {filtered} skipped (sense 0 deterministic), {len(tokens)} need C1")

    if limit:
        tokens = tokens[:limit]
        print(f"  (limited to {limit} for preview)")

    if not tokens:
        print("Nothing to submit.")
        return

    # Build batch requests
    requests = []
    id_map   = {}  # custom_id → token dict

    for t in tokens:
        custom_id = f"c1_1p_{t['verse_word_id']}"
        prompt = build_prompt(t)
        if dry_run:
            senses = [s.strip() for s in t["corpus_gloss"].split(';')]
            word_counts = [len(s.split()) for s in senses]
            print(f"\n── {t['strongs_id']} ({t['lemma']}) id={t['verse_word_id']} ──")
            sense_display = ' | '.join('%s(%dw)' % (s, wc) for s, wc in zip(senses, word_counts))
            print(f"   Senses ({len(senses)}): {sense_display}")
            print(f"   B1 gloss: {t['lite_gloss']}")
            print(f"   Morph code: {t.get('morphology_code')}")
            print(f"   Verse: {t['verse_greek'][:80]}")
            print(f"   Current sense_index: {t['current_sense_index']}")
            continue
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 8,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
        })
        id_map[custom_id] = {
            "verse_word_id":   t["verse_word_id"],
            "corpus_gloss":    t["corpus_gloss"],
            "pos_code":        t["pos_code"],
            "strongs_id":      t["strongs_id"],
            "tense":           t["tense"],
            "voice":           t["voice"],
            "mood":            t["mood"],
            "person":          t["person"],
            "number":          t["number"],
            "grammatical_case": t.get("grammatical_case"),
            "english_gloss":   t.get("english_gloss"),
            "current_sense_index": t["current_sense_index"],
        }

    if dry_run:
        print(f"\n── Dry run complete: {len(tokens)} prompts shown ──")
        return

    # Cost estimate
    n = len(requests)
    est_in  = n * 300   # ~300 input tokens per request
    est_out = n * 5     # ~5 output tokens (just a digit)
    est_cost = est_in / 1_000_000 * COST_INPUT_PER_M + est_out / 1_000_000 * COST_OUTPUT_PER_M
    print(f"\nReady to submit {n} requests")
    print(f"Estimated cost: ${est_cost:.4f}  ({est_in:,} in / {est_out:,} out tokens)")
    print("Model: claude-haiku-4-5-20251001 (batch API)")
    input("\nPress Enter to submit (Ctrl+C to abort)...")

    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)

    client = anthropic.Anthropic()
    batch  = client.beta.messages.batches.create(requests=requests)
    print(f"\nBatch submitted: {batch.id}")
    print(f"Status: {batch.processing_status}")

    state = {"batch_id": batch.id, "id_map": id_map, "book_id": book_id}
    sf = batch_state_file(book_id)
    sf.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"State saved to {sf}")
    print("\nNext: python scripts/run_c1.py --status  (then --collect when done)")


# ── Status ─────────────────────────────────────────────────────────────────────

def cmd_status(book_id=BOOK_ID_1PETER, batch_id_override=None):
    batch_id = batch_id_override

    if not batch_id:
        sf = batch_state_file(book_id)
        content = ''
        if sf.exists():
            content = sf.read_text(encoding='utf-8').strip()
        if not content:
            # State file missing or empty — scan for any c1 state file
            data_dir = Path(__file__).parent.parent / "data"
            found = sorted(data_dir.glob("c1-*-batch.json"))
            for candidate in reversed(found):
                c = candidate.read_text(encoding='utf-8').strip()
                if c:
                    content = c
                    print(f"Using state file: {candidate.name}")
                    break
        if content:
            try:
                batch_id = json.loads(content).get("batch_id")
            except json.JSONDecodeError:
                pass

    if not batch_id:
        print("No batch ID found. Pass --batch-id <id> or run --submit first.")
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)

    client = anthropic.Anthropic()
    batch  = client.beta.messages.batches.retrieve(batch_id)
    rc = batch.request_counts
    print(f"Batch {batch.id}")
    print(f"Status: {batch.processing_status}")
    print(f"  processing={rc.processing}  succeeded={rc.succeeded}  errored={rc.errored}")
    if batch.processing_status == "ended":
        print("\nBatch complete — run --collect to apply results.")


# ── Collect ────────────────────────────────────────────────────────────────────

def load_token_meta_from_db(conn, verse_word_ids):
    """Re-fetch token metadata from DB by verse_word_id list.
    Used when the state file id_map is missing (e.g. due to encoding error on submit).
    """
    if not verse_word_ids:
        return {}
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT vw.id AS verse_word_id, vw.pos_code, vw.tense, vw.voice, vw.mood,
                   vw.person, vw.number, vw.grammatical_case, vw.english_gloss,
                   l.strongs_id, m.short_gloss AS corpus_gloss,
                   gse.sense_index AS current_sense_index
            FROM verse_word vw
            LEFT JOIN lexeme l ON vw.lexeme_id = l.id
            LEFT JOIN lexeme_meaning m ON m.lexeme_id = l.id AND m.source = 'corpus'
            LEFT JOIN gloss_set gs ON gs.name = 'lite_auto'
            LEFT JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id AND gse.gloss_set_id = gs.id
            WHERE vw.id = ANY(%s)
        """, (list(verse_word_ids),))
        return {row["verse_word_id"]: dict(row) for row in cur.fetchall()}


def cmd_collect(conn, book_id=BOOK_ID_1PETER, batch_id_override=None):
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)

    # Resolve batch_id and id_map — state file is optional if batch_id is known
    batch_id = batch_id_override
    id_map   = {}

    sf = batch_state_file(book_id)
    if sf.exists():
        content = sf.read_text(encoding='utf-8').strip()
        if content:
            state    = json.loads(content)
            batch_id = batch_id or state.get("batch_id")
            id_map   = state.get("id_map", {})
        else:
            print("State file is empty — will re-fetch token metadata from DB.")
    if batch_id_override:
        print(f"Using provided batch ID: {batch_id_override}")
        if not id_map:
            print("Token metadata will be re-fetched from DB via custom_id.")
    else:
        data_dir = Path(__file__).parent.parent / "data"
        found = sorted(data_dir.glob("c1-*-batch.json"))
        if found:
            sf = found[-1]
            print(f"Using state file: {sf.name}")
            state  = json.loads(sf.read_text(encoding='utf-8'))
            batch_id = batch_id or state.get("batch_id")
            id_map   = state.get("id_map", {})
        else:
            print("No state file and no --batch-id given. Cannot collect.")
            sys.exit(1)

    if not batch_id:
        print("ERROR: batch_id unknown. Pass --batch-id <id>.")
        sys.exit(1)

    client = anthropic.Anthropic()

    batch = client.beta.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        print(f"Batch not finished (status={batch.processing_status}). Run --status.")
        sys.exit(1)

    gloss_set_id = get_gloss_set_id(conn)

    # First pass: collect all results and parse verse_word_ids for DB fallback
    raw_results = list(client.beta.messages.batches.results(batch_id))
    print(f"Retrieved {len(raw_results)} results from API")

    # If id_map is empty (state file was lost), re-fetch token metadata from DB
    if not id_map:
        print("id_map missing — reconstructing token metadata from DB...")
        vw_ids = set()
        for result in raw_results:
            m2 = re.match(r'^c1_1p_(\d+)$', result.custom_id)
            if m2:
                vw_ids.add(int(m2.group(1)))
        id_map = load_token_meta_from_db(conn, vw_ids)
        # Remap: key by custom_id string for lookup below
        id_map = {f"c1_1p_{vwid}": meta for vwid, meta in id_map.items()}
        print(f"  Reconstructed {len(id_map)} token records from DB")

    # Collect results
    updates   = []   # list of {verse_word_id, sense_index, gloss}
    ok = skipped = failed = unchanged = 0
    total_input = total_output = 0

    for result in raw_results:
        meta = id_map.get(result.custom_id)
        if not meta:
            continue

        if result.result.type != "succeeded":
            failed += 1
            continue

        usage = result.result.message.usage
        total_input  += usage.input_tokens
        total_output += usage.output_tokens

        raw = result.result.message.content[0].text.strip()
        # Parse the sense index — expect a single digit
        m = re.match(r'^(\d+)', raw)
        if not m:
            print(f"  WARN: unexpected response for {result.custom_id!r}: {raw!r}")
            skipped += 1
            continue

        sense_index = int(m.group(1))
        corpus_gloss = meta["corpus_gloss"]
        senses = [s.strip() for s in corpus_gloss.split(';')]
        sense_index = min(sense_index, len(senses) - 1)  # clamp

        # If same as current, skip (no DB write needed)
        current = meta.get("current_sense_index")
        if current is not None and current == sense_index:
            unchanged += 1
            continue

        # Re-run B1 with the new sense to get the updated gloss
        new_gloss = derive_gloss(meta, corpus_gloss, sense_index=sense_index)

        updates.append({
            "verse_word_id": meta["verse_word_id"],
            "sense_index":   sense_index,
            "gloss":         new_gloss,
        })
        ok += 1

    cost = total_input / 1_000_000 * COST_INPUT_PER_M + total_output / 1_000_000 * COST_OUTPUT_PER_M
    print(f"Results: {ok} changed, {unchanged} same as current, {skipped} parse errors, {failed} API errors")
    print(f"Actual cost: ${cost:.4f}  ({total_input:,} in / {total_output:,} out tokens)")

    if not updates:
        print("No updates to apply.")
        return

    # Upsert sense_index + gloss into gloss_set_entry
    print(f"Updating {len(updates)} tokens in DB...")
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO gloss_set_entry (gloss_set_id, verse_word_id, gloss, sense_index)
            VALUES %s
            ON CONFLICT (gloss_set_id, verse_word_id)
                DO UPDATE SET gloss = EXCLUDED.gloss, sense_index = EXCLUDED.sense_index
        """, [(gloss_set_id, u["verse_word_id"], u["gloss"], u["sense_index"]) for u in updates])
    conn.commit()

    print(f"Done. {len(updates)} tokens updated with C1 sense selection + regenerated B1 gloss.")
    print("\nNext: restart the API server so the new glosses are served.")
    print("      (Or trigger cache eviction if running in prod.)")


# ── Reset ─────────────────────────────────────────────────────────────────────

def cmd_reset(conn, book_id=BOOK_ID_1PETER):
    """Clear C1 sense_index values for the given scope (keeps gloss intact)."""
    scope_label = 'full NT' if book_id is None else BOOK_ABBREV.get(book_id, f'book {book_id}')
    book_filter = "AND v.book_id = %s" if book_id is not None else "AND v.book_id BETWEEN 40 AND 66"
    params = (book_id,) if book_id is not None else ()
    with conn.cursor() as cur:
        cur.execute(f"""
            UPDATE gloss_set_entry gse
            SET sense_index = NULL
            FROM gloss_set gs, verse_word vw, verse v
            WHERE gs.name = 'lite_auto'
              AND gse.gloss_set_id = gs.id
              AND gse.verse_word_id = vw.id
              AND vw.verse_id = v.id
              {book_filter}
        """, params)
        n = cur.rowcount
    conn.commit()
    print(f"Cleared sense_index for {n} tokens in {scope_label}.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="C1 contextual sense selection — 1 Peter by default, or any book / full NT"
    )
    parser.add_argument("--submit",   action="store_true", help="Submit batch to Claude API")
    parser.add_argument("--status",   action="store_true", help="Check batch status")
    parser.add_argument("--collect",  action="store_true", help="Collect results and update DB")
    parser.add_argument("--reset",    action="store_true", help="Clear C1 sense_index for scope")
    parser.add_argument("--dry-run",  action="store_true", help="Preview prompts without API calls")
    parser.add_argument("--limit",    type=int, default=0,  help="Limit tokens for --dry-run preview")
    parser.add_argument("--all",      action="store_true",  help="Target full NT (all books 40–66)")
    parser.add_argument("--book",     type=int, default=None, metavar="BOOK_ID",
                        help="Target a single book by book_id (e.g. 45 for Romans). Default: 60 (1 Peter)")
    parser.add_argument("--batch-id", type=str, default=None, metavar="BATCH_ID",
                        help="Override batch ID for --collect (use if state file was lost)")
    args = parser.parse_args()

    # Resolve scope
    if args.all:
        book_id = None          # None = full NT in all helper functions
    elif args.book is not None:
        book_id = args.book
    else:
        book_id = BOOK_ID_1PETER

    if args.status:
        cmd_status(book_id=book_id, batch_id_override=args.batch_id)
        return

    print(f"Connecting to {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = get_conn()

    if args.reset:
        cmd_reset(conn, book_id=book_id)
    elif args.collect:
        cmd_collect(conn, book_id=book_id, batch_id_override=args.batch_id)
    elif args.submit or args.dry_run:
        cmd_submit(conn, dry_run=args.dry_run,
                   limit=args.limit or (10 if args.dry_run else 0),
                   book_id=book_id)
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
