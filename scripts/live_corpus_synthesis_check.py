#!/usr/bin/env python3
"""
live_corpus_synthesis_check.py — prompt-regression guard for corpus synthesis (#190).

WHY THIS IS PYTHON AND NOT A JUNIT TEST

The issue asks for a JUnit `@Tag("live-ai")` test behind a `-Plive-ai` Maven profile, on the
"Studio synthesis path". There is no such path. Corpus synthesis has never been Java: the
prompt is built by `scripts/old/synthesize_corpus.py:build_prompt()` and submitted to the
Anthropic Batch API from there. Studio has no synthesis service, the AI service has no
synthesis endpoint, and `interlinear-bible-studio/docs/TECHNICAL_STUDIO.md` §6 records corpus
synthesis as a Path 1 step that was deliberately not ported.

A JUnit test would therefore have to reimplement the prompt in Java, and a guard against
prompt regression that watches a *copy* of the prompt guards nothing. So this imports the real
`build_prompt` and sends the real assembled prompt. Everything else the issue asks for holds:
opt-in, key-gated, free provider, assertions on structure and quality rather than exact text.

USAGE

    python scripts/live_corpus_synthesis_check.py                 # G3056 (logos)
    python scripts/live_corpus_synthesis_check.py --strongs G266   # hamartia
    python scripts/live_corpus_synthesis_check.py --dry-run       # print the prompt, no call
    python scripts/live_corpus_synthesis_check.py --show-response

Exit codes:  0 pass or skipped   1 a check failed   2 could not run

Skipped, not failed, when the provider key is absent — a machine with no key must not turn red.

PROVIDER

Groq by default, via its OpenAI-compatible endpoint. Never Anthropic: this is the fast feedback
loop, and the production path is a batch submission that takes hours. Override with
LIVE_AI_BASE_URL / LIVE_AI_MODEL / LIVE_AI_KEY_ENV for any other OpenAI-compatible provider.

Costs roughly nothing — one call, one lexeme.

A FAILING CHECK IS NOT AUTOMATICALLY A PROMPT REGRESSION

It can also be the model. The guard runs a free provider; production runs Claude Haiku via the
Batch API. When a check fails, the first question is whether the 5,516 definitions already in
`lexeme_meaning` have the same property — if they do, the prompt is at fault; if they do not,
the free model is simply weaker. `scripts/run_sql.py interlinear_bible_studio_dev "..."` against
`source='corpus'` answers it in one query.

That is how the two prompt fixes in this file's history were told apart from model noise: the
numbered-sense formatting was a genuine prompt weakness (production honoured it, but only just),
while llama's raw newlines were the model.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import types
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYNTH = PROJECT_ROOT / "scripts" / "old" / "synthesize_corpus.py"
AGDT = PROJECT_ROOT / "scripts" / "agdt-attestations.json"

DB_NAME = os.environ.get("LIVE_AI_DB", "interlinear_bible_studio_dev")

BASE_URL = os.environ.get("LIVE_AI_BASE_URL", "https://api.groq.com/openai/v1")
# gpt-oss-120b rather than llama-3.3-70b: llama reproducibly emits literal newlines inside JSON
# string values even when the prompt forbids it in as many words, and production parse_result
# raises on those rather than repairing them. That is a model limit, not a prompt defect — worth
# knowing when choosing a provider, and the reason the default is not the obvious first pick.
MODEL = os.environ.get("LIVE_AI_MODEL", "openai/gpt-oss-120b")
KEY_ENV = os.environ.get("LIVE_AI_KEY_ENV", "GROQ_API_KEY")

# The regression that caused the re-dos is the leading gloss drifting to the word's classical or
# etymological root — precisely what the prompt's CRITICAL ORDERING RULE exists to prevent, and
# it names two of these itself: "δόξα does not mean 'opinion' in the NT" and "ἁμαρτία does not
# mean 'missing the mark'".
#
# Stated as a deny-list rather than an allow-list, deliberately. An allow-list has to enumerate
# every acceptable synonym, and the first version of this check failed a perfectly good
# "utterance" for λόγος because it was not on the list — a guard that cries wolf gets ignored,
# which is worse than not having it. There are many right answers and few specific wrong ones.
FORBIDDEN_LEAD = {
    "G3056": {"reason", "ratio", "logic", "calculation", "reckoning", "proportion"},
    "G1391": {"opinion", "seeming", "appearance", "reputation"},
    "G266": {"missing", "miss", "mark", "error", "failure"},
    "G1577": {"assembly", "gathering", "summoned"},   # ekklesia: 'called-out assembly'
    "G4151": {"breath", "wind", "air"},               # pneuma: the concrete root
}


def load_env() -> None:
    for line in (PROJECT_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_synth_module():
    """
    Import the production prompt builder.

    Two things are in the way, both pre-existing and neither this script's business to fix:

    `synthesize_corpus.py` exits at import when the `anthropic` package is missing, which it is
    here — nothing else needs it. A stub satisfies the import; the client is never constructed,
    only `build_prompt` is called.

    Its AGDT_FILE resolves to `scripts/data/agdt-attestations.json` while the file is actually at
    `scripts/agdt-attestations.json`, so `load_agdt()` returns {} and the prompt silently loses
    its classical attestations section. That has been true of every real run, not just this one
    (see the note printed below). It is corrected here so the prompt under test is the intended
    one rather than the degraded one.
    """
    sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))

    spec = importlib.util.spec_from_file_location("synthesize_corpus", SYNTH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.AGDT_FILE = str(AGDT)
    return mod


def fetch_lexeme(strongs: str):
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(
        host="localhost", port=5432, dbname=DB_NAME,
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASS", "postgres"),
    )
    conn.set_session(readonly=True)
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, strongs_id, lemma, transliteration, part_of_speech AS pos_code
            FROM lexeme WHERE strongs_id = %s
        """, (strongs,))
        row = cur.fetchone()
    return conn, (dict(row) if row else None)


