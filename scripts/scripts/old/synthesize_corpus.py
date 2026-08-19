#!/usr/bin/env python3
"""
synthesize_corpus.py — AI corpus definition generator (Tier 4).

Uses the Anthropic Batch API: submit all words at once, collect results when done.
No per-minute rate limits. 50% cheaper than real-time API.

Usage:
  # Dry run — print prompts, no API calls
  python scripts/synthesize_corpus.py --dry-run --limit 3

  # Submit batch (all remaining words)
  python scripts/synthesize_corpus.py --submit

  # Check batch status
  python scripts/synthesize_corpus.py --status

  # Collect results and commit to DB (run after status shows 'ended')
  python scripts/synthesize_corpus.py --collect

  # Re-submit a single word for testing
  python scripts/synthesize_corpus.py --submit --strongs G3056 --reset

Requirements:
  pip install anthropic psycopg2-binary python-dotenv

Environment variables (all optional — defaults match dev profile):
  ANTHROPIC_API_KEY  — required (put in .env file in project root)
  DB_HOST            — default: localhost
  DB_PORT            — default: 5432
  DB_NAME            — default: interlinear_bible_dev
  DB_USER            — default: postgres
  DB_PASS            — default: letttech
"""

import os
import sys
import json
import time
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

# Load .env from project root (two levels up from scripts/)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic not installed. Run: pip install anthropic")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

AGDT_FILE   = os.path.join(os.path.dirname(__file__), "..", "data", "agdt-attestations.json")
BATCH_FILE  = os.path.join(os.path.dirname(__file__), "..", "data", "corpus-batch.json")
CORPUS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "corpus-lexicon.json")

MODEL           = "claude-haiku-4-5-20251001"
MAX_NT_EXAMPLES = 6
MAX_AGDT_EXAMPLES = 6

# Haiku batch pricing (50% off real-time)
COST_INPUT_PER_M  = 0.40
COST_OUTPUT_PER_M = 2.00

# ── Utilities ─────────────────────────────────────────────────────────────────

def nfc(s):
    return unicodedata.normalize("NFC", s) if s else ""


