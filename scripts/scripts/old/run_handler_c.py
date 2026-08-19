#!/usr/bin/env python3
"""
run_handler_c.py — Handler C: Disambiguation (AI sense classification).

One-time batch job. For each polysemous token (is_polysemous=true on its lexeme),
submits a classification prompt to Claude Batch API. The AI selects one sense_index
from the options in lexeme_sense. Result stored permanently in token_sense_override.

The AI is a SELECTOR, not a WRITER. It cannot generate new words. It receives a
numbered sense list and returns only an integer index. This prevents hallucination
and keeps all output grounded in the curated lexeme_sense data.

After --collect, generate_lite_glosses.py automatically uses the AI-selected sense
for polysemous tokens (via the token_sense_override join in get_tokens()).

Usage:
  python scripts/run_handler_c.py --dry-run        # preview prompts, no API call
  python scripts/run_handler_c.py --submit         # submit batch to Claude API
  python scripts/run_handler_c.py --status         # check batch progress
  python scripts/run_handler_c.py --collect        # write results to token_sense_override
  python scripts/run_handler_c.py --submit --limit 20   # test run on 20 tokens
  python scripts/run_handler_c.py --submit --strongs G4151  # one lemma only

Requirements:
  pip install anthropic psycopg2-binary python-dotenv
"""

import os, sys, json, re, argparse
from pathlib import Path
from datetime import datetime

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

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic")
    sys.exit(1)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

# Haiku is sufficient for classification — cheap and fast
MODEL = "claude-haiku-4-5-20251001"

BATCH_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "handler-c-batch.json")

BOOK_NAMES = {
    40: "Matthew", 41: "Mark", 42: "Luke", 43: "John",
    44: "Acts", 45: "Romans", 46: "1 Corinthians", 47: "2 Corinthians",
    48: "Galatians", 49: "Ephesians", 50: "Philippians", 51: "Colossians",
    52: "1 Thessalonians", 53: "2 Thessalonians", 54: "1 Timothy",
    55: "2 Timothy", 56: "Titus", 57: "Philemon", 58: "Hebrews",
    59: "James", 60: "1 Peter", 61: "2 Peter", 62: "1 John",
    63: "2 John", 64: "3 John", 65: "Jude", 66: "Revelation",
}

# =============================================================================
# DB HELPERS
# =============================================================================

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def load_batch_state():
    if os.path.exists(BATCH_FILE):
        with open(BATCH_FILE) as f:
            return json.load(f)
    return None


