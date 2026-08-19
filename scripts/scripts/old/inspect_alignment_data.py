#!/usr/bin/env python3
"""
inspect_alignment_data.py — Discover and report the structure of downloaded
alignment data (UGNT / Macula Greek / other) so we can write the right importer.

Run after downloading alignment data into data/:
  python scripts/inspect_alignment_data.py

Reports:
  - What directories / file patterns were found
  - Sample rows from each candidate file
  - Column layouts (for TSV/CSV)
  - XML structure (for XML)
"""

import os, sys, re, json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).parent.parent / "data"

# ── Candidate directory patterns ─────────────────────────────────────────────
SEARCH_ROOTS = [
    "el-x-koine_ugnt*",   # unfoldingWord UGNT
    "en_ult*",             # unfoldingWord ULT (may contain alignment USFM)
    "macula*",             # Clear.Bible Macula Greek
    "Clear-Bible*",        # Clear.Bible (alternate unzip name)
    "alignments*",         # Clear.Bible alignment sub-repos
    "ugnt*",
    "ult*",
]

def find_candidates():
    found = []
    for pat in SEARCH_ROOTS:
        found.extend(DATA_DIR.glob(pat))
    return sorted(set(found))


def sample_tsv(path, n=4):
    try:
        with open(path, encoding="utf-8") as f:
            lines = [f.readline() for _ in range(n + 1)]
        return [l.rstrip("\n") for l in lines if l.strip()]
    except Exception as e:
        return [f"  ERROR: {e}"]


def sample_xml(path, n=60):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(n * 20)[:1500]
    except Exception as e:
        return f"ERROR: {e}"


def sample_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return f"  Array of {len(data)} items. First: {json.dumps(data[0], ensure_ascii=False)[:300]}"
        elif isinstance(data, dict):
            keys = list(data.keys())[:10]
            return f"  Object with keys: {keys}"
    except Exception as e:
        return f"  ERROR: {e}"


def walk_and_report(root: Path, depth=0, max_files_per_ext=3):
    if depth > 4:
        return
    indent = "  " * depth

    # Count files by extension in this directory
    ext_counts = {}
    try:
        entries = list(root.iterdir())
    except PermissionError:
        return

    dirs = sorted(e for e in entries if e.is_dir())
    files = sorted(e for e in entries if e.is_file())

    for f in files:
        ext = f.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    # Report directory
    print(f"{indent}📁 {root.name}/  ({len(dirs)} subdirs, {len(files)} files: {ext_counts})")

    # Sample a few files of each interesting extension
    shown = {}
    for f in files:
        ext = f.suffix.lower()
        if ext not in (".tsv", ".csv", ".xml", ".json", ".usfm", ".sfm", ".txt"):
            continue
        if shown.get(ext, 0) >= max_files_per_ext:
            continue
        shown[ext] = shown.get(ext, 0) + 1

        size_kb = f.stat().st_size // 1024
        print(f"{indent}  📄 {f.name} ({size_kb} KB)")

        if ext in (".tsv", ".csv"):
            rows = sample_tsv(f)
            for r in rows:
                # Truncate each column for display
                cols = r.split("\t")
                display = " | ".join(c[:30] for c in cols[:8])
                print(f"{indent}     {display}")

        elif ext == ".xml":
            snippet = sample_xml(f)
            # Show first interesting lines
            lines = snippet.splitlines()[:12]
            for l in lines:
                print(f"{indent}     {l[:120]}")

        elif ext == ".json":
            info = sample_json(f)
            print(f"{indent}     {info}")

        elif ext in (".usfm", ".sfm"):
            rows = sample_tsv(f, n=8)
            for r in rows:
                print(f"{indent}     {r[:120]}")
        print()

    # Recurse into subdirs (skip node_modules, .git, etc.)
    skip = {".git", "node_modules", "__pycache__", ".github"}
    for d in dirs:
        if d.name in skip:
            continue
        walk_and_report(d, depth + 1, max_files_per_ext)


def main():
    print(f"Scanning {DATA_DIR} for alignment data...\n")
    candidates = find_candidates()

    if not candidates:
        print("No alignment data directories found yet.")
        print("Expected directories matching patterns:")
        for p in SEARCH_ROOTS:
            print(f"  data/{p}")
        print("\nDownload:")
        print("  ULT alignment: github.com/unfoldingWord/el-x-koine_ugnt → ZIP → data/")
        print("  ESV alignment: github.com/Clear-Bible/macula-greek     → ZIP → data/")
        return

    for root in candidates:
        print(f"\n{'='*60}")
        walk_and_report(root)

    print("\n" + "="*60)
    print("Inspection complete. Share this output to get the right importer built.")


if __name__ == "__main__":
    main()
