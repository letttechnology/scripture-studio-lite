#!/usr/bin/env python3
"""
sense_disambiguate.py — Per-token sense disambiguation for all multi-sense lexemes.

For each token whose lexeme has 2+ senses (corpus sense index 0, 1, 2...),
builds a prompt with verse context + all lexicon definitions (LSJ, Thayer, UGL)
and asks the AI to select the correct sense_index.

Output: ai_staging/sense_selection_{timestamp}.jsonl (staging file for review)
After review: POST /admin/import-sense-selections → token_sense_override → regenerate

Usage:
  python scripts/sense_disambiguate.py --dry-run --limit 5     # preview prompts
  python scripts/sense_disambiguate.py --dry-run --strongs G2087  # one lexeme
  python scripts/sense_disambiguate.py --submit                 # run full batch
  python scripts/sense_disambiguate.py --resume                 # resume interrupted run
  python scripts/sense_disambiguate.py --strongs G2087 --submit  # one lexeme only

Providers (round-robin on 429):
  - Groq (llama-3.3-70b)        → GROQ_API_KEY
  - Gemini (gemini-2.0-flash)  → GEMINI_API_KEY
  - GitHub Models (gpt-4o-mini) → GITHUB_TOKEN
"""

import os, sys, json, time, argparse, re
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: pip install requests"); sys.exit(1)

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary"); sys.exit(1)

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Config ────────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

STAGING_DIR = Path(__file__).parent.parent / "ai_staging"

PROVIDERS = [
    {
        "name":     "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model":    "llama-3.3-70b-versatile",
        "rpm":      30,
    },
    {
        "name":     "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model":    "gemini-2.0-flash",
        "rpm":      30,
    },
]

if os.environ.get("GITHUB_TOKEN"):
    PROVIDERS.append({
        "name":     "github_models",
        "base_url": "https://models.inference.ai.azure.com",
        "api_key_env": "GITHUB_TOKEN",
        "model":    "gpt-4o-mini",
        "rpm":      15,
    })

BOOK_NAMES = {
    40: "Matthew", 41: "Mark", 42: "Luke", 43: "John",
    44: "Acts", 45: "Romans", 46: "1 Corinthians", 47: "2 Corinthians",
    48: "Galatians", 49: "Ephesians", 50: "Philippians", 51: "Colossians",
    52: "1 Thessalonians", 53: "2 Thessalonians", 54: "1 Timothy", 55: "2 Timothy",
    56: "Titus", 57: "Philemon", 58: "Hebrews", 59: "James",
    60: "1 Peter", 61: "2 Peter", 62: "1 John", 63: "2 John", 64: "3 John",
    65: "Jude", 66: "Revelation",
}

SYSTEM_PROMPT = """You are a Greek New Testament lexical classifier.

Given a Greek word in its verse context, select the most appropriate sense from
the numbered list OR suggest a better gloss if none of the existing senses fit.

You may respond in two modes:
1. EXISTING SENSE — pick an index from the provided list:
   {"sense_index": <int>, "confidence": "high"|"medium"|"low"}
2. NEW SUGGESTION — if none of the existing senses are correct:
   {"sense_index": null, "selected_gloss": "<your gloss>", "confidence": "high"|"medium"|"low"}

Only suggest a new gloss when the existing senses are genuinely wrong for this
context. Prefer selecting from the existing senses.

Keep suggested glosses concise (1-6 words). No explanation. JSON only.

confidence guide:
  high   — the context makes the meaning clear beyond reasonable doubt
  medium — the sense is likely but another sense is plausible
  low    — the context is ambiguous; you are making a best guess"""

# ── Cache helpers ─────────────────────────────────────────────────────────────

def load_staging_file():
    files = sorted(STAGING_DIR.glob("sense_selection_*.jsonl"))
    return files[-1] if files else None

