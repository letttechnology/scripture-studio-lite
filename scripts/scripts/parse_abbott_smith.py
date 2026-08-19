#!/usr/bin/env python3
"""
Parse the Abbott-Smith Manual Greek Lexicon of the NT (TEI XML)
into a clean JSON keyed by Strong's number.

Source file:
  data/abbott-smith.tei.xml
  — Public domain (G. Abbott-Smith, 1922)
  — Available from: https://github.com/translatable-exegetical-tools/Abbott-Smith
    Download the raw XML and place it at data/abbott-smith.tei.json

Output:
  data/abbott-smith-lexicon.json
  Format: { "G1": { "shortGloss": "...", "fullDefinition": "..." }, ... }

Usage:
  python scripts/parse_abbott_smith.py
  python scripts/parse_abbott_smith.py --input data/abbott-smith.tei.json --output data/abbott-smith-lexicon.json
"""

import argparse
import json
import re
import sys
import io
from pathlib import Path
from xml.etree import ElementTree as ET

# The CrossWire TEIOSIS namespace used in this edition
NS = "http://www.crosswire.org/2013/TEIOSIS/namespace"

def tag(local):
    return f"{{{NS}}}{local}"

def all_text(elem) -> str:
    """Extract all text recursively, collapse whitespace."""
    return re.sub(r"\s+", " ", "".join(elem.itertext())).strip()

def parse_entry(entry_elem) -> tuple:
    """
    Returns (strongs_id, { shortGloss, fullDefinition }) or (None, None).
    @n format is 'lemma|G123' — we extract the G-number.
    """
    raw_n = entry_elem.get("n", "")
    m = re.search(r"G(\d+)", raw_n)
    if not m:
        return None, None
    strongs_id = f"G{int(m.group(1))}"

    # Collect all <sense> elements for the full definition
    senses = entry_elem.findall(f".//{tag('sense')}")
    # Also try <def> as a fallback
    if not senses:
        senses = entry_elem.findall(f".//{tag('def')}")

    if not senses:
        return None, None

    sense_texts = [all_text(s) for s in senses if all_text(s)]
    if not sense_texts:
        return None, None

    full_def = "\n".join(sense_texts)

    # Short gloss: first sentence of the first sense, capped at 120 chars
    first = sense_texts[0]
    short = first
    for sep in (";", ":", "."):
        idx = first.find(sep)
        if 0 < idx < 120:
            short = first[:idx].strip()
            break
    if len(short) > 120:
        short = short[:120].strip()

    return strongs_id, {
        "shortGloss": short or None,
        "fullDefinition": full_def,
    }


def parse(input_path: Path) -> dict:
    print(f"Parsing {input_path} ...")
    tree = ET.parse(input_path)
    root = tree.getroot()

    entries = root.findall(f".//{tag('entry')}")
    print(f"  Found {len(entries)} <entry> elements")

    result = {}
    skipped = 0

    for entry in entries:
        strongs_id, data = parse_entry(entry)
        if strongs_id is None:
            skipped += 1
            continue
        if strongs_id not in result:
            result[strongs_id] = data

    print(f"  Parsed {len(result)} entries, skipped {skipped}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Parse Abbott-Smith TEI XML -> JSON")
    parser.add_argument("--input",  default="data/abbott-smith.tei.xml",
                        help="Path to the TEI XML source file")
    parser.add_argument("--output", default="data/abbott-smith-lexicon.json",
                        help="Path for the output JSON")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        # Try .xml extension as fallback
        alt = input_path.with_suffix(".xml") if input_path.suffix == ".json" else input_path.with_suffix(".json")
        if alt.exists():
            input_path = alt
            print(f"Using {input_path}")
        else:
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            print("Download from: https://github.com/translatable-exegetical-tools/Abbott-Smith", file=sys.stderr)
            sys.exit(1)

    data = parse(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  Written to {output_path}")

    # Show a few samples
    for k, v in list(data.items())[:3]:
        print(f"  {k}: {v['shortGloss']!r}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
