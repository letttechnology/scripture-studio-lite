#!/usr/bin/env python3
"""
parse_agdt.py — Build lemma → attestations index from AGDT v2.1 treebank XML.

Input:  treebank_data-master/v2.1/Greek/texts/*.tb.xml
Output: agdt-attestations.json

Format:
  {
    "λόγος": [
      {
        "author": "Plato",
        "work":   "Euthyphro",
        "era":    "classical",
        "cite":   "urn:cts:greekLit:tlg0059.tlg001:2.3",
        "text":   "ὁ δὲ λόγος ὅδε ἦν"
      },
      ...
    ],
    ...
  }

License: AGDT data is CC-BY-SA (PerseusDL/treebank_data).
Run:  python data/parse_agdt.py
"""

import os
import json
import unicodedata
from collections import defaultdict
from xml.etree import ElementTree as ET

# ── Author/work map (TLG author id . TLG work id → human labels + era) ────────
WORKS = {
    # Homer (~800 BCE)
    "tlg0012.tlg001": ("Homer",     "Iliad",                  "archaic"),
    "tlg0012.tlg002": ("Homer",     "Odyssey",                "archaic"),
    # Pseudo-Homer
    "tlg0013.tlg002": ("Hesiod",    "Shield of Heracles",     "archaic"),
    # Hesiod (~700 BCE)
    "tlg0020.tlg001": ("Aeschylus", "Agamemnon",              "classical"),
    "tlg0020.tlg002": ("Aeschylus", "Libation Bearers",       "classical"),
    "tlg0020.tlg003": ("Aeschylus", "Eumenides",              "classical"),
    # Aeschylus (~525–456 BCE)
    "tlg0011.tlg001": ("Sophocles", "Ajax",                   "classical"),
    "tlg0011.tlg002": ("Sophocles", "Antigone",               "classical"),
    "tlg0011.tlg003": ("Sophocles", "Electra",                "classical"),
    "tlg0011.tlg004": ("Sophocles", "Oedipus Tyrannus",       "classical"),
    "tlg0011.tlg005": ("Sophocles", "Trachinae",              "classical"),
    # Herodotus (~484–425 BCE)
    "tlg0016.tlg001": ("Herodotus", "Histories",              "classical"),
    # Thucydides (~460–400 BCE)
    "tlg0003.tlg001": ("Thucydides","Histories",              "classical"),
    # Plato (~428–348 BCE)
    "tlg0059.tlg001": ("Plato",     "Euthyphro",              "classical"),
    # Lysias (~445–380 BCE)
    "tlg0085.tlg001": ("Lysias",    "Oration 1",              "classical"),
    "tlg0085.tlg002": ("Lysias",    "Oration 14",             "classical"),
    "tlg0085.tlg003": ("Lysias",    "Oration 15",             "classical"),
    "tlg0085.tlg004": ("Lysias",    "Oration 23",             "classical"),
    "tlg0085.tlg005": ("Lysias",    "Oration (other)",        "classical"),
    "tlg0085.tlg006": ("Lysias",    "Oration (other)",        "classical"),
    "tlg0085.tlg007": ("Lysias",    "Oration (other)",        "classical"),
    # Isocrates (~436–338 BCE)
    "tlg0540.tlg001": ("Isocrates", "Oration 1",              "classical"),
    "tlg0540.tlg014": ("Isocrates", "Oration 14",             "classical"),
    "tlg0540.tlg015": ("Isocrates", "Oration 15",             "classical"),
    "tlg0540.tlg023": ("Isocrates", "Oration 23",             "classical"),
    # Polybius (~200–118 BCE)
    "tlg0543.tlg001": ("Polybius",  "Histories",              "hellenistic"),
    # Pseudo-Apollodorus (~1st–2nd c CE)
    "tlg0548.tlg001": ("Apollodorus","Library",               "koine"),
    # Plutarch (~46–120 CE)
    "tlg0007.tlg004": ("Plutarch",  "Alcibiades",             "koine"),
    "tlg0007.tlg015": ("Plutarch",  "Lycurgus",               "koine"),
    # Pausanias (~110–180 CE)
    "tlg0008.tlg001": ("Pausanias", "Description of Greece",  "koine"),
    # Athenaeus (~2nd–3rd c CE)
    "tlg0008.tlg001": ("Athenaeus", "Deipnosophists",         "koine"),
    # Diodorus Siculus (~1st c BCE)
    "tlg0060.tlg001": ("Diodorus",  "Library of History",     "hellenistic"),
    # Dionysius of Halicarnassus (~60–7 BCE)
    "tlg0096.tlg002": ("Dionysius", "Roman Antiquities",      "hellenistic"),
}

