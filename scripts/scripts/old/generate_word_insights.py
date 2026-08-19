#!/usr/bin/env python3
"""
generate_word_insights.py — Pre-generate Word Insight commentary for NT lexemes.

Uses Anthropic Batch API (Haiku 4.5) to generate ~200-word commentary per lemma.
Results are written to data/word-insights-export.json and can be bulk-loaded
into the lexeme_insight table via the --import flag.

Usage:
  python scripts/generate_word_insights.py --submit          # submit batch
  python scripts/generate_word_insights.py --status          # check progress
  python scripts/generate_word_insights.py --collect         # save results to JSON
  python scripts/generate_word_insights.py --import-db       # load JSON → lexeme_insight table
  python scripts/generate_word_insights.py --dry-run --limit 3   # preview prompts
  python scripts/generate_word_insights.py --reset-batch     # clear batch state (start over)

Requirements:
  pip install anthropic python-dotenv psycopg2-binary
"""

import os, sys, json, argparse, time
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
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic"); sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary"); sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR         = Path(__file__).parent.parent / "data"
EXPORT_FILE      = DATA_DIR / "word-insights-export.json"
BATCH_STATE_FILE = DATA_DIR / "word-insights-batch.json"

MODEL = "claude-haiku-4-5-20251001"

# ── DB connection ──────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "interlinear_bible"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", os.getenv("DB_PASSWORD", "postgres")),
    )