def load_existing_results():
    results = {}
    f = load_staging_file()
    if f:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    results[r["verse_word_id"]] = r
    return results

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_multi_sense_tokens(conn, strongs=None, limit=0):
    """Fetch tokens whose lexeme has 2+ corpus senses, with verse context."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        params = []
        where = ""

        if strongs:
            where = "AND l.strongs_id = %s"
            params.append(strongs.upper())

        q = f"""
            SELECT
                vw.id              AS verse_word_id,
                vw.surface_form,
                vw.lemma,
                vw.pos_code,
                vw.tense, vw.voice, vw.mood,
                vw.person, vw.number,
                vw.grammatical_case,
                vw.dep_relation,
                vw.verse_id,
                v.book_id, v.chapter, v.verse_num,
                l.id               AS lexeme_id,
                l.strongs_id,
                l.lemma            AS lexeme_lemma,
                btv.verse_text,
                (
                    SELECT COUNT(*) FROM lexeme_sense ls
                    WHERE ls.lexeme_id = l.id
                ) AS sense_count
            FROM verse_word vw
            JOIN lexeme l ON vw.lexeme_id = l.id
            JOIN verse v ON vw.verse_id = v.id
            LEFT JOIN bible_translation_verse btv
                ON btv.book_id = v.book_id
                AND btv.chapter = v.chapter
                AND btv.verse_num = v.verse_num
                AND btv.translation_code = 'BSB'
            WHERE (
                SELECT COUNT(*) FROM lexeme_sense ls
                WHERE ls.lexeme_id = l.id
            ) > 1
            {where}
            ORDER BY l.strongs_id, v.id, vw.position
        """

        cur.execute(q, params)
        tokens = [dict(r) for r in cur.fetchall()]

        if limit:
            tokens = tokens[:limit]

        return tokens

def get_sense_options(conn, lexeme_id):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT sense_index, gloss, sense_type
            FROM lexeme_sense
            WHERE lexeme_id = %s
            ORDER BY sense_index
        """, (lexeme_id,))
        return [dict(r) for r in cur.fetchall()]

# Store the interlinear cache so we don't re-query every time
_interlinear_cache = {}

def build_prompt(token, sense_options, lex_defs, db_conn=None):
    surface   = token["surface_form"] or ""
    lemma     = token.get("lexeme_lemma") or token.get("lemma") or token.get("strongs_id", "")
    sid       = token.get("strongs_id", "")
    ref       = f"{BOOK_NAMES.get(token['book_id'], f'Book {token['book_id']}')} {token['chapter']}:{token['verse_num']}"
    verse_id  = token["verse_id"]
    dep_rel   = token.get("dep_relation") or "unknown"

    morph_parts = []
    for f in ["tense", "voice", "mood", "person", "number", "grammatical_case"]:
        if token.get(f):
            morph_parts.append(str(token[f]))
    morph_str = ", ".join(morph_parts) if morph_parts else "undetermined"

    lines = []
    lines.append(f"=== {surface} ({sid} — {lemma}) ===")
    lines.append(f"Reference: {ref}")
    lines.append(f"Morphology: {morph_str}")
    lines.append(f"Syntax role: {dep_rel}")
    lines.append("")

    # Show Greek interlinear context
    lines.append("Context:")
    words = None
    if db_conn and verse_id in _interlinear_cache:
        words = _interlinear_cache[verse_id]
    elif db_conn:
        words = get_verse_interlinear(db_conn, verse_id)
        _interlinear_cache[verse_id] = words
    if words:
        greek_parts = []
        for w in words:
            if w["id"] == token["verse_word_id"]:
                greek_parts.append(f"[{w['surface_form']}]")
            else:
                greek_parts.append(w["surface_form"] or "?")
        lines.append("  Greek: " + " ".join(greek_parts))
    lines.append("")

    # Short lexicon glosses
    if lex_defs:
        lines.append("Lexicon:")
        for ld in lex_defs:
            g = (ld.get("short_gloss") or "").strip()
            if g and len(g) > 3:
                lines.append(f"  {ld['source'].upper()}: {g}")
        lines.append("")

    # Existing corpus senses
    lines.append("Existing corpus senses:")
    for s in sense_options:
        lines.append(f"  [{s['sense_index']}] {s['gloss']}")
    lines.append("  [OTHER] Suggest a different gloss (only if existing senses are wrong)")
    lines.append("")

    lines.append("Respond with JSON only. Pick an existing sense_index or use null + selected_gloss.")
    lines.append("Examples: {\"sense_index\": 1}  or  {\"sense_index\": null, \"selected_gloss\": \"my gloss\"}")

    return "\n".join(lines)

# ── Provider chain ───────────────────────────────────────────────────────────

