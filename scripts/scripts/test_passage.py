#!/usr/bin/env python3
"""
Test sense disambiguation on a specific passage.
Usage: python scripts/test_passage.py --book 46 --chapter 1 --verses 1-5
"""
import os, sys, json, re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(Path(__file__).parent.parent)

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except ImportError:
    pass

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary"); sys.exit(1)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

STAGING_DIR = Path.cwd() / "ai_staging"
OUT_PATH = STAGING_DIR / "sense_selection_test.jsonl"

PROVIDERS = [
    {"name": "groq", "base_url": "https://api.groq.com/openai/v1",
     "api_key_env": "GROQ_API_KEY", "model": "llama-3.3-70b-versatile", "rpm": 30},
]

gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
if gh_token:
    PROVIDERS.append({
        "name": "github_models", "base_url": "https://models.inference.ai.azure.com",
        "api_key_env": None, "api_key": gh_token, "model": "gpt-4o-mini", "rpm": 15,
    })

BOOK_NAMES = {
    40: "Matthew", 41: "Mark", 42: "Luke", 43: "John", 44: "Acts",
    45: "Romans", 46: "1 Corinthians", 47: "2 Corinthians",
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

# ── DB ──

def get_passage_tokens(conn, book_id, chapter, verse_start, verse_end):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT vw.id, vw.surface_form, vw.lemma, vw.pos_code,
                   vw.tense, vw.voice, vw.mood, vw.person, vw.number,
                   vw.grammatical_case, vw.dep_relation,
                   vw.verse_id, v.book_id, v.chapter, v.verse_num,
                   l.id AS lexeme_id, l.strongs_id, l.lemma AS lexeme_lemma,
                   btv.verse_text,
                   (SELECT COUNT(*) FROM lexeme_sense ls WHERE ls.lexeme_id = l.id) AS sense_count
            FROM verse_word vw
            JOIN lexeme l ON vw.lexeme_id = l.id
            JOIN verse v ON vw.verse_id = v.id
            LEFT JOIN bible_translation_verse btv
                ON btv.book_id = v.book_id AND btv.chapter = v.chapter
                AND btv.verse_num = v.verse_num AND btv.translation_code = 'BSB'
            WHERE v.book_id = %s AND v.chapter = %s
              AND v.verse_num BETWEEN %s AND %s
            ORDER BY v.verse_num, vw.position
        """, (book_id, chapter, verse_start, verse_end))
        return [dict(r) for r in cur.fetchall()]

def get_sense_options(conn, lexeme_id):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT sense_index, gloss, sense_type FROM lexeme_sense WHERE lexeme_id = %s ORDER BY sense_index", (lexeme_id,))
        return [dict(r) for r in cur.fetchall()]

def get_lexicon_definitions(conn, lexeme_id):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT source, short_gloss FROM lexeme_meaning
            WHERE lexeme_id = %s AND source IN ('ugl','lsj','thayer','abbottsmith','strongs')
              AND short_gloss IS NOT NULL AND short_gloss != ''
            ORDER BY CASE source WHEN 'ugl' THEN 1 WHEN 'lsj' THEN 2 WHEN 'thayer' THEN 3 WHEN 'abbottsmith' THEN 4 ELSE 5 END
        """, (lexeme_id,))
        return [dict(r) for r in cur.fetchall()]

_interlinear_cache = {}