def call_provider(system: str, user: str, api_key: str) -> str:
    """
    One synthesis call.

    Retries on 429 only. Groq's free tier is 8,000 tokens/minute and this prompt is ~7,000, so
    two runs inside a minute rate-limit each other — checking two lexemes in a row would
    otherwise report a provider quota as a prompt failure. Groq states the wait in the error;
    that is used when present rather than a guessed backoff.
    """
    import requests
    import time

    payload = {
        "model": MODEL,
        "temperature": 0.2,
        # 2000 truncated fullDefinition mid-sentence, which then failed the JSON check for a
        # reason that had nothing to do with the prompt. The budget is 450 words of prose across
        # three fields, plus Greek and Hebrew, which tokenise badly.
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    for attempt in range(3):
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]

        if r.status_code == 429 and attempt < 2:
            wait = re.search(r"try again in ([\d.]+)s", r.text)
            delay = float(wait.group(1)) + 1 if wait else 20.0
            print(f"  rate limited, waiting {delay:.0f}s...")
            time.sleep(delay)
            continue

        raise RuntimeError(f"{MODEL} returned {r.status_code}: {r.text[:400]}")

    raise RuntimeError(f"{MODEL}: still rate limited after 3 attempts")


# ── checks ────────────────────────────────────────────────────────────────────
# Each returns (ok, detail). They assert shape and quality, never exact wording — the model is
# free to word a gloss differently between runs and that is not a regression.

