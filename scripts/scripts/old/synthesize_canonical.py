#!/usr/bin/env python3
"""
synthesize_canonical.py — AI batch pass to derive canonical_word for every NT lemma.

Reads data/canonical_words.json (built by extract_canonical_words.py).
For each lemma, asks Claude: given the corpus definitions + lemma, what single
English word best represents this word in NT usage?

This is the correct source for the rules engine base word — not string
manipulation of definition text.

Usage:
  python scripts/synthesize_canonical.py --submit          # submit batch to Claude
  python scripts/synthesize_canonical.py --status          # check batch progress
  python scripts/synthesize_canonical.py --collect         # apply results → update JSON
  python scripts/synthesize_canonical.py --test G599 G4160 G1163 G1107  # live test (not batch)
  python scripts/synthesize_canonical.py --dry-run         # preview prompts, no API calls

Requirements:
  pip install anthropic python-dotenv
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
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic")
    sys.exit(1)

CANONICAL_FILE   = Path(__file__).parent.parent / "data" / "canonical_words.json"
EXPORT_FILE      = Path(__file__).parent.parent / "data" / "canonical_words_export.json"
BATCH_STATE_FILE = Path(__file__).parent.parent / "data" / "canonical_batch.json"

MODEL = "claude-haiku-4-5-20251001"


def load_canonical():
    if not CANONICAL_FILE.exists():
        print(f"ERROR: {CANONICAL_FILE} not found. Run extract_canonical_words.py first.")
        sys.exit(1)
    with open(CANONICAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_canonical(data):
    with open(CANONICAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_export(data):
    """Write a flat export JSON suitable for re-import or backup.

    Format: list of objects, one per lemma, with all fields.
    Can be re-imported into canonical_words.json via --import-export.
    """
    rows = [
        {"strongs_id": sid, **entry}
        for sid, entry in sorted(data.items())
    ]
    with open(EXPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"Export written to {EXPORT_FILE}  ({len(rows)} entries)")


def build_prompt(strongs_id, lemma, transliteration, corpus_gloss):
    """
    Prompt for one lemma. Asks for a single English word — the canonical
    modern English equivalent for this NT Greek word.

    Rules given to the model:
    - One word only (no phrases, no 'to X')
    - NT usage, not classical
    - For verbs: base/infinitive form (die, not died/dying)
    - For impersonal verbs (δεῖ = 'it is necessary'): use 'must' or 'need'
    - For pronouns/particles: the standard English equivalent
    """
    return f"""You are a New Testament Greek lexicographer. For the Greek word below, give the single best modern English equivalent word for use in an interlinear Bible reader.

Greek: {lemma} ({transliteration}) [{strongs_id}]
Definitions: {corpus_gloss}

Rules:
- One word only. No phrases. No "to X" prefix.
- For verbs: bare infinitive form (die, give, believe — not died/dying/to die)
- For impersonal verbs like δεῖ ("it is necessary"): use must or need
- For compound meanings like "to make known": pick the core verb (reveal, declare)
- For proper nouns: return the name as-is (Jesus, God, Abraham)
- For pronouns/articles/particles: standard English (the, and, not, I, who)
- NT Greek usage, not classical

