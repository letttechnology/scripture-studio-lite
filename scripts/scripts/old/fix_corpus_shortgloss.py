#!/usr/bin/env python3
"""
fix_corpus_shortgloss.py — Post-process corpus-lexicon.json to ensure the
shortGloss first term matches the canonical_word from canonical_words.json.

Background:
  AI synthesis repeatedly puts verbose descriptions first (e.g. "physical body"
  for σάρξ) instead of the traditional NT English word ("flesh"). Every major
  lexicon (Thayer, UGL, Abbott-Smith, Mounce) leads with "flesh". The first term
  of shortGloss is the most prominent display in the Word Detail panel.

Fix:
  For each entry where canonical_word != first term of shortGloss, prepend the
  canonical_word to the shortGloss. The original terms are kept as subsequent
  senses. Idempotent: re-running produces no changes if already applied.

Comparison is case-insensitive and also ignores leading articles ("a ", "an ",
"the ", "to ") so that e.g. "the north" is treated as matching "north" and is
not prepended redundantly.

Usage:
  python scripts/fix_corpus_shortgloss.py [--dry-run] [--strongs G4561]

After running:
  curl -X POST "http://localhost:8080/api/admin/import-corpus?reset=true"
  python scripts/generate_lite_glosses.py --reset
"""

import sys
import json
import re
import argparse
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).parent.parent
CORPUS_LEXICON = ROOT / "data" / "corpus-lexicon.json"
CANONICAL_WORDS = ROOT / "data" / "canonical_words.json"

ARTICLE_RE = re.compile(r'^(a |an |the |to )', re.IGNORECASE)

def strip_articles(s: str) -> str:
    """Strip leading 'a ', 'an ', 'the ', 'to ' for comparison purposes."""
    return ARTICLE_RE.sub('', s).strip()

def already_matches(first_term: str, canonical: str) -> bool:
    """Return True if the first term already leads with the canonical word."""
    return strip_articles(first_term).lower().startswith(canonical.lower())

def fix_shortgloss(short_gloss: str, canonical: str) -> tuple[str, bool]:
    """
    Return (new_shortgloss, changed).
    Prepends canonical as first term if it isn't already there.
    """
    if not short_gloss or not canonical:
        return short_gloss, False
    first_term = short_gloss.split(';')[0].strip()
    if already_matches(first_term, canonical):
        return short_gloss, False
    new_gloss = canonical + '; ' + short_gloss
    return new_gloss, True

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Print changes without writing to file')
    parser.add_argument('--strongs', metavar='ID',
                        help='Process only this Strong\'s ID (e.g. G4561)')
    args = parser.parse_args()

    with open(CANONICAL_WORDS, encoding='utf-8') as f:
        canonical_words = json.load(f)

    with open(CORPUS_LEXICON, encoding='utf-8') as f:
        corpus = json.load(f)

    changed = 0
    skipped_no_canonical = 0
    already_correct = 0

    targets = [args.strongs] if args.strongs else list(corpus.keys())

    for sid in targets:
        if sid not in corpus:
            print(f'WARN: {sid} not in corpus-lexicon.json', file=sys.stderr)
            continue
        cw_entry = canonical_words.get(sid, {})
        canonical = cw_entry.get('canonical_word', '').strip()
        if not canonical:
            skipped_no_canonical += 1
            continue

        entry = corpus[sid]
        old_gloss = entry.get('shortGloss', '')
        new_gloss, did_change = fix_shortgloss(old_gloss, canonical)

        if did_change:
            changed += 1
            first_before = old_gloss.split(';')[0].strip()
            if args.dry_run or args.strongs:
                print(f'{sid}: {first_before!r} → {canonical!r}')
                print(f'  old: {old_gloss[:120]}')
                print(f'  new: {new_gloss[:120]}')
            if not args.dry_run:
                corpus[sid]['shortGloss'] = new_gloss
        else:
            already_correct += 1

    print(f'\nResults: {changed} fixed, {already_correct} already correct, '
          f'{skipped_no_canonical} no canonical word')

    if args.dry_run:
        print('(dry run — no changes written)')
        return

    if args.strongs:
        print('(single-word mode — no file written; remove --strongs to write)')
        return

    if changed == 0:
        print('Nothing to write.')
        return

    with open(CORPUS_LEXICON, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    print(f'Wrote {CORPUS_LEXICON}')
    print()
    print('Next steps:')
    print('  curl -X POST "http://localhost:8080/api/admin/import-corpus?reset=true"')
    print('  python scripts/generate_lite_glosses.py --reset')

if __name__ == '__main__':
    main()