def unfence(raw: str) -> str:
    """Strip a markdown code fence, exactly as production parse_result does."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
    return stripped.strip()


def escape_raw_newlines(text: str) -> str:
    r"""
    Escape literal newlines appearing inside JSON string values.

    Models emit these when asked for multi-line prose inside a JSON field, and they are a hard
    parse error. Production `parse_result` does not repair them — it raises, and the batch
    collector loses that word. So this repair exists for the guard's benefit only: it lets the
    remaining quality checks run instead of all of them being masked by one bad byte. Whether
    the response was *strictly* valid is reported separately, and that is the part that matters.
    """
    out, in_string, escaped = [], False, False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = in_string
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch in "\n\r":
            out.append("\\n" if ch == "\n" else "")
            continue
        out.append(ch)
    return "".join(out)


def check_json(raw: str):
    """Returns (strictly_valid, parsed_dict_or_error_string, was_repaired)."""
    body = unfence(raw)
    try:
        return True, json.loads(body), False
    except json.JSONDecodeError as strict_error:
        try:
            return False, json.loads(escape_raw_newlines(body)), True
        except json.JSONDecodeError:
            return False, f"not valid JSON: {strict_error}", False


def run_checks(result: dict, strongs: str) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []

    def add(name, ok, detail=""):
        out.append((name, ok, detail))

    short = (result.get("shortGloss") or "").strip()
    full = (result.get("fullDefinition") or "").strip()
    lxx = result.get("lxxNote")

    add("required fields present",
        all(k in result for k in ("shortGloss", "fullDefinition", "lxxNote")),
        f"got {sorted(result)}")

    add("shortGloss non-empty", bool(short), repr(short))

    # Definition leakage: the failure mode that produced full sentences where a 2-6 word gloss
    # was asked for. Word count catches it without pinning the wording.
    words = len(short.split())
    add("shortGloss is a gloss, not a definition", words <= 14, f"{words} words")

    add("shortGloss has no trailing sentence period",
        not re.search(r"[a-z]\.\s*$", short), repr(short[-30:]))

    # Parenthetical leakage — clean_corpus_shortgloss.py exists because this shipped once.
    add("shortGloss free of parentheticals",
        not re.search(r"[(\[]", short), repr(short))

    add("shortGloss not wrapped in quotes",
        not (short.startswith(('"', "'")) and short.endswith(('"', "'"))), repr(short[:40]))

    senses = [s for s in short.split(";") if s.strip()]
    add("shortGloss sense count sane (1-5)", 1 <= len(senses) <= 5, f"{len(senses)} senses")

    if strongs in FORBIDDEN_LEAD:
        lead = re.split(r"[;,/]", short)[0].strip().lower()
        drift = set(re.findall(r"[a-z]+", lead)) & FORBIDDEN_LEAD[strongs]
        add(f"{strongs} does not lead with its classical/etymological root",
            not drift, f"lead={lead!r} contains {sorted(drift)}")

    add("fullDefinition non-empty", bool(full), f"{len(full)} chars")
    add("fullDefinition has numbered senses",
        bool(re.search(r"^\s*1\.", full, re.M) and re.search(r"^\s*2\.", full, re.M)),
        "no '1.' / '2.' at line start")

    fw = len(full.split())
    add("fullDefinition within the 450-word budget", fw <= 550, f"{fw} words")

    add("fullDefinition is not markdown-fenced", "```" not in full, "contains a code fence")

    if lxx in (None, "", "null"):
        add("lxxNote null is allowed", True, "null — word has no Hebrew/LXX link")
    else:
        text = " ".join(str(v) for v in lxx.values()) if isinstance(lxx, dict) else str(lxx)
        add("lxxNote cites a Strong's Hebrew number",
            bool(re.search(r"\bH\d{3,4}\b", text)), text[:120])

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strongs", default="G3056", help="lexeme to synthesise (default G3056)")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt, make no call")
    ap.add_argument("--show-response", action="store_true", help="print the raw response")
    args = ap.parse_args()

    load_env()

    api_key = os.environ.get(KEY_ENV, "").strip()
    if not api_key and not args.dry_run:
        print(f"SKIP: {KEY_ENV} is not set — live provider check not run.")
        return 0

    if not SYNTH.is_file():
        print(f"ERROR: prompt builder not found at {SYNTH}", file=sys.stderr)
        return 2

    synth = load_synth_module()
    if not AGDT.is_file():
        print(f"NOTE: {AGDT.name} missing — prompt will omit classical attestations.")

    conn, lexeme = fetch_lexeme(args.strongs)
    if not lexeme:
        print(f"ERROR: {args.strongs} not found in {DB_NAME}.lexeme", file=sys.stderr)
        return 2

    meanings = synth.get_meanings(conn, lexeme["id"])
    occurrences = synth.get_nt_occurrences(conn, lexeme["id"])
    system, user = synth.build_prompt(lexeme, meanings, occurrences, synth.load_agdt())
    conn.close()

    print(f"Lexeme    : {lexeme['lemma']} ({lexeme['transliteration']}) {args.strongs}")
    print(f"Sources   : {len(meanings)} lexicons, {len(occurrences)} NT occurrences")
    print(f"Prompt    : {len(system)} + {len(user)} chars")
    print(f"Provider  : {MODEL} @ {BASE_URL}\n")

    if args.dry_run:
        print("=" * 78, "\nSYSTEM\n", "=" * 78, f"\n{system}\n")
        print("=" * 78, "\nUSER\n", "=" * 78, f"\n{user}")
        return 0

    try:
        raw = call_provider(system, user, api_key)
    except Exception as e:
        print(f"ERROR: provider call failed: {e}", file=sys.stderr)
        return 2

    if args.show_response:
        print(raw, "\n")

    strict_ok, parsed, repaired = check_json(raw)
    if not isinstance(parsed, dict):
        print(f"[FAIL] response parses as JSON — {parsed}")
        print(f"\nRaw response:\n{raw[:1000]}")
        return 1

    results = run_checks(parsed, args.strongs)
    results.insert(0, ("response parses as JSON", strict_ok,
                       "raw newlines inside string values — production parse_result would raise"
                       if repaired else ""))

    for name, passed, detail in results:
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))

    failed = [n for n, p, _ in results if not p]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print(f"\nshortGloss: {parsed.get('shortGloss')!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