def save_batch_state(state):
    os.makedirs(os.path.dirname(BATCH_FILE), exist_ok=True)
    with open(BATCH_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_polysemous_tokens(conn, strongs=None, limit=0, reset=False):
    """Fetch all polysemous tokens with verse context and sense options."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

        # Skip tokens already classified unless --reset
        already_done = set()
        if not reset:
            cur.execute("SELECT verse_word_id FROM token_sense_override")
            already_done = {r[0] for r in cur.fetchall()}

        q = """
            SELECT
                vw.id              AS verse_word_id,
                vw.surface_form,
                vw.pos_code,
                vw.tense,
                vw.voice,
                vw.mood,
                vw.grammatical_case,
                vw.dep_relation,
                l.strongs_id,
                l.lemma,
                v.book_id,
                v.chapter,
                v.verse_num,
                btv.verse_text
            FROM verse_word vw
            JOIN lexeme l ON vw.lexeme_id = l.id
            JOIN verse v ON vw.verse_id = v.id
            LEFT JOIN bible_translation_verse btv
                ON btv.book_id = v.book_id
                AND btv.chapter = v.chapter
                AND btv.verse_num = v.verse_num
                AND btv.translation_code = 'BSB'
            WHERE l.is_polysemous = true
        """
        params = []
        if strongs:
            q += " AND l.strongs_id = %s"
            params.append(strongs.upper())

        q += " ORDER BY l.strongs_id, vw.id"
        if limit:
            q += f" LIMIT {limit}"

        cur.execute(q, params)
        tokens = [dict(r) for r in cur.fetchall()]

        if already_done:
            tokens = [t for t in tokens if t["verse_word_id"] not in already_done]

        # Fetch sense options for each lemma (cached by strongs_id)
        sense_cache = {}
        for t in tokens:
            sid = t["strongs_id"]
            if sid not in sense_cache:
                cur.execute("""
                    SELECT ls.sense_index, ls.gloss
                    FROM lexeme_sense ls
                    JOIN lexeme l ON ls.lexeme_id = l.id
                    WHERE l.strongs_id = %s
                    ORDER BY ls.sense_index
                """, (sid,))
                sense_cache[sid] = [dict(r) for r in cur.fetchall()]
            t["senses"] = sense_cache[sid]

        return tokens


# =============================================================================
# PROMPT BUILDER
# =============================================================================

SYSTEM_PROMPT = """You are a Greek New Testament lexical classifier.

Your task: given a Greek word in its verse context, select the most appropriate sense
from a numbered list. You are a SELECTOR only — you must return one of the provided
sense indexes. You cannot generate new words or senses not in the list.

Respond with JSON only. No explanation. Format:
{"sense_index": <integer>, "confidence": "high"|"medium"|"low"}

confidence guide:
  high   — the context makes the meaning clear beyond reasonable doubt
  medium — the sense is likely but another sense is plausible
  low    — the context is ambiguous; you are making a best guess"""


def build_prompt(token):
    """Build the classification prompt for one polysemous token."""
    sid          = token["strongs_id"]
    surface      = token["surface_form"] or ""
    lemma        = token["lemma"] or sid
    book_name    = BOOK_NAMES.get(token["book_id"], f"Book {token['book_id']}")
    ref          = f"{book_name} {token['chapter']}:{token['verse_num']}"
    verse_text   = (token["verse_text"] or "[verse text not available]").strip()
    dep_rel      = token["dep_relation"] or "unknown"
    senses       = token["senses"]

    # Morphology description
    morph_parts = []
    if token["pos_code"] == "V":
        for field in ["tense", "voice", "mood"]:
            if token.get(field):
                morph_parts.append(token[field])
    elif token["pos_code"] == "N":
        for field in ["grammatical_case", "mood"]:
            if token.get(field):
                morph_parts.append(token[field])
    morph_str = ", ".join(morph_parts) if morph_parts else "undetermined"

    sense_list = "\n".join(
        f"  {s['sense_index']}: {s['gloss']}" for s in senses
    )

    user_content = f"""Greek word:    {surface} ({lemma})
Reference:     {ref}
Morphology:    {morph_str}
Syntax role:   {dep_rel}
Verse (BSB):   {verse_text}

Available senses (select one index):
{sense_list}

Which sense_index best fits this specific occurrence?"""

    return user_content


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_submit(args, client, conn):
    """Build prompts and submit to Claude Batch API."""
    tokens = get_polysemous_tokens(
        conn,
        strongs=args.strongs,
        limit=args.limit,
        reset=args.reset,
    )

    print(f"  {len(tokens)} tokens to classify")
    if not tokens:
        print("Nothing to submit — all polysemous tokens already classified.")
        print("Use --reset to re-classify.")
        return

    # Group by lemma for progress display
    from collections import Counter
    by_lemma = Counter(t["strongs_id"] for t in tokens)
    for sid, count in sorted(by_lemma.items(), key=lambda x: -x[1]):
        print(f"    {sid}: {count} tokens")
    print()

    print("Building prompts...")
    requests = []
    id_map = {}  # custom_id -> verse_word_id

    for token in tokens:
        if not token["senses"]:
            print(f"  WARNING: no senses for {token['strongs_id']} token {token['verse_word_id']} — skipping")
            continue

        custom_id = str(token["verse_word_id"])
        user_content = build_prompt(token)

        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": MODEL,
                "max_tokens": 60,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}]
            }
        })
        id_map[custom_id] = token["verse_word_id"]

    print(f"  {len(requests)} prompts ready")

    if args.dry_run:
        print("\n[DRY RUN] Sample prompt (first token):\n")
        print("SYSTEM:", SYSTEM_PROMPT[:200], "...")
        print()
        print("USER:", requests[0]["params"]["messages"][0]["content"])
        print(f"\n[DRY RUN] Would submit {len(requests)} requests to {MODEL}. No API call made.")
        return

    print(f"\nSubmitting batch ({len(requests)} requests) to Anthropic...")
    batch = client.beta.messages.batches.create(requests=requests)

    state = {
        "batch_id":     batch.id,
        "submitted_at": datetime.utcnow().isoformat(),
        "count":        len(requests),
        "model":        MODEL,
        "id_map":       id_map,
    }
    save_batch_state(state)

    print(f"\n  Batch ID:  {batch.id}")
    print(f"  Tokens:    {len(requests)}")
    print(f"  Status:    {batch.processing_status}")
    print(f"\nBatch submitted. Typically completes in 1–4 hours.")
    print(f"Check progress: python scripts/run_handler_c.py --status")
    print(f"Collect results: python scripts/run_handler_c.py --collect")


def cmd_status(args, client):
    """Check batch status."""
    state = load_batch_state()
    if not state:
        print("No batch found. Run --submit first.")
        return

    batch = client.beta.messages.batches.retrieve(state["batch_id"])
    counts = batch.request_counts

    print(f"Batch ID:    {state['batch_id']}")
    print(f"Submitted:   {state.get('submitted_at', 'unknown')}")
    print(f"Model:       {state.get('model', MODEL)}")
    print(f"Tokens:      {state['count']}")
    print(f"Status:      {batch.processing_status}")
    print(f"  Succeeded: {counts.succeeded}")
    print(f"  Processing:{counts.processing}")
    print(f"  Errored:   {counts.errored}")

    if batch.processing_status == "ended":
        print(f"\nDone. Run: python scripts/run_handler_c.py --collect")
    else:
        total = counts.processing + counts.succeeded + counts.errored
        pct = (counts.succeeded + counts.errored) / total * 100 if total else 0
        print(f"\nProgress: {pct:.0f}%")


def cmd_collect(args, client, conn):
    """Stream batch results into token_sense_override."""
    state = load_batch_state()
    if not state:
        print("No batch found. Run --submit first.")
        return

    batch = client.beta.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        counts = batch.request_counts
        print(f"Batch not finished. Status: {batch.processing_status} "
              f"({counts.succeeded} done, {counts.processing} processing)")
        return

    print(f"Collecting results for batch {state['batch_id']}...")
    id_map = state.get("id_map", {})

    ok = skipped = errored = 0
    cur = conn.cursor()

    for result in client.beta.messages.batches.results(state["batch_id"]):
        custom_id    = result.custom_id
        verse_word_id = id_map.get(custom_id)

        if not verse_word_id:
            print(f"  WARNING: unknown custom_id {custom_id}")
            skipped += 1
            continue

        if result.result.type != "succeeded":
            print(f"  ERROR: token {verse_word_id} — {result.result.type}")
            errored += 1
            continue

        raw_text = result.result.message.content[0].text.strip()

        try:
            # Strip markdown code fences if present (model sometimes wraps in ```json...```)
            text = raw_text
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```\s*$', '', text.strip())
                text = text.strip()
            # Extract just the first JSON object — handles trailing explanation text
            match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if match:
                text = match.group()
            parsed = json.loads(text)
            sense_index = int(parsed["sense_index"])
            confidence  = parsed.get("confidence", "medium")
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  PARSE ERROR token {verse_word_id}: {e} — raw: {raw_text[:80]}")
            errored += 1
            continue

        # Look up the gloss for this sense_index
        cur.execute("""
            SELECT ls.gloss
            FROM lexeme_sense ls
            JOIN verse_word vw ON vw.lexeme_id = (
                SELECT lexeme_id FROM verse_word WHERE id = %s
            )
            WHERE ls.lexeme_id = (SELECT lexeme_id FROM verse_word WHERE id = %s)
              AND ls.sense_index = %s
            LIMIT 1
        """, (verse_word_id, verse_word_id, sense_index))
        row = cur.fetchone()
        selected_gloss = row[0] if row else f"sense_{sense_index}"

        cur.execute("""
            INSERT INTO token_sense_override
                (verse_word_id, sense_index, selected_gloss, method, confidence)
            VALUES (%s, %s, %s, 'ai_classification', %s)
            ON CONFLICT (verse_word_id) DO UPDATE
                SET sense_index    = EXCLUDED.sense_index,
                    selected_gloss = EXCLUDED.selected_gloss,
                    confidence     = EXCLUDED.confidence,
                    updated_at     = NOW()
        """, (verse_word_id, sense_index, selected_gloss, confidence))

        ok += 1
        if ok % 200 == 0:
            conn.commit()
            print(f"  Committed {ok} so far...")

    conn.commit()
    cur.close()

    print(f"\nCollection complete:")
    print(f"  Stored:  {ok}")
    print(f"  Errored: {errored}")
    print(f"  Skipped: {skipped}")
    print(f"\nRun generate_lite_glosses.py --reset to regenerate glosses with AI sense selections.")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Handler C — AI sense classification batch")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--submit",   action="store_true", help="Submit batch to Claude API")
    group.add_argument("--status",   action="store_true", help="Check batch progress")
    group.add_argument("--collect",  action="store_true", help="Write results to token_sense_override")

    parser.add_argument("--dry-run", action="store_true", help="Preview prompt, no API call")
    parser.add_argument("--reset",   action="store_true", help="Re-classify already-done tokens")
    parser.add_argument("--limit",   type=int, default=0, help="Limit token count (for testing)")
    parser.add_argument("--strongs", type=str, default="",  help="Classify one lemma only")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in environment or .env file")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    if args.status:
        cmd_status(args, client)
        return

    conn = get_conn()
    try:
        if args.submit:
            print(f"Handler C — Sense Classification Batch")
            print(f"Model: {MODEL}\n")
            cmd_submit(args, client, conn)
        elif args.collect:
            cmd_collect(args, client, conn)
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
