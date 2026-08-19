"""
parse_strongs_xml.py

Converts strongsgreek.xml → data/strongs-greek.json

Output format:
{
  "G2476": {
    "lemma":    "ἵστημι",
    "translit": "hístēmi",
    "pronounce": "his'-tay-mee",
    "short_def": "to stand (transitively or intransitively)...",
    "derivation": "a prolonged form of ...",
    "kjv_def": "abide, appoint, bring, ..."
  },
  ...
}

Usage:
    python scripts/parse_strongs_xml.py
    python scripts/parse_strongs_xml.py --input data/strongsgreek.xml --output data/strongs-greek.json
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def strip_tags(element) -> str:
    """Return all text content of an element with child tags removed, whitespace collapsed."""
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        # Include unicode attr from <greek> elements
        if child.tag == "greek":
            unicode_val = child.get("unicode", "")
            if unicode_val:
                parts.append(unicode_val)
        # <strongsref language="GREEK" strongs="1537"/> is an EMPTY element — its meaning
        # lives in attributes. Render it as "G1537"/"H1537" or the derivation text loses
        # its cross-references entirely (issue #52: "from and χέω" instead of
        # "from G1537 and χέω").
        elif child.tag == "strongsref":
            num = child.get("strongs", "").strip()
            lang = child.get("language", "GREEK").strip().upper()
            if num:
                try:
                    parts.append(("H" if lang.startswith("H") else "G") + str(int(num)))
                except ValueError:
                    parts.append(num)
        # Recurse into other inline elements (pronunciation text is useless here, skip)
        elif child.tag not in ("pronunciation",):
            parts.append(strip_tags(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def clean_kjv(raw: str) -> str:
    """Strip leading :-- and trailing period from KJV keyword string."""
    s = raw.strip()
    if s.startswith(":--"):
        s = s[3:]
    return s.rstrip(".").strip()


def parse(xml_path: Path) -> dict:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    entries_el = root.find("entries")
    if entries_el is None:
        # Some versions have entries as direct children
        entries_el = root

    result = {}
    skipped = 0

    for entry in entries_el.iter("entry"):
        raw_num = entry.get("strongs", "").strip()
        if not raw_num:
            skipped += 1
            continue

        # Normalise to G{n} without leading zeros
        try:
            num = int(raw_num)
            strongs_id = f"G{num}"
        except ValueError:
            skipped += 1
            continue

        # Greek lemma + translit
        greek_el = entry.find("greek")
        lemma    = greek_el.get("unicode", "").strip() if greek_el is not None else ""
        translit = greek_el.get("translit", "").strip() if greek_el is not None else ""

        # Pronunciation
        pron_el  = entry.find("pronunciation")
        pronounce = pron_el.get("strongs", "").strip() if pron_el is not None else ""

        # Short definition
        def_el   = entry.find("strongs_def")
        short_def = strip_tags(def_el).strip() if def_el is not None else ""

        # Derivation note
        deriv_el  = entry.find("strongs_derivation")
        derivation = strip_tags(deriv_el).strip() if deriv_el is not None else ""

        # KJV keywords
        kjv_el  = entry.find("kjv_def")
        kjv_def = clean_kjv(strip_tags(kjv_el)) if kjv_el is not None else ""

        obj = {}
        if lemma:    obj["lemma"]    = lemma
        if translit: obj["translit"] = translit
        if pronounce: obj["pronounce"] = pronounce
        if short_def: obj["short_def"] = short_def
        if derivation: obj["derivation"] = derivation
        if kjv_def:  obj["kjv_def"]  = kjv_def

        result[strongs_id] = obj

    return result, skipped


def main():
    parser = argparse.ArgumentParser(description="Convert strongsgreek.xml to strongs-greek.json")
    parser.add_argument("--input",  default="data/strongsgreek.xml",  help="Path to strongsgreek.xml")
    parser.add_argument("--output", default="data/strongs-greek.json", help="Output JSON path")
    args = parser.parse_args()

    xml_path = Path(args.input)
    out_path = Path(args.output)

    if not xml_path.exists():
        print(f"ERROR: {xml_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {xml_path}...")
    data, skipped = parse(xml_path)

    print(f"Writing {len(data)} entries to {out_path}...")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Done. {len(data)} entries written, {skipped} skipped.")
    if data:
        sample_key = "G2476"
        if sample_key in data:
            print(f"\nSample {sample_key}:")
            print(json.dumps(data[sample_key], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