def get_verse_interlinear(conn, verse_id):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT vw.id, vw.surface_form, vw.position,
                   COALESCE(ls.gloss, '?') AS corpus_gloss
            FROM verse_word vw
            LEFT JOIN lexeme l ON vw.lexeme_id = l.id
            LEFT JOIN lexeme_sense ls ON l.id = ls.lexeme_id AND ls.sense_index = 0
            WHERE vw.verse_id = %s
            ORDER BY vw.position
        """, (verse_id,))
        return [dict(r) for r in cur.fetchall()]

# ── Prompt ──

def build_prompt(token, sense_options, lex_defs, db_conn=None):
    surface = token["surface_form"] or ""
    lemma = token.get("lexeme_lemma") or token.get("lemma") or token.get("strongs_id", "")
    sid = token.get("strongs_id", "")
    ref = f"{BOOK_NAMES.get(token['book_id'], f'Book {token['book_id']}')} {token['chapter']}:{token['verse_num']}"
    verse_id = token.get("verse_id")
    dep_rel = token.get("dep_relation") or "unknown"
    morph_parts = [str(token[f]) for f in ["tense","voice","mood","person","number","grammatical_case"] if token.get(f)]
    morph_str = ", ".join(morph_parts) if morph_parts else "undetermined"

    lines = [f"=== {surface} ({sid} — {lemma}) ===",
             f"Reference: {ref}",
             f"Morphology: {morph_str}",
             f"Syntax role: {dep_rel}",
             ""]

    # Greek interlinear context
    words = None
    if db_conn and verse_id and verse_id in _interlinear_cache:
        words = _interlinear_cache[verse_id]
    elif db_conn and verse_id:
        words = get_verse_interlinear(db_conn, verse_id)
        _interlinear_cache[verse_id] = words
    if words:
        greek_parts = [(f"[{w['surface_form']}]" if w["id"] == token.get("id") or w["id"] == token.get("verse_word_id") else w["surface_form"] or "?") for w in words]
        lines.append("Context:")
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
    lines.append('Examples: {"sense_index": 1}  or  {"sense_index": null, "selected_gloss": "my gloss"}')
    return "\n".join(lines)

# ── AI provider ──

class ProviderChain:
    def __init__(self):
        self.providers = []
        for p in PROVIDERS:
            key = p.get("api_key") or os.environ.get(p["api_key_env"]) if p.get("api_key_env") else None
            if key:
                self.providers.append({**p, "api_key": key, "last_call": 0, "min_interval": 60.0 / p["rpm"]})
        if not self.providers:
            print("ERROR: No AI providers configured"); sys.exit(1)
        print(f"  Providers: {', '.join(p['name'] for p in self.providers)}")

    def call(self, prompt):
        import time, requests
        MAX_RETRY_WAIT = 120
        for p in self.providers:
            for attempt in range(5):
                elapsed = time.time() - p["last_call"]
                if elapsed < p["min_interval"]:
                    time.sleep(p["min_interval"] - elapsed)
                try:
                    resp = requests.post(f"{p['base_url'].rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {p['api_key']}", "Content-Type": "application/json"},
                        json={"model": p["model"], "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}
                        ], "max_tokens": 150, "temperature": 0}, timeout=30)
                    p["last_call"] = time.time()
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"].strip()
                        if content.startswith("```"):
                            content = re.sub(r'```(?:json)?\s*', '', content).strip()
                        return json.loads(content), p["name"]
                    elif resp.status_code == 429:
                        retry = int(resp.headers.get("Retry-After", 60))
                        wait = min(retry, MAX_RETRY_WAIT)
                        print(f"    ⏳ {p['name']} 429 — waiting {wait}s (attempt {attempt+1}/5)")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"    ⚠ {p['name']} {resp.status_code}")
                        break
                except Exception as e:
                    print(f"    ⚠ {p['name']} error: {e}")
                    time.sleep(5)
                    continue
        return None, None

# ── Main ──

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", type=int, required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--verses", default="1-999")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    vs = args.verses.split("-")
    v_start, v_end = int(vs[0]), int(vs[1]) if len(vs) > 1 else int(vs[0])

    conn = psycopg2.connect(**DB_CONFIG)
    tokens = get_passage_tokens(conn, args.book, args.chapter, v_start, v_end)
    multi_tokens = [t for t in tokens if t["sense_count"] > 1]
    book_name = BOOK_NAMES.get(args.book, f"Book {args.book}")

    print(f"  {book_name} {args.chapter}:{args.verses}")
    print(f"  Total tokens: {len(tokens)}")
    print(f"  Multi-sense tokens: {len(multi_tokens)}")

    if args.dry_run:
        lex_cache = {}; sense_cache = {}
        for t in multi_tokens:
            lid = t["lexeme_id"]
            if lid not in lex_cache:
                lex_cache[lid] = get_lexicon_definitions(conn, lid)
                sense_cache[lid] = get_sense_options(conn, lid)
            prompt = build_prompt(t, sense_cache[lid], lex_cache[lid], conn)
            ref = f"{book_name} {t['chapter']}:{t['verse_num']}"
            print(f"\n{'='*60}")
            print(f"  {t['surface_form']} ({t['strongs_id']}) — {ref}")
            print(f"{'='*60}")
            print(prompt)
        conn.close()
        return

    chain = ProviderChain()
    lex_cache = {}; sense_cache = {}
    results = []

    for i, t in enumerate(multi_tokens, 1):
        lid = t["lexeme_id"]
        if lid not in lex_cache:
            lex_cache[lid] = get_lexicon_definitions(conn, lid)
            sense_cache[lid] = get_sense_options(conn, lid)

        prompt = build_prompt(t, sense_cache[lid], lex_cache[lid], conn)
        result, provider = chain.call(prompt)

        ref = f"{book_name} {t['chapter']}:{t['verse_num']}"
        if result:
            si = result.get("sense_index")
            senses = sense_cache[lid]
            valid_senses = [s["sense_index"] for s in senses]
            hallucination = si is not None and si not in valid_senses

            if si is not None and si in valid_senses:
                selected = next(s["gloss"] for s in senses if s["sense_index"] == si)
                sel_type = "existing"
            elif si is not None and si not in valid_senses:
                selected = f"sense_{si}"
                sel_type = "hallucination"
            elif result.get("selected_gloss"):
                si = None
                selected = result["selected_gloss"].strip()
                sel_type = "suggested"
            else:
                print(f"  [{i}/{len(multi_tokens)}] {t['surface_form']} ({t['strongs_id']}) — {ref}")
                print(f"    INVALID RESPONSE")
                continue

            tag = " [HALLUCINATION]" if hallucination else ""
            print(f"  [{i}/{len(multi_tokens)}] {t['surface_form']} ({t['strongs_id']}) — {ref}")
            print(f"    sense {si}: '{selected}' ({result.get('confidence','?')}) via {provider}{tag}")
            results.append({"verse_word_id": t.get("verse_word_id") or t["id"], "strongs_id": t["strongs_id"],
                "surface_form": t["surface_form"], "sense_index": si,
                "selected_gloss": selected, "selection_type": sel_type,
                "hallucination": hallucination,
                "confidence": result.get("confidence","medium"),
                "provider": provider, "ref": ref})
        else:
            print(f"  [{i}/{len(multi_tokens)}] {t['surface_form']} ({t['strongs_id']}) — {ref}")
            print(f"    → FAILED")

    if results:
        STAGING_DIR.mkdir(exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n  Results: {OUT_PATH}")
        print(f"  Import: curl -X POST 'http://localhost:8081/api/admin/import-sense-selections'")

    conn.close()

if __name__ == "__main__":
    main()
