#!/usr/bin/env python3
"""
clean_corpus_shortgloss.py — Strip parentheticals from corpus shortGloss.

Removes (...) content from the shortGloss field in the corpus JSON, then
cleans up any resulting double semicolons, trailing commas, and extra whitespace.

This is a safe first-pass cleanup that does not touch the DB — it writes a
cleaned JSON file. Re-import via POST /admin/import-corpus?reset=true afterward.

Usage:
  python scripts/clean_corpus_shortgloss.py --dry-run              # preview changes
  python scripts/clean_corpus_shortgloss.py --apply                # write cleaned JSON
  python scripts/clean_corpus_shortgloss.py --apply --in-file data/corpus-LITE.json

The cleaned file is written to data/corpus-LITE-v2-cleaned.json by default.
A backup of the input file is always written before --apply overwrites anything.
"""

import json, re, sys, shutil
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
IN_FILE   = BASE_DIR / 'data' / 'corpus-LITE-v2.json'
OUT_FILE  = BASE_DIR / 'data' / 'corpus-LITE-v2-cleaned.json'

PAREN_RE  = re.compile(r'\s*\([^)]*\)')
SEMI_RE   = re.compile(r'(\s*;\s*){2,}')
LEAD_SEMI = re.compile(r'^\s*;\s*')
TRAIL_SEMI= re.compile(r'\s*;\s*$')
TRAIL_COM = re.compile(r'\s*,\s*$')


def clean_gloss(value: str) -> str:
    cleaned = PAREN_RE.sub('', value)
    cleaned = SEMI_RE.sub('; ', cleaned)
    cleaned = LEAD_SEMI.sub('', cleaned)
    cleaned = TRAIL_SEMI.sub('', cleaned)
    cleaned = TRAIL_COM.sub('', cleaned)
    return cleaned.strip()


def run(dry_run: bool, in_file: Path, out_file: Path):
    print(f'Input:  {in_file}')
    if not in_file.exists():
        print(f'ERROR: file not found: {in_file}')
        sys.exit(1)

    with open(in_file, encoding='utf-8') as f:
        data = json.load(f)

    print(f'Loaded {len(data)} entries')

    changes = []
    for strongs_id, entry in data.items():
        original = entry.get('shortGloss', '')
        if '(' not in original:
            continue
        cleaned = clean_gloss(original)
        if cleaned != original:
            changes.append((strongs_id, original, cleaned))

    print(f'Entries with parentheticals to strip: {len(changes)}\n')

    print(f'  {"Strongs":<8} {"Before":<70} {"After"}')
    print('  ' + '-' * 130)
    for sid, before, after in changes[:40]:
        print(f'  {sid:<8} {before[:68]:<70} {after[:68]}')
    if len(changes) > 40:
        print(f'  ... and {len(changes) - 40} more')

    if dry_run:
        print('\n[DRY RUN] No files written.')
        return

    # Backup before writing
    backup = in_file.with_suffix('.json.bak')
    shutil.copy2(in_file, backup)
    print(f'\nBackup written: {backup}')

    # Apply changes to in-memory data
    for sid, _, after in changes:
        data[sid]['shortGloss'] = after

    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'Cleaned file written: {out_file}')
    print(f'\nNext step: rename to corpus-LITE-v2.json (or corpus-LITE.json), then:')
    print('  POST /admin/import-corpus?reset=true')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Strip parentheticals from corpus shortGloss')
    parser.add_argument('--dry-run', action='store_true', help='Preview — no files written (default)')
    parser.add_argument('--apply',   action='store_true', help='Write cleaned JSON to output file')
    parser.add_argument('--in-file', default=str(IN_FILE),  help='Input corpus JSON file')
    parser.add_argument('--out-file',default=str(OUT_FILE), help='Output cleaned JSON file')
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print('ERROR: cannot use --apply and --dry-run together')
        sys.exit(1)

    dry_run = not args.apply
    run(dry_run=dry_run,
        in_file=Path(args.in_file),
        out_file=Path(args.out_file))


if __name__ == '__main__':
    main()