Reply with exactly one word."""


def build_request(strongs_id, entry):
    return {
        "custom_id": strongs_id,
        "params": {
            "model": MODEL,
            "max_tokens": 20,
            "messages": [{
                "role": "user",
                "content": build_prompt(
                    strongs_id,
                    entry["lemma"],
                    entry["transliteration"],
                    entry["corpus_gloss"] or entry["canonical_word"],
                )
            }]
        }
    }


# ── Live test (no batch) ──────────────────────────────────────────────────────

def run_test(strongs_ids, data):
    client = anthropic.Anthropic()
    print(f"\nLive test — {len(strongs_ids)} lemmas\n")
    print(f"  {'Strongs':<8} {'Lemma':<20} {'Old':<15} {'AI':<15}  Corpus gloss")
    print(f"  {'-'*8} {'-'*20} {'-'*15} {'-'*15}  -----------")

    for sid in strongs_ids:
        sid = sid.upper()
        if not sid.startswith("G"):
            sid = "G" + sid
        entry = data.get(sid)
        if not entry:
            print(f"  {sid} — not found")
            continue

        prompt = build_prompt(sid, entry["lemma"], entry["transliteration"],
                              entry["corpus_gloss"] or entry["canonical_word"])
        resp = client.messages.create(
            model=MODEL,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )
        ai_word = resp.content[0].text.strip().lower().split()[0].rstrip('.,;:')
        old_word = entry["canonical_word"] or "—"
        changed = " ←" if ai_word != old_word else ""
        corpus_preview = (entry["corpus_gloss"] or "")[:55]
        print(f"  {sid:<8} {entry['lemma']:<20} {old_word:<15} {ai_word:<15}  {corpus_preview}{changed}")


# ── Batch submit ──────────────────────────────────────────────────────────────

def submit(data, dry_run=False):
    requests = []
    for sid, entry in data.items():
        if not entry.get("corpus_gloss"):
            continue  # skip entries with no corpus data
        requests.append(build_request(sid, entry))

    print(f"Preparing {len(requests)} batch requests...")

    if dry_run:
        print("\nSample prompts (first 3):\n")
        for req in requests[:3]:
            sid = req["custom_id"]
            e = data[sid]
            print(f"  [{sid}] {e['lemma']}")
            print(f"  {build_prompt(sid, e['lemma'], e['transliteration'], e['corpus_gloss'])}")
            print()
        return

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests)

    state = {
        "batch_id":  batch.id,
        "submitted": batch.created_at.isoformat() if hasattr(batch.created_at, 'isoformat') else str(batch.created_at),
        "count":     len(requests),
        "status":    batch.processing_status,
    }
    with open(BATCH_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    print(f"Submitted: {batch.id}")
    print(f"  {len(requests)} requests | status: {batch.processing_status}")
    print(f"  State saved to {BATCH_STATE_FILE}")
    print(f"\nCheck progress: python scripts/synthesize_canonical.py --status")


# ── Status check ──────────────────────────────────────────────────────────────

def status():
    if not BATCH_STATE_FILE.exists():
        print("No batch state found. Run --submit first.")
        return
    with open(BATCH_STATE_FILE) as f:
        state = json.load(f)

    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(state["batch_id"])
    print(f"Batch: {batch.id}")
    print(f"Status: {batch.processing_status}")
    if hasattr(batch, 'request_counts'):
        rc = batch.request_counts
        print(f"  processing={rc.processing}  succeeded={rc.succeeded}  errored={rc.errored}")
    if batch.processing_status == "ended":
        print("\nReady to collect: python scripts/synthesize_canonical.py --collect")


# ── Collect results ───────────────────────────────────────────────────────────

def collect(data):
    if not BATCH_STATE_FILE.exists():
        print("No batch state found.")
        return
    with open(BATCH_STATE_FILE) as f:
        state = json.load(f)

    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        print(f"Batch not complete yet: {batch.processing_status}")
        return

    updated = 0
    errors = 0
    unchanged = 0

    for result in client.messages.batches.results(state["batch_id"]):
        sid = result.custom_id
        if result.result.type != "succeeded":
            errors += 1
            continue

        raw = result.result.message.content[0].text.strip()
        # Take first word, lowercase, strip punctuation
        word = raw.lower().split()[0].rstrip('.,;:') if raw else ""

        if not word or len(word) > 30:
            errors += 1
            continue

        # Preserve capitalisation for proper nouns (if AI returned capitalised)
        if raw[0].isupper() and word[0].islower():
            word = raw.split()[0].rstrip('.,;:')

        entry = data.get(sid)
        if not entry:
            continue

        old = entry.get("canonical_word", "")
        if word != old:
            entry["canonical_word"] = word
            entry["source"] = "ai"
            updated += 1
        else:
            unchanged += 1

    save_canonical(data)
    save_export(data)
    print(f"Collected: {updated} updated  |  {unchanged} unchanged  |  {errors} errors")
    print(f"Saved to {CANONICAL_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI batch: derive canonical_word per NT lemma")
    parser.add_argument("--submit",        action="store_true", help="Submit batch to Claude API")
    parser.add_argument("--status",        action="store_true", help="Check batch status")
    parser.add_argument("--collect",       action="store_true", help="Collect completed batch results")
    parser.add_argument("--export",        action="store_true", help="Write export JSON from current canonical_words.json")
    parser.add_argument("--import-export", action="store_true", help="Re-apply canonical_words_export.json → canonical_words.json")
    parser.add_argument("--test",          nargs="+", metavar="STRONGS_ID",
                        help="Live test on specific Strong's IDs (e.g. G599 G1163)")
    parser.add_argument("--dry-run",       action="store_true", help="Preview prompts, no API calls")
    args = parser.parse_args()

    data = load_canonical()

    if args.test:
        run_test(args.test, data)
    elif args.status:
        status()
    elif args.collect:
        collect(data)
    elif args.export:
        save_export(data)
    elif args.import_export:
        if not EXPORT_FILE.exists():
            print(f"ERROR: {EXPORT_FILE} not found. Run --collect or --export first.")
            sys.exit(1)
        with open(EXPORT_FILE, encoding="utf-8") as f:
            rows = json.load(f)
        imported = 0
        for row in rows:
            sid = row.get("strongs_id")
            if not sid:
                continue
            entry = {k: v for k, v in row.items() if k != "strongs_id"}
            data[sid] = entry
            imported += 1
        save_canonical(data)
        print(f"Imported {imported} entries from {EXPORT_FILE} → {CANONICAL_FILE}")
    elif args.submit or args.dry_run:
        submit(data, dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