def load_agdt():
    if not os.path.exists(AGDT_FILE):
        print(f"WARNING: AGDT file not found at {AGDT_FILE} — classical attestations skipped")
        return {}
    with open(AGDT_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_batch_state():
    if os.path.exists(BATCH_FILE):
        with open(BATCH_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_batch_state(state):
    with open(BATCH_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_corpus_lexicon():
    """Load existing corpus-lexicon.json, or return empty dict."""
    if os.path.exists(CORPUS_FILE):
        with open(CORPUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_corpus_lexicon(data):
    with open(CORPUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_all_lexemes(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT
                l.id,
                l.strongs_id,
                l.lemma,
                l.transliteration,
                l.part_of_speech AS pos_code,
                EXISTS(
                    SELECT 1 FROM lexeme_meaning m
                    WHERE m.lexeme_id = l.id AND m.source = 'corpus'
                ) AS has_corpus
            FROM lexeme l
            ORDER BY l.strongs_id
        """)
        return [dict(r) for r in cur.fetchall()]


def get_meanings(conn, lexeme_id):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT source, short_gloss, full_definition
            FROM lexeme_meaning
            WHERE lexeme_id = %s
            ORDER BY display_order
        """, (lexeme_id,))
        return {r["source"]: dict(r) for r in cur.fetchall()}


def get_nt_occurrences(conn, lexeme_id, limit=MAX_NT_EXAMPLES):
    """
    Verses where the lexeme occurs, each with the whole verse's glosses as the snippet.

    The prompt labels this section "NT occurrences in context" and the whole ordering rule —
    define the NT sense first — rests on the model seeing that context. It was not seeing any.
    The previous query put `vw.lexeme_id = %s` in the WHERE, so string_agg aggregated the single
    matching token and every snippet was one word:

        Matt 5.32 — word
        Matt 5.37 — word
        Matt 7.24 — word

    Selecting the verse first and aggregating its words separately is what was meant. Found by
    scripts/live_corpus_synthesis_check.py (#190) on its first run.

    Note this does not change any definition already in the database — those 5,516 rows were all
    generated against the contextless prompt and only a re-run would revise them.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            WITH hits AS (
                SELECT DISTINCT vw.verse_id
                FROM verse_word vw
                WHERE vw.lexeme_id = %s
            )
            SELECT
                b.abbreviation AS book_abbrev,
                v.chapter,
                v.verse_num,
                string_agg(vw.english_gloss, ' ' ORDER BY vw.position) AS snippet
            FROM hits
            JOIN verse v ON v.id = hits.verse_id
            JOIN book b ON v.book_id = b.id
            JOIN verse_word vw ON vw.verse_id = v.id AND vw.english_gloss IS NOT NULL
            GROUP BY b.abbreviation, v.chapter, v.verse_num, v.id
            ORDER BY v.id
            LIMIT %s
        """, (lexeme_id, limit))
        return [dict(r) for r in cur.fetchall()]



# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(lexeme, meanings, nt_occurrences, agdt_data):
    lemma    = nfc(lexeme.get("lemma", ""))
    translit = lexeme.get("transliteration", "")
    pos      = lexeme.get("pos_code", "")
    strongs  = lexeme["strongs_id"]

    ugl       = meanings.get("ugl")
    abbsmith  = meanings.get("abbottsmith")
    thayer    = meanings.get("thayer")
    mounce    = meanings.get("mounce")
    lsj       = meanings.get("lsj")
    wikt      = meanings.get("wiktionary")
    strongs_m = meanings.get("strongs")

    agdt_atts = agdt_data.get(lemma, [])[:MAX_AGDT_EXAMPLES]

    lines = []
    lines.append(f"## Greek word: {lemma} ({translit}) — {strongs}")
    if pos:
        lines.append(f"Part of speech: {pos}")
    lines.append("")

    # ── NT usage first — AI must see actual NT context before any lexicon ────
    if nt_occurrences:
        lines.append("### NT occurrences in context")
        for i, occ in enumerate(nt_occurrences, 1):
            ref = f"{occ['book_abbrev']} {occ['chapter']}.{occ['verse_num']}"
            lines.append(f"{i}. {ref} — {occ['snippet'][:120]}")
        lines.append("")

    # ── NT-focused lexicons (modern → 19th-century) ──────────────────────────
    if ugl:
        lines.append("### UGL — unfoldingWord Greek Lexicon (modern NT Koine)")
        if ugl.get("short_gloss"):
            lines.append(ugl["short_gloss"])
        if ugl.get("full_definition") and ugl["full_definition"] != ugl.get("short_gloss"):
            lines.append(ugl["full_definition"][:600])
        lines.append("")

    if abbsmith:
        lines.append("### Abbott-Smith (NT Greek lexicon)")
        if abbsmith.get("short_gloss"):
            lines.append(abbsmith["short_gloss"])
        if abbsmith.get("full_definition") and abbsmith["full_definition"] != abbsmith.get("short_gloss"):
            lines.append(abbsmith["full_definition"][:400])
        lines.append("")

    if thayer:
        lines.append("### Thayer (Greek-English Lexicon of the NT, 1889)")
        if thayer.get("short_gloss"):
            lines.append(thayer["short_gloss"])
        if thayer.get("full_definition") and thayer["full_definition"] != thayer.get("short_gloss"):
            lines.append(thayer["full_definition"][:400])
        lines.append("")

    if mounce:
        lines.append("### Mounce (Concise Greek-English Dictionary)")
        if mounce.get("short_gloss"):
            lines.append(mounce["short_gloss"])
        lines.append("")

    # ── Classical and broad-coverage lexicons ────────────────────────────────
    if lsj:
        lines.append("### LSJ (Liddell-Scott-Jones — classical through Koine)")
        if lsj.get("short_gloss"):
            lines.append(lsj["short_gloss"])
        if lsj.get("full_definition") and lsj["full_definition"] != lsj.get("short_gloss"):
            lines.append(lsj["full_definition"][:500])
        lines.append("")

    if wikt:
        lines.append("### Wiktionary (Ancient Greek senses)")
        if wikt.get("full_definition"):
            lines.append(wikt["full_definition"][:400])
        elif wikt.get("short_gloss"):
            lines.append(wikt["short_gloss"])
        lines.append("")

    if agdt_atts:
        lines.append("### Classical attestations (Homer, Sophocles, Plato, etc.)")
        for i, att in enumerate(agdt_atts, 1):
            lines.append(f"{i}. {att['author']}, {att['work']} ({att['era']}): \"{att['text']}\"")
        lines.append("")

    if strongs_m:
        lines.append("### Strong's (KJV gloss)")
        if strongs_m.get("short_gloss"):
            lines.append(strongs_m["short_gloss"])
        lines.append("")

    prompt_body = "\n".join(lines)

    system = (
        "You are an elite Greek lexicographer writing scholarly definitions grounded in the full "
        "history of Greek usage from Homer through the New Testament. "
        "You understand that NT Greek cannot be read in isolation — it sits at the intersection of "
        "three linguistic worlds:\n"
        "  1. CLASSICAL GREEK (800–300 BCE): Homer, Sophocles, Plato, Thucydides — the root meanings.\n"
        "  2. SEPTUAGINT / LXX (250–100 BCE): The Greek translation of the Hebrew OT. This is "
        "critical. Jewish writers like Paul, the author of Hebrews, and others were steeped in the "
        "LXX. When they chose a Greek word, they often deliberately invoked its LXX associations — "
        "its Hebrew equivalents (like taw, chesed, shalom), its theological weight in the Torah and "
        "Prophets, and its covenant context. A word's LXX usage often unlocks the NT meaning.\n"
        "  3. KOINE / NT GREEK (300 BCE–200 CE): The everyday and theological Greek of the NT.\n\n"
        "CRITICAL ORDERING RULE: Always define the word as it is used in the NEW TESTAMENT first. "
        "Classical and etymological meanings are background context — they explain how the word arrived "
        "at its NT meaning, but they are NOT the definition. A word's etymology is not its meaning. "
        "δόξα does not mean 'opinion' in the NT; it means 'glory'. ἁμαρτία does not mean 'missing the mark'; "
        "it means 'sin'. The classical root explains the metaphor; the NT usage is the definition.\n\n"
        "For each word, trace the semantic journey: classical root → LXX shift → NT arrival. "
        "Apply the THREE-POINT ANCHOR method:\n"
        "  a) HEBREW ROOT: Which Hebrew word(s) did the LXX use this Greek word to translate? "
        "Give the Hebrew word, its transliteration, its Strong's H-number (e.g. H4394), and its literal concrete meaning. "
        "This is critical — Hebrew roots are often concrete images (e.g. milluim = 'filling of hands') "
        "that reveal the physical picture behind the abstract Greek theological term.\n"
        "  b) LXX BRIDGE: Where and how was this word used in the Septuagint? Note the semantic weight "
        "it carried for Jewish readers steeped in the Torah and Prophets.\n"
        "  c) NT ARRIVAL: What does the word mean in the NT — not what it implies, not what theologians "
        "derived from it, but what the NT authors meant when they chose this word. This is the primary sense.\n"
        "Your definitions are independent of any English Bible translation. "
        "Respond ONLY with a valid JSON object — no prose, no markdown, no code fences. "
        # Both additions below are formatting, not content. Weaker models honour neither: the
        # live check (#190) found free providers running the numbered senses together in one
        # paragraph, and emitting literal newlines inside JSON strings — which parse_result does
        # not survive, so the word is simply lost from the batch. Haiku happened to get both
        # right (5,500 of 5,516 stored definitions are correctly line-numbered), so this was
        # invisible until a second model ran the same prompt. Saying it explicitly costs nothing
        # and does not change what any model is asked to *say*.
        "Inside JSON string values, write line breaks as the two characters \\n — never as a "
        "literal newline, which makes the JSON unparseable."
    )

    user = (
        f"{prompt_body}"
        "Write an elite corpus definition for this word. Respond ONLY with this JSON:\n"
        "{\n"
        '  "shortGloss": "2-6 word NT-era meaning first; use semicolons only for genuinely distinct '
        'NT senses. The first term must reflect how the word is used in the New Testament, not its '
        'classical or etymological root. Classical/etymological meanings belong in fullDefinition, '
        # No parentheses: this leaked into shipped data once already and needed
        # clean_corpus_shortgloss.py to strip it out afterwards. The gloss is rendered directly
        # on a reader token card, where "glory (radiant divine splendor)" does not fit and is not
        # what a gloss is for. Forbidding it in the prompt is cheaper than repairing it again —
        # the live check (#190) still produced it for δόξα before this line existed.
        'not as the leading term in shortGloss. Use no parentheses, brackets or qualifiers of any '
        'kind — bare terms only; nuance belongs in fullDefinition.",\n'
        '  "fullDefinition": "Numbered senses (1. 2. 3.), each starting on its own line — put a '
        '\\n before every number so 2. and 3. begin a new line rather than continuing the '
        'previous paragraph. '
        'Structure as: Sense 1 (NT primary — how the word is used in the NT, grounded in koine and LXX), '
        'Sense 2 (LXX/Septuagint bridge) if it meaningfully differs from NT sense, '
        'Sense 3 (Classical/etymological) to show semantic development. '
        'Do NOT lead with classical meaning. The classical root is background, not the definition. '
        'Where the LXX usage bridges a Hebrew concept to NT meaning, state the Hebrew word '
        'and its significance explicitly. Max 450 words.",\n'
        '  "lxxNote": "The Three-Point Anchor: (1) Hebrew root — give the Hebrew word, transliteration, '
        'Strong\'s H-number, and its literal concrete meaning; (2) how the LXX used this word and what '
        'Hebrew concept it carried; (3) how the NT author exploited this LXX weight for theological depth. '
        'Be specific about verse references. Set to null only if the word has no Hebrew/LXX connection."\n'
        "}"
    )

    return system, user


# ── Parse result helper ───────────────────────────────────────────────────────

def parse_result(raw_text):
    """Parse Claude JSON response. Returns (short_gloss, full_definition) or raises."""
    raw = raw_text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    short_gloss     = result.get("shortGloss") or ""
    full_definition = result.get("fullDefinition") or ""
    lxx_note = result.get("lxxNote") or ""

    if isinstance(lxx_note, dict):
        lxx_note = " ".join(str(v) for v in lxx_note.values() if v)
    elif not isinstance(lxx_note, str):
        lxx_note = str(lxx_note) if lxx_note else ""

    if lxx_note:
        full_definition = full_definition + "\n\nLXX: " + lxx_note

    return short_gloss, full_definition


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_submit(args, client, conn, agdt_data):
    """Build prompts for all remaining words and submit as a single batch."""
    lexemes = get_all_lexemes(conn)
    print(f"  {len(lexemes)} NT lexemes found")

    if args.strongs:
        lexemes = [l for l in lexemes if l["strongs_id"] == args.strongs.upper()]
    elif not args.reset:
        lexemes = [l for l in lexemes if not l["has_corpus"]]

    if args.limit:
        lexemes = lexemes[:args.limit]

    print(f"  {len(lexemes)} to submit\n")

    if not lexemes:
        print("Nothing to submit — all words already have corpus entries.")
        return

    print("Building prompts...")
    requests = []
    id_map = {}  # strongs_id -> lexeme_id

    for i, lexeme in enumerate(lexemes, 1):
        meanings       = get_meanings(conn, lexeme["id"])
        nt_occurrences = get_nt_occurrences(conn, lexeme["id"])
        system, user   = build_prompt(lexeme, meanings, nt_occurrences, agdt_data)

        requests.append({
            "custom_id": lexeme["strongs_id"],
            "params": {
                "model": MODEL,
                "max_tokens": 1600,
                "system": system,
                "messages": [{"role": "user", "content": user}]
            }
        })
        id_map[lexeme["strongs_id"]] = lexeme["id"]

        if i % 500 == 0:
            print(f"  Built {i}/{len(lexemes)} prompts...")

    print(f"  {len(requests)} prompts ready")

    if args.dry_run:
        print("\n[DRY RUN] First prompt preview:")
        print(requests[0]["params"]["messages"][0]["content"][:800])
        print(f"\n[DRY RUN] Would submit {len(requests)} requests. No API call made.")
        return

    print("\nSubmitting batch to Anthropic...")
    batch = client.beta.messages.batches.create(requests=requests)

    state = {
        "batch_id":     batch.id,
        "submitted_at": datetime.utcnow().isoformat(),
        "count":        len(requests),
        "id_map":       id_map,
    }
    save_batch_state(state)

    print(f"\n  Batch ID:  {batch.id}")
    print(f"  Status:    {batch.processing_status}")
    print(f"  Words:     {len(requests)}")
    print(f"\nBatch submitted. Batches typically complete in 1–4 hours.")
    print(f"Check status:   python scripts/synthesize_corpus.py --status")
    print(f"Collect when done: python scripts/synthesize_corpus.py --collect")


def cmd_status(args, client):
    """Poll the saved batch for current status."""
    state = load_batch_state()
    if not state:
        print("No batch found. Run --submit first.")
        return

    batch_id = state["batch_id"]
    batch = client.beta.messages.batches.retrieve(batch_id)

    counts = batch.request_counts
    print(f"Batch ID:    {batch_id}")
    print(f"Submitted:   {state.get('submitted_at', 'unknown')}")
    print(f"Words:       {state['count']}")
    print(f"Status:      {batch.processing_status}")
    print(f"Processing:  {counts.processing}")
    print(f"Succeeded:   {counts.succeeded}")
    print(f"Errored:     {counts.errored}")
    print(f"Canceled:    {counts.canceled}")
    print(f"Expired:     {counts.expired}")

    if batch.processing_status == "ended":
        print(f"\nBatch is done! Run: python scripts/synthesize_corpus.py --collect")
    else:
        pct = 0
        total = counts.processing + counts.succeeded + counts.errored
        if total > 0:
            pct = (counts.succeeded + counts.errored) / total * 100
        print(f"\nProgress: {pct:.0f}% — check again in a few minutes.")


def cmd_collect(args, client, conn):
    """Stream batch results and write to corpus-lexicon.json.
    Run POST /admin/import-corpus?reset=true afterwards to push to the DB.
    """
    state = load_batch_state()
    if not state:
        print("No batch found. Run --submit first.")
        return

    batch_id = state["batch_id"]

    batch = client.beta.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        counts = batch.request_counts
        print(f"Batch not finished yet. Status: {batch.processing_status}")
        print(f"  Processing: {counts.processing}  Succeeded: {counts.succeeded}  Errored: {counts.errored}")
        print(f"Run --status to check progress.")
        return

    print(f"Collecting results for batch {batch_id}...")
    print(f"Words in batch: {state['count']}\n")

    # Load existing corpus so we only overwrite words that came back in this batch
    corpus = load_corpus_lexicon()

    ok = 0; failed = 0; skipped = 0
    total_input = 0; total_output = 0

    for result in client.beta.messages.batches.results(batch_id):
        strongs_id = result.custom_id

        if result.result.type == "succeeded":
            message = result.result.message
            raw = message.content[0].text

            try:
                short_gloss, full_definition = parse_result(raw)
            except Exception as e:
                print(f"  {strongs_id} PARSE ERROR: {e}", flush=True)
                failed += 1
                continue

            corpus[strongs_id] = {
                "shortGloss":     short_gloss[:200],
                "fullDefinition": full_definition[:4000],
            }

            in_tok  = message.usage.input_tokens
            out_tok = message.usage.output_tokens
            total_input  += in_tok
            total_output += out_tok
            ok += 1

            if ok % 100 == 0:
                running_cost = (total_input / 1_000_000 * COST_INPUT_PER_M +
                                total_output / 1_000_000 * COST_OUTPUT_PER_M)
                print(f"  {ok} collected... (running cost ${running_cost:.3f})", flush=True)

        elif result.result.type == "errored":
            err = result.result.error
            print(f"  {strongs_id} API ERROR: {err.type}", flush=True)
            failed += 1

        else:
            print(f"  {strongs_id} unexpected result type: {result.result.type}", flush=True)
            skipped += 1

    save_corpus_lexicon(corpus)

    total_cost = (total_input / 1_000_000 * COST_INPUT_PER_M +
                  total_output / 1_000_000 * COST_OUTPUT_PER_M)

    print(f"\nDone — {ok} collected, {failed} failed, {skipped} skipped")
    print(f"Tokens — {total_input:,} input / {total_output:,} output")
    print(f"Cost   — ${total_cost:.4f} this batch")
    print(f"\nResults written to: {CORPUS_FILE}")
    print(f"To import into DB:")
    print(f"  curl -X POST 'http://localhost:8080/api/admin/import-corpus?reset=true'")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Corpus synthesis via Anthropic Batch API")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--submit",   action="store_true", help="Build prompts and submit batch")
    mode.add_argument("--status",   action="store_true", help="Check status of submitted batch")
    mode.add_argument("--collect",  action="store_true", help="Collect batch results and commit to DB")

    parser.add_argument("--dry-run", action="store_true", help="Print prompts, no API calls (use with --submit)")
    parser.add_argument("--limit",   type=int, default=0,  help="Process at most N lexemes (use with --submit)")
    parser.add_argument("--reset",   action="store_true",  help="Re-generate already-done words (use with --submit)")
    parser.add_argument("--strongs", type=str, default="", help="Single Strong's ID only, e.g. G3056")
    args = parser.parse_args()

    if not (args.submit or args.status or args.collect or args.dry_run):
        parser.print_help()
        print("\nQuick start:")
        print("  python scripts/synthesize_corpus.py --submit    # submit all remaining words")
        print("  python scripts/synthesize_corpus.py --status    # check progress")
        print("  python scripts/synthesize_corpus.py --collect   # commit results to DB")
        sys.exit(0)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env in the project root.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key) if api_key else None

    if args.status:
        cmd_status(args, client)
        return

    print(f"Connecting to DB {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"ERROR: DB connection failed — {e}")
        sys.exit(1)

    if args.submit or args.dry_run:
        print("Loading AGDT attestations...")
        agdt_data = load_agdt()
        print(f"  {len(agdt_data)} lemmas in AGDT index")
        cmd_submit(args, client, conn, agdt_data)
    elif args.collect:
        cmd_collect(args, client, conn)

    conn.close()


if __name__ == "__main__":
    main()