class ProviderChain:
    def __init__(self):
        self.providers = []
        for p in PROVIDERS:
            key = os.environ.get(p["api_key_env"])
            if key:
                self.providers.append({
                    **p,
                    "api_key": key,
                    "last_call": 0,
                    "call_count": 0,
                    "min_interval": 60.0 / p["rpm"],
                })
        if not self.providers:
            print("ERROR: No AI providers configured. Set GROQ_API_KEY and/or GEMINI_API_KEY in .env")
            sys.exit(1)
        print(f"  Providers: {', '.join(p['name'] for p in self.providers)}")

    def call_with_fallback(self, prompt, max_retries=3):
        for p in self.providers:
            for attempt in range(max_retries):
                elapsed = time.time() - p["last_call"]
                if elapsed < p["min_interval"]:
                    time.sleep(p["min_interval"] - elapsed)

                try:
                    resp = requests.post(
                        f"{p['base_url'].rstrip('/')}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {p['api_key']}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": p["model"],
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": 150,
                            "temperature": 0,
                        },
                        timeout=30,
                    )
                    p["last_call"] = time.time()
                    p["call_count"] += 1

                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"].strip()
                        return self._parse_response(content), p["name"]
                    elif resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", 60))
                        print(f"  ⏳ {p['name']} 429 — retry in {retry_after}s")
                        time.sleep(min(retry_after, 60))
                        continue
                    else:
                        print(f"  ⚠ {p['name']} {resp.status_code}: {resp.text[:100]}")
                        break
                except Exception as e:
                    print(f"  ⚠ {p['name']} error: {e}")
                    time.sleep(2)
                    continue

        print(f"  ✗ All providers exhausted for this token")
        return None, None

    def _parse_response(self, text):
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        try:
            obj = json.loads(text) if text else None
            if not obj:
                return None
            si = obj.get("sense_index")
            if si is None and obj.get("selected_gloss"):
                return obj  # new gloss suggestion — passes through as-is
            if isinstance(si, int) and si >= 0:
                obj["sense_index"] = si
                return obj
            return None
        except (json.JSONDecodeError, ValueError):
            return None

# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_dry_run(args, conn):
    tokens = get_multi_sense_tokens(conn, strongs=args.strongs, limit=args.limit)
    print(f"  {len(tokens)} tokens found\n")

    lex_def_cache = {}
    sense_cache = {}

    for i, t in enumerate(tokens, 1):
        lid = t["lexeme_id"]
        if lid not in lex_def_cache:
            lex_def_cache[lid] = get_lexicon_definitions(conn, lid)
            sense_cache[lid] = get_sense_options(conn, lid)

        prompt = build_prompt(t, sense_cache[lid], lex_def_cache[lid], conn)
        ref = f"{BOOK_NAMES.get(t['book_id'], '?')} {t['chapter']}:{t['verse_num']}"
        sid = t["strongs_id"]
        surface = t["surface_form"]
        print(f"\n{'='*70}")
        print(f"  [{i}/{len(tokens)}] {surface} ({sid}) — {ref}")
        print(f"{'='*70}")
        print(prompt)
        print()