# Era priority for sorting (earlier = higher priority in final output)
ERA_ORDER = {"archaic": 0, "classical": 1, "hellenistic": 2, "koine": 3}

TEXTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data",
    "treebank_data-master", "v2.1", "Greek", "texts"
)
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "agdt-attestations.json")

# Max attestations to keep per lemma
MAX_PER_LEMMA = 10
# Min / max sentence length (word count) to be useful as a snippet
MIN_WORDS = 3
MAX_WORDS = 30


def nfc(s):
    return unicodedata.normalize("NFC", s) if s else s


def extract_work_key(filename):
    """Extract 'tlg0012.tlg001' from filename like 'tlg0012.tlg001.perseus-grc1.tb.xml'."""
    parts = os.path.basename(filename).split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return None


def parse_file(filepath):
    """Parse one treebank XML file. Returns list of (lemma, attestation_dict)."""
    work_key = extract_work_key(filepath)
    meta = WORKS.get(work_key)
    if not meta:
        print(f"  ⚠ Unknown work key '{work_key}' — skipping {os.path.basename(filepath)}")
        return []

    author, work, era = meta
    results = []

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"  ✗ XML parse error in {os.path.basename(filepath)}: {e}")
        return []

    for sentence in root.iter("sentence"):
        subdoc = sentence.get("subdoc", "")
        words = sentence.findall("word")

        # Reconstruct sentence text (skip punctuation: postag starts with 'u')
        text_tokens = []
        for w in words:
            postag = w.get("postag", "")
            if postag.startswith("u"):
                continue
            form = nfc(w.get("form", "").strip())
            if form:
                text_tokens.append(form)

        if not (MIN_WORDS <= len(text_tokens) <= MAX_WORDS):
            continue

        sentence_text = " ".join(text_tokens)

        # Collect cite from first word that has one
        cite = ""
        for w in words:
            c = w.get("cite", "").strip()
            if c:
                cite = c
                break

        # Emit one entry per unique lemma in this sentence
        seen_lemmas = set()
        for w in words:
            postag = w.get("postag", "")
            if postag.startswith("u"):
                continue
            lemma = nfc(w.get("lemma", "").strip())
            if not lemma or lemma in seen_lemmas:
                continue
            seen_lemmas.add(lemma)

            results.append((lemma, {
                "author": author,
                "work":   work,
                "era":    era,
                "cite":   cite,
                "text":   sentence_text,
            }))

    return results


def main():
    print("AGDT Parser — building lemma attestation index")
    print(f"Input:  {TEXTS_DIR}")
    print(f"Output: {OUTPUT_FILE}")

    xml_files = sorted(
        f for f in os.listdir(TEXTS_DIR) if f.endswith(".tb.xml")
    )
    print(f"Found {len(xml_files)} XML files\n")

    # lemma → list of attestations
    index = defaultdict(list)

    for filename in xml_files:
        filepath = os.path.join(TEXTS_DIR, filename)
        print(f"Parsing {filename}...")
        entries = parse_file(filepath)
        for lemma, att in entries:
            index[lemma].append(att)

    print(f"\nRaw index: {len(index)} unique lemmas")

    # For each lemma: sort by era priority, deduplicate by author, cap at MAX_PER_LEMMA
    final = {}
    for lemma, atts in index.items():
        # Sort by era (archaic first), then by text length (shorter = more quotable)
        atts.sort(key=lambda a: (ERA_ORDER.get(a["era"], 9), len(a["text"])))

        # Keep variety — max 2 per author
        per_author = defaultdict(int)
        kept = []
        for a in atts:
            if per_author[a["author"]] < 2:
                kept.append(a)
                per_author[a["author"]] += 1
            if len(kept) >= MAX_PER_LEMMA:
                break

        if kept:
            final[lemma] = kept

    print(f"Final index: {len(final)} lemmas (max {MAX_PER_LEMMA} attestations each)")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Written to {OUTPUT_FILE}")

    # Quick sanity check
    for sample in ["λόγος", "πίστις", "χάρις", "ἀγάπη", "θεός"]:
        count = len(final.get(sample, []))
        if count:
            ex = final[sample][0]
            print(f"  {sample}: {count} attestations — first: {ex['author']}, {ex['work']}")
        else:
            print(f"  {sample}: no attestations found")


if __name__ == "__main__":
    main()
