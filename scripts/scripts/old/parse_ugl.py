"""
Parses the unfoldingWord Greek Lexicon (UGL) markdown files into ugl-lexicon.json.

Source:  data/unfoldingWord/en_ugl/content/G{5digit}/01.md   (6,304 files)
Output:  data/ugl-lexicon.json
License: CC-BY-SA 4.0 (unfoldingWord)

Each entry becomes:
  {
    "G26": {
      "shortGloss":     "love",           # first Glosses line from Sense 1.0
      "fullDefinition": "..."             # all senses: Definition + Explanation
    }
  }
"""
import json
import os
import re

CONTENT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data',
                           'unfoldingWord', 'en_ugl', 'content')
OUTPUT     = os.path.join(os.path.dirname(__file__), '..', 'data', 'ugl-lexicon.json')


# ── Helpers ───────────────────────────────────────────────────────────────────

def dir_to_strongs(dirname: str) -> str | None:
    """
    UGL uses a 10x numbering scheme: directory G00260 = Strong's G26.
    Returns None for out-of-range or placeholder directories.
    """
    if not dirname.startswith('G') or not dirname[1:].isdigit():
        return None
    num = int(dirname[1:]) // 10
    if num == 0 or num > 5843:
        return None
    return f'G{num}'


def extract_senses(text: str) -> list[dict]:
    """Return list of {glosses, definition, explanation} dicts, one per sense block."""
    # Split on sense headers: ### Sense  1.0:
    parts = re.split(r'###\s+Sense\s+\d+\.\d+\s*:', text)
    senses = []
    for part in parts[1:]:          # skip preamble before first sense
        glosses     = _section(part, 'Glosses')
        definition  = _section(part, 'Definition')
        explanation = _section(part, 'Explanation')
        if glosses or definition:
            senses.append({
                'glosses':     glosses,
                'definition':  definition,
                'explanation': explanation,
            })
    return senses


def _section(text: str, heading: str) -> str:
    """Extract text under a #### Heading: block, stopping at the next ####."""
    pattern = rf'####\s+{heading}\s*:?\s*\n(.*?)(?=####|\Z)'
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ''
    raw = m.group(1)
    # Strip markdown links [text](url) → text
    raw = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', raw)
    # Strip orphaned ](url) remnants (malformed links in source)
    raw = re.sub(r'\]\([^\)]*\)', '', raw)
    # Strip leading ~ on citation lines (sense category markers)
    raw = re.sub(r'^~', '', raw, flags=re.MULTILINE)
    # Collapse whitespace
    lines = [l.strip() for l in raw.split('\n')]
    lines = [l for l in lines if l]
    return ' '.join(lines).strip()


def build_entry(senses: list[dict]) -> dict | None:
    if not senses:
        return None

    # shortGloss: first non-empty glosses value from Sense 1
    short_gloss = ''
    for s in senses:
        g = s['glosses'].split(';')[0].split(',')[0].strip()
        if g:
            short_gloss = g
            break
    if not short_gloss:
        return None

    # fullDefinition: each sense as "Sense N: definition. explanation."
    parts = []
    for i, s in enumerate(senses, 1):
        chunks = []
        if s['definition']:
            chunks.append(s['definition'])
        if s['explanation']:
            chunks.append(s['explanation'])
        if chunks:
            parts.append(f"Sense {i}: {' '.join(chunks)}")

    full_def = '\n\n'.join(parts) if parts else short_gloss

    return {'shortGloss': short_gloss, 'fullDefinition': full_def}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    result = {}
    skipped_out_of_range = 0
    skipped_no_senses    = 0

    dirs = sorted(os.listdir(CONTENT_DIR))
    for d in dirs:
        strongs = dir_to_strongs(d)
        if strongs is None:
            skipped_out_of_range += 1
            continue

        md_path = os.path.join(CONTENT_DIR, d, '01.md')
        if not os.path.isfile(md_path):
            continue

        text = open(md_path, encoding='utf-8').read()

        senses = extract_senses(text)
        entry  = build_entry(senses)
        if entry is None:
            skipped_no_senses += 1
            continue

        result[strongs] = entry

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Written {len(result)} entries to {OUTPUT}")
    print(f"Skipped: {skipped_out_of_range} out-of-range, "
          f"{skipped_no_senses} no senses")

    # Spot-check
    for k in ['G1', 'G26', 'G2889', 'G4151', 'G3056']:
        e = result.get(k)
        if e:
            print(f"\n{k}:")
            print(f"  shortGloss:     {e['shortGloss']}")
            print(f"  fullDefinition: {e['fullDefinition'][:120]!r}")


if __name__ == '__main__':
    main()