def cmd_submit(args, conn):
    tokens = get_multi_sense_tokens(conn, strongs=args.strongs, limit=args.limit)
    print(f"  {len(tokens)} multi-sense tokens found")

    existing = load_existing_results()
    if existing and not args.strongs:
        tokens_before = len(tokens)
        tokens = [t for t in tokens if t["verse_word_id"] not in existing]
        print(f"  {len(existing)} already in staging — {len(tokens)} remaining (of {tokens_before})")
    elif existing and args.strongs:
        tokens = [t for t in tokens if t["verse_word_id"] not in existing]
        print(f"  {len(existing)} already done — {len(tokens)} remaining for {args.strongs}")

    if not tokens:
        print("  Nothing to do.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_path = STAGING_DIR / f"sense_selection_{ts}.jsonl"

    chain = ProviderChain()
    lex_def_cache = {}
    sense_cache = {}
    ok = 0; fail = 0; skip = 0
    start = time.time()

    print(f"\n  Output: {staging_path}")
    print(f"  Starting...\n")

    with open(staging_path, "a", encoding="utf-8") as out:
        i = 0
        while i < len(tokens):
            t = tokens[i]
            lid = t["lexeme_id"]

            if lid not in lex_def_cache:
                lex_def_cache[lid] = get_lexicon_definitions(conn, lid)
                sense_cache[lid] = get_sense_options(conn, lid)

            senses = sense_cache[lid]
            if len(senses) <= 1:
                skip += 1
                i += 1
                continue

            prompt = build_prompt(t, senses, lex_def_cache[lid], conn)
            result, provider = chain.call_with_fallback(prompt)

            if not result:
                fail += 1
                line = json.dumps({
                    "verse_word_id": t["verse_word_id"],
                    "strongs_id": t["strongs_id"],
                    "error": "failed",
                    "timestamp": datetime.utcnow().isoformat(),
                }, ensure_ascii=False)
                out.write(line + "\n")
                out.flush()
            else:
                si = result.get("sense_index")
                if si is not None and any(s["sense_index"] == si for s in senses):
                    # Existing sense chosen
                    existing_sense = next(s for s in senses if s["sense_index"] == si)
                    selected_gloss = existing_sense["gloss"]
                    selection_type = "existing"
                elif result.get("selected_gloss"):
                    # New gloss suggested
                    si = None
                    selected_gloss = result["selected_gloss"].strip()
                    selection_type = "suggested"
                else:
                    fail += 1
                    line = json.dumps({
                        "verse_word_id": t["verse_word_id"],
                        "strongs_id": t["strongs_id"],
                        "error": "invalid_response",
                        "raw": str(result),
                        "timestamp": datetime.utcnow().isoformat(),
                    }, ensure_ascii=False)
                    out.write(line + "\n")
                    out.flush()
                    i += 1
                    continue

                ok += 1
                line = json.dumps({
                    "verse_word_id": t["verse_word_id"],
                    "strongs_id": t["strongs_id"],
                    "surface_form": t["surface_form"],
                    "lexeme_lemma": t.get("lexeme_lemma", ""),
                    "sense_index": si,
                    "selected_gloss": selected_gloss,
                    "selection_type": selection_type,
                    "confidence": result.get("confidence", "medium"),
                    "provider": provider,
                    "ref": f"{BOOK_NAMES.get(t['book_id'], '?')} {t['chapter']}:{t['verse_num']}",
                    "timestamp": datetime.utcnow().isoformat(),
                }, ensure_ascii=False)
                out.write(line + "\n")
                out.flush()

            elapsed = time.time() - start
            rate = ok / (elapsed / 60) if elapsed > 0 else 0
            eta = (len(tokens) - (i + 1)) / rate * 60 / 60 if rate > 0 else 0

            sys.stdout.write(f"\r  {ok} ok / {fail} fail / {skip} skip — {i+1}/{len(tokens)} — {rate:.0f} req/min — ETA: {eta:.1f}h")
            sys.stdout.flush()
            i += 1

    elapsed_h = (time.time() - start) / 3600
    print(f"\n\n  Done — {ok} ok, {fail} failed, {skip} skipped in {elapsed_h:.1f}h")
    print(f"  Results: {staging_path}")
    print(f"\n  To import after review:")
    print(f"    curl -X POST 'http://localhost:8081/api/admin/import-sense-selections'")
    print(f"  Then regenerate glosses:")
    print(f"    curl -X POST 'http://localhost:8081/api/admin/regenerate-lite-glosses'")

def cmd_resume(args, conn):
    f = load_staging_file()
    if not f:
        print("  No staging file found. Run --submit first.")
        return
    print(f"  Resuming from: {f}")
    cmd_submit(args, conn)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Per-token sense disambiguation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview prompts, no AI calls")
    mode.add_argument("--submit",  action="store_true", help="Run disambiguation batch")
    mode.add_argument("--resume",  action="store_true", help="Resume from existing staging file")

    parser.add_argument("--limit",   type=int, default=0,  help="Process at most N tokens")
    parser.add_argument("--strongs", type=str, default="",  help="Single Strong's ID only, e.g. G2087")
    args = parser.parse_args()

    if not (args.dry_run or args.submit or args.resume):
        parser.print_help()
        print("\nQuick start:")
        print("  python scripts/sense_disambiguate.py --dry-run --limit 5")
        print("  python scripts/sense_disambiguate.py --submit")
        print("  python scripts/sense_disambiguate.py --resume")
        sys.exit(0)

    print(f"Connecting to DB {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"ERROR: DB connection failed — {e}")
        sys.exit(1)

    try:
        if args.dry_run:
            cmd_dry_run(args, conn)
        elif args.submit:
            cmd_submit(args, conn)
        elif args.resume:
            cmd_resume(args, conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