def fetch_lexemes(conn, limit=None, strongs_ids=None, min_frequency=None):
    """Fetch lexeme data with corpus gloss for prompt context."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    conditions = []
    params: list = []

    if strongs_ids:
        conditions.append("l.strongs_id = ANY(%s)")
        params.append(strongs_ids)

    if min_frequency is not None:
        conditions.append(f"l.frequency_nt >= %s")
        params.append(min_frequency)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    lim = f"LIMIT {int(limit)}" if limit else ""

    cur.execute(f"""
        SELECT
            l.strongs_id,
            l.lemma,
            l.transliteration,
            l.part_of_speech,
            l.frequency_nt,
            l.etymology,
            -- corpus gloss (highest priority)
            (SELECT lm.short_gloss
             FROM lexeme_meaning lm
             WHERE lm.lexeme_id = l.id AND lm.source = 'corpus'
             ORDER BY lm.display_order LIMIT 1) AS corpus_gloss,
            -- mounce as fallback
            (SELECT lm.short_gloss
             FROM lexeme_meaning lm
             WHERE lm.lexeme_id = l.id AND lm.source = 'mounce'
             ORDER BY lm.display_order LIMIT 1) AS mounce_gloss,
            -- full lsj definition for context
            (SELECT lm.full_definition
             FROM lexeme_meaning lm
             WHERE lm.lexeme_id = l.id AND lm.source = 'lsj'
             ORDER BY lm.display_order LIMIT 1) AS lsj_def,
            -- thayer definition
            (SELECT lm.full_definition
             FROM lexeme_meaning lm
             WHERE lm.lexeme_id = l.id AND lm.source = 'thayer'
             ORDER BY lm.display_order LIMIT 1) AS thayer_def
        FROM lexeme l
        {where}
        ORDER BY l.frequency_nt DESC NULLS LAST
        {lim}
    """, params if params else None)

    return cur.fetchall()


def already_generated(conn):
    """Return set of strongs_ids already in lexeme_insight."""
    cur = conn.cursor()
    cur.execute("SELECT strongs_id FROM lexeme_insight")
    return {r[0] for r in cur.fetchall()}


# ── Prompt builder ─────────────────────────────────────────────────────────────
def build_prompt(row) -> str:
    sid    = row["strongs_id"]
    lemma  = row["lemma"] or ""
    translit = row["transliteration"] or ""
    pos    = row["part_of_speech"] or ""
    freq   = row["frequency_nt"] or ""
    etym   = (row["etymology"] or "")[:300]
    gloss  = row["corpus_gloss"] or row["mounce_gloss"] or ""
    lsj    = (row["lsj_def"] or "")[:500]
    thayer = (row["thayer_def"] or "")[:500]

    lines = [
        "You are a New Testament Greek scholar writing for a serious Bible student (not a scholar).",
        "Write a concise Word Insight for the Greek word below. Cover:",
        "1. The core meaning and its range (what it covers, what it doesn't)",
        "2. The most theologically significant NT uses (cite 2–3 key verses by reference)",
        "3. Any important Hebrew background or LXX connection",
        "4. One practical takeaway for reading the NT",
        "",
        "Format: 3–5 short paragraphs. No bullet points. No headers. Plain prose. ~200–250 words.",
        "",
        f"Word: {lemma} ({translit}) [{sid}]",
    ]
    if pos:    lines.append(f"Part of speech: {pos}")
    if freq:   lines.append(f"NT frequency: {freq} occurrences")
    if gloss:  lines.append(f"Gloss: {gloss}")
    if etym:   lines.append(f"Etymology: {etym}")
    if lsj:    lines.append(f"LSJ definition: {lsj}")
    if thayer: lines.append(f"Thayer definition: {thayer}")

    return "\n".join(lines)


# ── Batch submit ───────────────────────────────────────────────────────────────
def submit(conn, dry_run=False, limit=None, strongs_ids=None, min_frequency=None):
    done = already_generated(conn)
    rows = fetch_lexemes(conn, limit=limit, strongs_ids=strongs_ids, min_frequency=min_frequency)
    rows = [r for r in rows if r["strongs_id"] not in done]

    print(f"Lexemes to process: {len(rows)}  (already done: {len(done)})")
    if not rows:
        print("Nothing to do."); return

    requests = [
        {
            "custom_id": row["strongs_id"],
            "params": {
                "model": MODEL,
                "max_tokens": 400,
                "messages": [{"role": "user", "content": build_prompt(row)}],
            }
        }
        for row in rows
    ]

    if dry_run:
        print(f"\nSample prompts (first {min(3, len(requests))}):\n")
        for req in requests[:3]:
            sid = req["custom_id"]
            print(f"=== {sid} ===")
            print(req["params"]["messages"][0]["content"])
            print()
        return

    client = anthropic.Anthropic()
    batch  = client.messages.batches.create(requests=requests)

    state = {
        "batch_id":  batch.id,
        "submitted": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count":     len(requests),
        "status":    batch.processing_status,
    }
    BATCH_STATE_FILE.write_text(json.dumps(state, indent=2))

    print(f"Submitted batch: {batch.id}")
    print(f"  {len(requests)} requests | status: {batch.processing_status}")
    print(f"  State: {BATCH_STATE_FILE}")
    print(f"\nCheck: python scripts/generate_word_insights.py --status")


# ── Status ─────────────────────────────────────────────────────────────────────
def status():
    if not BATCH_STATE_FILE.exists():
        print("No batch state. Run --submit first."); return
    state = json.loads(BATCH_STATE_FILE.read_text())
    client = anthropic.Anthropic()
    batch  = client.messages.batches.retrieve(state["batch_id"])
    print(f"Batch:  {batch.id}")
    print(f"Status: {batch.processing_status}")
    if hasattr(batch, "request_counts"):
        rc = batch.request_counts
        print(f"  processing={rc.processing}  succeeded={rc.succeeded}  errored={rc.errored}")
    if batch.processing_status == "ended":
        print("\nReady: python scripts/generate_word_insights.py --collect")


# ── Collect ────────────────────────────────────────────────────────────────────
def collect():
    if not BATCH_STATE_FILE.exists():
        print("No batch state."); return
    state  = json.loads(BATCH_STATE_FILE.read_text())
    client = anthropic.Anthropic()
    batch  = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        print(f"Not complete yet: {batch.processing_status}"); return

    results = {}
    errors  = 0
    for result in client.messages.batches.results(state["batch_id"]):
        sid = result.custom_id
        if result.result.type != "succeeded":
            errors += 1; continue
        text = result.result.message.content[0].text.strip()
        if text:
            results[sid] = {"strongs_id": sid, "insight_text": text, "model": MODEL}

    rows = sorted(results.values(), key=lambda r: r["strongs_id"])
    EXPORT_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Collected: {len(results)} insights  |  {errors} errors")
    print(f"Saved to {EXPORT_FILE}")
    print(f"\nLoad into DB: python scripts/generate_word_insights.py --import-db")


# ── Import to DB ───────────────────────────────────────────────────────────────
def import_db(conn):
    if not EXPORT_FILE.exists():
        print(f"Export file not found: {EXPORT_FILE}"); return

    rows = json.loads(EXPORT_FILE.read_text())
    cur  = conn.cursor()
    inserted = updated = 0

    for row in rows:
        sid  = row["strongs_id"]
        text = row["insight_text"]
        model = row.get("model", MODEL)
        cur.execute("""
            INSERT INTO lexeme_insight (strongs_id, insight_text, model_used, generated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (strongs_id) DO UPDATE
              SET insight_text = EXCLUDED.insight_text,
                  model_used   = EXCLUDED.model_used,
                  generated_at = now()
        """, (sid, text, model))
        if cur.rowcount == 1:
            inserted += 1
        else:
            updated += 1

    conn.commit()
    print(f"Loaded: {inserted} inserted  |  {updated} updated  (total {len(rows)})")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pre-generate Word Insight commentary via AI batch")
    parser.add_argument("--submit",      action="store_true", help="Submit batch to Claude API")
    parser.add_argument("--status",      action="store_true", help="Check batch status")
    parser.add_argument("--collect",     action="store_true", help="Collect results → export JSON")
    parser.add_argument("--import-db",   action="store_true", help="Load export JSON → lexeme_insight table")
    parser.add_argument("--reset-batch", action="store_true", help="Delete batch state file")
    parser.add_argument("--dry-run",     action="store_true", help="Preview prompts, no API calls")
    parser.add_argument("--limit",         type=int,  help="Limit number of lemmas to submit")
    parser.add_argument("--min-frequency", type=int,  help="Only include lemmas with NT frequency >= N (e.g. 10)")
    parser.add_argument("--strongs",       nargs="+", help="Submit specific Strong's IDs only")
    args = parser.parse_args()

    if args.reset_batch:
        BATCH_STATE_FILE.unlink(missing_ok=True)
        print("Batch state cleared."); return

    if args.status:
        status(); return

    if args.collect:
        collect(); return

    # Commands that need DB
    conn = get_db()
    try:
        if args.import_db:
            import_db(conn)
        elif args.submit or args.dry_run:
            strongs = [s.upper() if s.upper().startswith("G") else "G" + s.upper()
                       for s in (args.strongs or [])]
            submit(conn, dry_run=args.dry_run, limit=args.limit,
                   strongs_ids=strongs or None,
                   min_frequency=args.min_frequency)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
