#!/usr/bin/env python3
"""
generate_lite_glosses.py — Build the LITE morphologically-aware gloss set (Option B).

Pass 1 (B1 — rule-based, free):
  For each of the 137K NT tokens, applies morphology transformation rules to the
  corpus first-sense gloss to produce a context-appropriate English word.

  Examples:
    ἦν   (εἰμί, imperfect indicative 3sg) → "was"
    ὁ    (article, nominative)             → "the"
    Λόγος (noun, nominative sg)            → "word"
    λύσας (aorist participle active)       → "having loosed"
    ἐλύσεν (aorist indicative 3sg active)  → "loosed"

Pass 2 (B2 — AI refinement):
  Finds verb combinations where B1 produced potentially awkward results
  (irregular aorists, perfect tense, etc.) and submits them to Claude Batch API.
  Each unique (strongs_id, tense, mood, voice) combination is submitted once.

Results stored in gloss_set_entry (gloss_set name = 'lite_auto').

Usage:
  python scripts/generate_lite_glosses.py          # run B1, populate DB
  python scripts/generate_lite_glosses.py --dry-run --limit 50  # preview
  python scripts/generate_lite_glosses.py --reset  # re-generate all
  python scripts/generate_lite_glosses.py --b2-submit  # submit B2 batch to Claude
  python scripts/generate_lite_glosses.py --b2-status  # check batch status
  python scripts/generate_lite_glosses.py --b2-collect # apply B2 results to DB

Requirements:
  pip install psycopg2-binary python-dotenv anthropic
"""

import os, sys, re, argparse, unicodedata, json
from pathlib import Path

try:
    from lemminflect import getAllInflections
    _LEMMINFLECT_AVAILABLE = True
except ImportError:
    _LEMMINFLECT_AVAILABLE = False

# ── Canonical words ───────────────────────────────────────────────────────────
# Read from corpus-LITE.json — single source of truth for canonical_word per lemma.
# corpus-LITE.json replaces canonical_words.json (now redundant).
_CORPUS_LITE_FILE = Path(__file__).parent.parent / "data" / "corpus-LITE.json"
CANONICAL_WORDS: dict = {}
if _CORPUS_LITE_FILE.exists():
    with open(_CORPUS_LITE_FILE, encoding="utf-8") as _f:
        CANONICAL_WORDS = json.load(_f)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import psycopg2, psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary")
    sys.exit(1)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "interlinear_bible_dev"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "letttech"),
}

# ── Irregular verb overrides ──────────────────────────────────────────────────
# strongs_id → {morphology_key → English gloss}
# morphology_key = (tense, mood, voice_class, person, number)
# voice_class: 'act' covers Active + Deponent; 'pass' covers Passive variants

def _mk(tense, mood, voice, person=None, number=None):
    return (tense, mood, voice, person, number)

IRREGULAR_VERBS = {
    # εἰμί — to be
    "G1510": {
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "am",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "are",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "is",
        _mk("Present",   "Indicative", "act", "1st", "Plural"):    "are",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "are",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "are",
        _mk("Imperfect", "Indicative", "act", "1st", "Singular"):  "was",
        _mk("Imperfect", "Indicative", "act", "2nd", "Singular"):  "were",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was",
        _mk("Imperfect", "Indicative", "act", "1st", "Plural"):    "were",
        _mk("Imperfect", "Indicative", "act", "2nd", "Plural"):    "were",
        _mk("Imperfect", "Indicative", "act", "3rd", "Plural"):    "were",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will be",
        _mk("Future",    "Indicative", "act", "3rd", "Plural"):    "will be",
        _mk("Present",   "Infinitive", "act"):                     "to be",
        _mk("Present",   "Participle", "act"):                     "being",
        _mk("Present",   "Subjunctive","act", "3rd", "Singular"):  "may be",
        _mk("Present",   "Subjunctive","act", "3rd", "Plural"):    "may be",
    },
    # ἔρχομαι — to come / go
    "G2064": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "comes",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "come",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was coming",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "came",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "came",
        _mk("Aorist",    "Participle", "act"):                     "having come",
        _mk("Present",   "Participle", "act"):                     "coming",
        _mk("Present",   "Infinitive", "act"):                     "to come",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will come",
    },
    # λέγω — to say / speak
    "G3004": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "says",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "say",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was saying",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "said",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "said",
        _mk("Aorist",    "Participle", "act"):                     "having said",
        _mk("Present",   "Participle", "act"):                     "saying",
        _mk("Present",   "Infinitive", "act"):                     "to say",
    },
    # ὁράω / εἶδον — to see
    "G3708": {
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "saw",
        _mk("Imperfect", "Indicative", "act", "3rd", "Plural"):    "saw",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "saw",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "saw",
        _mk("Aorist",    "Participle", "act"):                     "having seen",
        _mk("Present",   "Participle", "act"):                     "seeing",
        _mk("Aorist",   "Indicative", "pass", "3rd", "Singular"):  "was seen",
        _mk("Aorist",   "Indicative", "pass", "3rd", "Plural"):    "were seen",
        _mk("Aorist",   "Indicative", "pass", "1st", "Singular"):  "was seen",
        _mk("Aorist",   "Participle", "pass"):                     "having been seen",
        _mk("Perfect",  "Indicative", "pass", "3rd", "Singular"):  "has been seen",
        _mk("Future",   "Indicative", "pass", "3rd", "Singular"):  "will be seen",
        _mk("Future",   "Indicative", "pass", "1st", "Singular"):  "will be seen",
    },
    # ἔχω — to have
    "G2192": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "has",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "have",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "had",
        _mk("Imperfect", "Indicative", "act", "3rd", "Plural"):    "had",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "had",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will have",
    },
    # γίνομαι — to become / happen
    "G1096": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "becomes",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was becoming",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "became",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "became",
        _mk("Aorist",    "Indicative", "pass","3rd", "Singular"):  "happened",
        _mk("Aorist",    "Participle", "act"):                     "having become",
        _mk("Present",   "Participle", "act"):                     "becoming",
        _mk("Present",   "Infinitive", "act"):                     "to become",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will become",
    },
    # G1492 covers two distinct Greek word groups sharing one Strong's number:
    #
    # 1. οἶδα  (V-R*) — perfect form, present meaning "know"
    #    MorphGNT stores these with tense=None (R = perfect not parsed as tense string)
    #    V-RAI-* → indicative, V-RAP-* → participle, V-RAN → infinitive,
    #    V-RAM-* → imperative, V-RAS-* → subjunctive
    #    V-2LAI-* (L = pluperfect, tense=None) → "knew" (past meaning)
    #
    # 2. εἶδον (V-2A*) — 2nd aorist stem, meaning "saw / see"
    #    tense=Aorist for these forms.
    #    V-2AAI-* → "saw", V-2AAP-* → "having seen", V-2AAM-* → "see" (imp),
    #    V-2AAN → "to see" (handled by general rule correctly)
    "G1492": {
        # ── οἶδα "know" forms (tense=None, V-RAI-* / V-RAM-* / V-RAN / V-RAP-* / V-RAS-*) ──
        _mk(None, "Indicative", "act", "1st", "Singular"): "know",
        _mk(None, "Indicative", "act", "2nd", "Singular"): "know",
        _mk(None, "Indicative", "act", "3rd", "Singular"): "knows",
        _mk(None, "Indicative", "act", "1st", "Plural"):   "know",
        _mk(None, "Indicative", "act", "2nd", "Plural"):   "know",
        _mk(None, "Indicative", "act", "3rd", "Plural"):   "know",
        _mk(None, "Infinitive", "act"):                    "to know",
        _mk(None, "Participle", "act"):                    "knowing",
        _mk(None, "Imperative", "act"):                    "know",
        _mk(None, "Subjunctive","act", "1st", "Singular"): "may know",
        _mk(None, "Subjunctive","act", "2nd", "Singular"): "may know",
        _mk(None, "Subjunctive","act", "3rd", "Singular"): "may know",
        _mk(None, "Subjunctive","act", "1st", "Plural"):   "may know",
        _mk(None, "Subjunctive","act", "2nd", "Plural"):   "may know",
        _mk(None, "Subjunctive","act", "3rd", "Plural"):   "may know",
        _mk(None, None,         "act"):                    "know",    # V-RAM-* (mood=None → imperative "know")
        # ── εἶδον forms with mood=None (V-2AAM-*, aorist imperative "see!") ──
        _mk("Aorist", None,    "act"):                    "see",     # V-2AAM-* (mood=None)
        # V-2LAI-* pluperfect forms → "knew" (past knowledge)
        # These also have tense=None in DB; differentiate by person/number later
        # For now, the None-tense Indicative entries above cover them as "know"
        # ── εἶδον "saw/see" forms (tense=Aorist, V-2AA*) ──
        _mk("Aorist", "Indicative", "act", "1st", "Singular"): "saw",
        _mk("Aorist", "Indicative", "act", "2nd", "Singular"): "saw",
        _mk("Aorist", "Indicative", "act", "3rd", "Singular"): "saw",
        _mk("Aorist", "Indicative", "act", "1st", "Plural"):   "saw",
        _mk("Aorist", "Indicative", "act", "2nd", "Plural"):   "saw",
        _mk("Aorist", "Indicative", "act", "3rd", "Plural"):   "saw",
        _mk("Aorist", "Participle", "act"):                    "having seen",
        _mk("Aorist", "Imperative", "act"):                    "see",
        # Aorist Infinitive → "to see" is produced correctly by general rule
        # Aorist Subjunctive → "may see" is produced correctly by general rule
    },
    # γεννάω — to beget / father / give birth (irregular: fathered/begot)
    "G1080": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "fathers",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "father",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "fathered",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "fathered",
        _mk("Aorist",    "Indicative", "act", "1st", "Singular"):  "fathered",
        _mk("Aorist",    "Participle", "act"):                     "having fathered",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Singular"): "was born",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Plural"):   "were born",
        _mk("Aorist",    "Participle", "pass"):                    "having been born",
        _mk("Perfect",   "Indicative", "pass", "3rd", "Singular"): "has been born",
        _mk("Present",   "Infinitive", "act"):                     "to father",
        _mk("Present",   "Participle", "act"):                     "fathering",
        _mk("Present",   "Participle", "pass"):                    "being born",
    },
    # νοέω — to understand / perceive with the mind (irregular: understood)
    "G3539": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "understands",
        _mk("Present",   "Participle", "act"):                     "understanding",
        _mk("Present",   "Infinitive", "act"):                     "to understand",
        _mk("Present",   "Participle", "pass"):                    "being understood",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "understood",
        _mk("Aorist",    "Participle", "pass"):                    "having been understood",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Plural"):   "were understood",
    },
    # γινώσκω — to know (irregular past: knew, known)
    "G1097": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "knows",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "know",
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "know",
        _mk("Imperfect", "Indicative", "act", "1st", "Singular"):  "knew",
        _mk("Imperfect", "Indicative", "act", "2nd", "Singular"):  "knew",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "knew",
        _mk("Imperfect", "Indicative", "act", "1st", "Plural"):    "knew",
        _mk("Imperfect", "Indicative", "act", "2nd", "Plural"):    "knew",
        _mk("Imperfect", "Indicative", "act", "3rd", "Plural"):    "knew",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "knew",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "knew",
        _mk("Aorist",    "Indicative", "act", "1st", "Plural"):    "knew",
        _mk("Aorist",    "Participle", "act"):                     "having known",
        _mk("Aorist",    "Participle", "pass"):                    "having been known",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Singular"): "was known",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Plural"):   "were known",
        _mk("Present",   "Participle", "act"):                     "knowing",
        _mk("Present",   "Infinitive", "act"):                     "to know",
        _mk("Perfect",   "Indicative", "act", "3rd", "Singular"):  "has known",
    },
    # παραδίδωμι — to hand over / deliver / betray (G3860)
    "G3860": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "hands over",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was handing over",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "handed over",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "handed over",
        _mk("Aorist",    "Indicative", "act", "1st", "Singular"):  "handed over",
        _mk("Aorist",    "Participle", "act"):                     "having handed over",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Singular"): "was handed over",
        _mk("Aorist",    "Indicative", "pass", "3rd", "Plural"):   "were handed over",
        _mk("Present",   "Infinitive", "act"):                     "to hand over",
        _mk("Present",   "Participle", "act"):                     "handing over",
    },
    # πιστεύω — to believe / trust
    "G4100": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "believes",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "believe",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "believed",
        _mk("Aorist",    "Subjunctive","act", "2nd", "Plural"):    "believe",
        _mk("Present",   "Infinitive", "act"):                     "to believe",
        _mk("Present",   "Participle", "act"):                     "believing",
    },
    # ἀγαπάω — to love
    "G25": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "loves",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "loved",
        _mk("Present",   "Participle", "act"):                     "loving",
        _mk("Present",   "Infinitive", "act"):                     "to love",
    },
    # φεύγω — to flee (irregular past: fled)
    "G5343": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "flees",
        _mk("Present",   "Participle", "act"):                     "fleeing",
        _mk("Present",   "Infinitive", "act"):                     "to flee",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "fled",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "fled",
        _mk("Aorist",    "Indicative", "act", "2nd", "Plural"):    "fled",
        _mk("Aorist",    "Participle", "act"):                     "having fled",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will flee",
        _mk("Future",    "Indicative", "act", "2nd", "Plural"):    "will flee",
    },
    # ἀποφεύγω (G668), ἐκφεύγω (G1628), καταφεύγω (G2703) — compounds of φεύγω
    "G668": {
        _mk("Aorist",    "Participle", "act"):                     "having fled",
        _mk("Aorist",    "Infinitive", "act"):                     "to flee",
    },
    "G1628": {
        _mk("Aorist",    "Indicative", "act", "1st", "Singular"):  "fled",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "fled",
        _mk("Aorist",    "Participle", "act"):                     "having fled",
    },
    "G2703": {
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "fled",
        _mk("Aorist",    "Participle", "act"):                     "having fled",
    },
    # βλέπω — to see/look (G991, aorist "saw")
    "G991": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "sees",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "see",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "saw",
        _mk("Aorist",    "Indicative", "act", "1st", "Singular"):  "saw",
        _mk("Aorist",    "Imperative", "act"):                     "see",
        _mk(None,        "Imperative", "act"):                     "see",
        _mk("Present",   "Participle", "act"):                     "seeing",
        _mk("Present",   "Participle", "pass"):                    "being seen",
        _mk("Present",   "Infinitive", "act"):                     "to see",
    },
    # προοράω / προβλέπω — to foresee (G4308, G4265)
    "G4308": {
        _mk("Aorist",    "Participle", "act"):                     "having foreseen",
    },
    "G4265": {
        _mk("Aorist",    "Participle", "act"):                     "having foreseen",
    },
    # πράσσω — to do / practice (G4238)
    # Corpus base "to do" → same "do" problem as ποιέω. Cover the most common forms.
    "G4238": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "does",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "do",
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "do",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "do",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "do",
        _mk("Imperfect", "Indicative", "act"):                      "was doing",
        _mk("Aorist",    "Indicative", "act"):                      "did",
        _mk("Aorist",    "Participle", "act"):                      "having done",
        _mk("Aorist",    "Participle", "pass"):                     "having been done",
        _mk("Present",   "Participle", "act"):                      "doing",
        _mk("Present",   "Infinitive", "act"):                      "to do",
    },
    # ποιέω — to do / make (G4160)
    # Corpus gives first sense "to make" → base "make" → "makes/made/making" (correct).
    # Explicit entries added here for all high-frequency forms to guarantee quality.
    "G4160": {
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "do",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "do",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "does",
        _mk("Present",   "Indicative", "act", "1st", "Plural"):    "do",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "do",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "do",
        _mk("Imperfect", "Indicative", "act", "3rd", "Singular"):  "was doing",
        _mk("Imperfect", "Indicative", "act", "3rd", "Plural"):    "were doing",
        _mk("Aorist",    "Indicative", "act", "1st", "Singular"):  "did",
        _mk("Aorist",    "Indicative", "act", "2nd", "Singular"):  "did",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "did",
        _mk("Aorist",    "Indicative", "act", "1st", "Plural"):    "did",
        _mk("Aorist",    "Indicative", "act", "2nd", "Plural"):    "did",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "did",
        _mk("Aorist",    "Indicative", "pass","3rd", "Singular"):  "was done",
        _mk("Aorist",    "Indicative", "pass","3rd", "Plural"):    "were done",
        _mk("Aorist",    "Participle", "act"):                     "having done",
        _mk("Aorist",    "Participle", "pass"):                    "having been done",
        _mk("Present",   "Participle", "act"):                     "doing",
        _mk("Present",   "Participle", "pass"):                    "being done",
        _mk("Present",   "Infinitive", "act"):                     "to do",
        _mk("Aorist",    "Infinitive", "act"):                     "to do",
        _mk("Present",   "Subjunctive","act", "1st", "Singular"):  "may do",
        _mk("Present",   "Subjunctive","act", "2nd", "Singular"):  "may do",
        _mk("Present",   "Subjunctive","act", "3rd", "Singular"):  "may do",
        _mk("Present",   "Subjunctive","act", "1st", "Plural"):    "may do",
        _mk("Present",   "Subjunctive","act", "3rd", "Plural"):    "may do",
        _mk("Aorist",    "Subjunctive","act", "1st", "Singular"):  "may do",
        _mk("Aorist",    "Subjunctive","act", "2nd", "Singular"):  "may do",
        _mk("Aorist",    "Subjunctive","act", "3rd", "Singular"):  "may do",
        _mk("Aorist",    "Subjunctive","act", "1st", "Plural"):    "may do",
        _mk("Aorist",    "Subjunctive","act", "3rd", "Plural"):    "may do",
        _mk("Future",    "Indicative", "act", "1st", "Singular"):  "will do",
        _mk("Future",    "Indicative", "act", "2nd", "Singular"):  "will do",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will do",
        _mk("Future",    "Indicative", "act", "1st", "Plural"):    "will do",
        _mk("Future",    "Indicative", "act", "3rd", "Plural"):    "will do",
        _mk("Perfect",   "Indicative", "act", "3rd", "Singular"):  "has done",
        _mk("Perfect",   "Indicative", "act", "3rd", "Plural"):    "have done",
    },
    # θέλω — to wish / want (G2309)
    # Corpus base "to will" → "will" → _past_ed → "willed" (archaic/wrong for NT).
    # Explicit entries use "wish/wished" which reads naturally in English.
    # No-person-number keys (_mk without 4th/5th args) act as catch-alls for any
    # person/number combo not explicitly listed.
    "G2309": {
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "wish",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "wish",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "wishes",
        _mk("Present",   "Indicative", "act", "1st", "Plural"):    "wish",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "wish",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "wish",
        _mk("Imperfect", "Indicative", "act"):                      "wished",    # catch-all
        _mk("Aorist",    "Indicative", "act"):                      "wished",    # catch-all
        _mk("Aorist",    "Participle", "act"):                      "having wished",
        _mk("Present",   "Participle", "act"):                      "wishing",
        _mk("Present",   "Infinitive", "act"):                      "to wish",
        _mk("Present",   "Subjunctive","act"):                      "may wish",  # catch-all persons
        _mk("Aorist",    "Subjunctive","act"):                      "may wish",
        _mk("Present",   "Optative",   "act"):                      "might wish",
        _mk("Aorist",    "Optative",   "act"):                      "might wish",
        _mk("Present",   "Imperative", "act"):                      "wish",
        _mk("Future",    "Indicative", "act"):                      "will wish",
    },
    # βούλομαι — to wish / intend / purpose (G1014, deponent)
    # Same "willed" problem as θέλω — base "will" from corpus "to will".
    "G1014": {
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "wish",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "wish",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "wishes",
        _mk("Present",   "Indicative", "act", "1st", "Plural"):    "wish",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "wish",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "wish",
        _mk("Imperfect", "Indicative", "act"):                      "wished",
        _mk("Aorist",    "Indicative", "act"):                      "wished",
        _mk("Aorist",    "Participle", "act"):                      "having wished",
        _mk("Present",   "Participle", "act"):                      "wishing",
        _mk("Present",   "Infinitive", "act"):                      "to wish",
        _mk("Present",   "Subjunctive","act"):                      "may wish",
        _mk("Aorist",    "Subjunctive","act"):                      "may wish",
        _mk("Present",   "Optative",   "act"):                      "might wish",
    },
    # ἐνυπνιάζομαι — to dream (G1797, deponent)
    # Acts 2:17 uses future passive ἐνυπνιασθήσονται — deponent, so active in English.
    # Without this, future passive → "will be dreamed".
    "G1797": {
        _mk("Future", "Indicative", "pass"): "will dream",
    },
    # δεῖ — it is necessary (G1163, impersonal verb)
    # Canonical_word "must" does not inflect usefully ("musting", "musted").
    # This verb has only 4 morphological forms in the NT — enumerate them all.
    "G1163": {
        _mk("Imperfect", "Indicative", "act"):  "was necessary",  # catch-all (only 3rd sg occurs)
        _mk("Present",   "Infinitive", "act"):  "to be necessary",
        _mk("Present",   "Participle", "act"):  "being necessary",
    },
    # δύναμαι — to be able / can (G1410, deponent)
    # Canonical_word "can" is defective (no past tense "canned", no infinitive "to can").
    # Catch-all keys cover all person/number combinations per tense.
    "G1410": {
        _mk("Present",   "Indicative",  "act"):  "can",         # catch-all all persons
        _mk("Imperfect", "Indicative",  "act"):  "could",       # catch-all
        _mk("Aorist",    "Indicative",  "act"):  "could",       # catch-all
        _mk("Future",    "Indicative",  "act"):  "will be able",
        _mk("Present",   "Infinitive",  "act"):  "to be able",
        _mk("Present",   "Participle",  "act"):  "being able",
        _mk("Aorist",    "Participle",  "act"):  "having been able",
        _mk("Present",   "Subjunctive", "act"):  "may be able",
        _mk("Aorist",    "Subjunctive", "act"):  "may be able",
        _mk("Present",   "Optative",    "act"):  "might be able",
        _mk("Aorist",    "Optative",    "act"):  "might be able",
    },
    # ὑστερέω — to fall short (G5302)
    # Middle/passive forms are intransitive in NT — "fall short", NOT "are lacked".
    # All voices use active-meaning English; passive template must not apply.
    "G5302": {
        _mk("Present",   "Indicative", "act", "1st", "Singular"):  "fall short",
        _mk("Present",   "Indicative", "act", "2nd", "Singular"):  "fall short",
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "falls short",
        _mk("Present",   "Indicative", "act", "1st", "Plural"):    "fall short",
        _mk("Present",   "Indicative", "act", "2nd", "Plural"):    "fall short",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "fall short",
        _mk("Present",   "Indicative", "pass", "1st", "Plural"):   "fall short",
        _mk("Present",   "Indicative", "pass", "3rd", "Plural"):   "fall short",
        _mk("Present",   "Participle", "act"):                     "falling short",
        _mk("Present",   "Participle", "pass"):                    "falling short",
        _mk("Present",   "Infinitive", "pass"):                    "to fall short",
        _mk("Present",   "Infinitive", "act"):                     "to fall short",
        _mk("Aorist",    "Indicative", "act"):                     "fell short",
        _mk("Aorist",    "Indicative", "pass"):                    "fell short",
        _mk("Aorist",    "Participle", "act"):                     "having fallen short",
        _mk("Aorist",    "Participle", "pass"):                    "having fallen short",
        _mk("Perfect",   "Indicative", "act"):                     "have fallen short",
        _mk("Perfect",   "Infinitive", "act"):                     "to have fallen short",
    },
    # πίπτω — to fall (G4098); "fall" is now in _ENGLISH_IRREGULAR_PAST (fell/fallen).
    # Explicit entries ensure correct forms for the most common morphologies.
    "G4098": {
        _mk("Present",   "Indicative", "act", "3rd", "Singular"):  "falls",
        _mk("Present",   "Indicative", "act", "3rd", "Plural"):    "fall",
        _mk("Aorist",    "Indicative", "act", "3rd", "Singular"):  "fell",
        _mk("Aorist",    "Indicative", "act", "3rd", "Plural"):    "fell",
        _mk("Aorist",    "Indicative", "act", "1st", "Singular"):  "fell",
        _mk("Aorist",    "Indicative", "act", "2nd", "Singular"):  "fell",
        _mk("Aorist",    "Participle", "act"):                     "having fallen",
        _mk("Present",   "Participle", "act"):                     "falling",
        _mk("Present",   "Infinitive", "act"):                     "to fall",
        _mk("Future",    "Indicative", "act", "3rd", "Singular"):  "will fall",
        _mk("Perfect",   "Indicative", "act", "3rd", "Singular"):  "has fallen",
    },
}

# ── Function word glosses ─────────────────────────────────────────────────────
# For articles, common conjunctions, particles — use fixed glosses
ARTICLE_GLOSS = "the"

FUNCTION_WORD_OVERRIDES = {
    # ── Conjunctions / particles / prepositions ───────────────────────────────
    "G2532": "and",           # καί
    "G1161": "but",           # δέ  (also: and, now — context-dependent, LITE default)
    "G3756": "not",           # οὐ
    "G3361": "not",           # μή
    "G1722": "in",            # ἐν
    "G1537": "from",          # ἐκ/ἐξ
    "G1519": "into",          # εἰς
    "G3754": "that",          # ὅτι
    "G1063": "for",           # γάρ
    "G1223": "through",       # διά
    "G2443": "so that",       # ἵνα
    "G3779": "thus",          # οὕτως
    "G235": "but",           # ἀλλά (strong adversative)
    "G3767": "therefore",     # οὖν
    "G2596": "according to",  # κατά
    "G3326": "with",          # μετά
    "G4314": "to",            # πρός
    "G5228": "above",         # ὑπέρ
    "G1909": "upon",          # ἐπί
    "G3844": "beside",        # παρά
    "G4012": "about",         # περί
    "G575": "from",          # ἀπό
    "G5259": "under",         # ὑπό
    "G1065": "indeed",        # γέ (emphatic particle)
    "G686": "then",          # ἄρα
    "G2089": "still",         # ἔτι
    "G3765": "no longer",     # οὐκέτι
    "G3568": "now",           # νῦν
    "G5119": "then",          # τότε
    "G3699": "where",         # ὅπου
    "G3753": "when",          # ὅτε
    "G5613": "as",            # ὡς
    "G2531": "just as",       # καθώς
    "G1437": "if",            # ἐάν
    "G1487": "if",            # εἰ
    "G3761": "nor",           # οὐδέ
    "G3366": "nor",           # μηδέ
    "G2228": "or",            # ἤ
    # ── Personal pronouns ─────────────────────────────────────────────────────
    "G1473": "I",             # ἐγώ (1st sg)
    "G2249": "we",            # ἡμεῖς (1st pl)
    "G4771": "you",           # σύ / ὑμεῖς (2nd sg/pl — all forms)
    # ── Reflexive / intensive pronouns ────────────────────────────────────────
    "G1438": "himself",       # ἑαυτοῦ (reflexive; default masculine sg form)
    # G846 αὐτός handled in derive_gloss() — case-based inflection (he/him/his/they/their etc.)
    # ── Proper nouns ───────────────────────────────────────────────────────────
    "G4074": "Peter",         # Πέτρος
    "G5547": "Christ",        # Χριστός — title/name in NT; corpus sense 0 "anointed one" is literal not functional
    # ── Relative / interrogative / indefinite pronouns ────────────────────────
    "G3739": "who",           # ὅς (relative pronoun)
    "G3748": "whoever",       # ὅστις (indefinite relative)
    "G5101": "who",           # τίς (interrogative)
    "G5100": "someone",       # τις (indefinite)
    # ── Demonstrative pronouns ────────────────────────────────────────────────
    "G3778": "this",          # οὗτος
    "G1565": "that",          # ἐκεῖνος
    "G3592": "this",          # ὅδε
}

# ── Verb transformation rules ─────────────────────────────────────────────────

def voice_class(voice):
    """Normalize voice to 'act' or 'pass' for rule lookup.
    Middle voice is treated as active for interlinear gloss purposes
    (the middle reflexive sense is conveyed by context, not the gloss form).
    """
    if voice in ("Active", "Deponent", "Middle", "Passive Deponent",
                 "Middle/Passive Deponent", "Middle/Passive", "Middle or Passive"):
        return "act"
    return "pass"


def get_base(corpus_gloss, sense_index=None):
    """Extract a single root verb word from corpus gloss.

    By default uses the FIRST sense (sense_index=None or 0).
    Pass sense_index to select a different semicolon-separated sense —
    used by C1 contextual sense selection when the first sense is wrong.

    Examples (sense_index=None → first sense):
      'to arm with weapons; ...'  → 'arm'   (not 'arm with weapons')
      'to perceive clearly; ...'  → 'perceive'
      'to hand over, deliver; ..' → 'hand'
      'to loose; to free'         → 'loose'

    Phrasal verbs ('hand over', 'mark out') lose their particle here; add
    the important ones to IRREGULAR_VERBS for fully-correct forms.
    """
    if not corpus_gloss:
        return None
    # Split into semicolon-separated senses
    senses = [s.strip() for s in corpus_gloss.split(';') if s.strip()]
    if not senses:
        return None
    # Pick the requested sense (clamp to valid range)
    idx = 0 if sense_index is None else max(0, min(sense_index, len(senses) - 1))
    chosen = senses[idx]
    # Within the chosen sense, take the first comma-separated phrase
    first = chosen.split(',')[0].strip()
    # Strip leading "to " (corpus/LSJ/GK format).
    # Corpus covers all NT lemmas so this is the only case that matters.
    # Dodson "I X" format is deprioritized (rank 5) and should never fire
    # in practice — corpus + LSJ + GK cover all 5,624 NT lemmas.
    if first.lower().startswith("to "):
        first = first[3:].strip()
    elif first.startswith("I "):
        first = first[2:].strip()
    # If the phrase contains "/" alternatives ("become/make"), take the first
    first = re.split(r'/', first)[0].strip()
    # Return only the first word — avoids "arm with weapons" → "arm with weaponsed"
    first_word = first.split()[0].strip() if first else ''
    return first_word if first_word else None


# ── English verb inflection via lemminflect ───────────────────────────────────
# lemminflect knows all English verb forms from corpus data — no hand-coded list.
# Penn Treebank tags used:
#   VBD = simple past       (sinned, fell, brought)
#   VBN = past participle   (sinned, fallen, brought)
#   VBG = present participle (sinning, falling, bringing)
#   VBZ = 3rd sg present    (sins, falls, brings)
#   VBP = non-3rd present   (sin, fall, bring)
#
# Fallback rules handle the rare case where lemminflect has no entry (novel/unknown words).

def _inflect(base_lower, tag):
    """Return the requested English inflection of base_lower using lemminflect.

    tag: Penn Treebank POS tag (VBD, VBN, VBG, VBZ, VBP).
    Falls back to rule-based forms if lemminflect has no entry.
    """
    if _LEMMINFLECT_AVAILABLE:
        forms = getAllInflections(base_lower)
        if tag in forms:
            return forms[tag][0]
        # VBN (past participle) often omitted when identical to VBD — use VBD form
        if tag == "VBN" and "VBD" in forms:
            return forms["VBD"][0]
    # Fallback for unknown words
    if tag == "VBG":
        if base_lower.endswith("ie"):
            return base_lower[:-2] + "ying"
        if base_lower.endswith("e") and not base_lower.endswith("ee"):
            return base_lower[:-1] + "ing"
        return base_lower + "ing"
    if tag in ("VBD", "VBN"):
        if base_lower.endswith("e"):
            return base_lower + "d"
        if base_lower.endswith("y") and len(base_lower) > 1 and base_lower[-2] not in "aeiou":
            return base_lower[:-1] + "ied"
        return base_lower + "ed"
    if tag == "VBZ":
        if base_lower.endswith(("s", "sh", "ch", "x", "z")):
            return base_lower + "es"
        if base_lower.endswith("y") and len(base_lower) > 1 and base_lower[-2] not in "aeiou":
            return base_lower[:-1] + "ies"
        return base_lower + "s"
    return base_lower


def _past_ed(base_lower):
    return _inflect(base_lower, "VBD")


def _past_part(base_lower):
    return _inflect(base_lower, "VBN")


def _ing_form(base_lower):
    return _inflect(base_lower, "VBG")


def apply_verb_rules(strongs_id, tense, mood, voice, person, number, corpus_gloss,
                     sense_index=None, is_stative=False, use_canonical=True):
    """Return morphologically-appropriate English gloss for a verb token.

    use_canonical: if True (default), use CANONICAL_WORDS[strongs_id] as the base
      verb — the AI-verified single English word for this lemma. Set to False when
      an AI sense override selected a non-primary sense (polysemous tokens), so the
      resolved_gloss (already a clean word like "heal") is used directly via get_base.
    sense_index: retained for polysemous sense selection via get_base fallback.
    is_stative: if True, imperfect active produces simple past ("believed") not
      progressive ("was believing"). Stative verbs don't use progressive in English.
    Irregular overrides in IRREGULAR_VERBS always take priority.
    """
    vc = voice_class(voice or "")
    # Normalize empty strings to None — MorphGNT stores "" not NULL for perfect/pluperfect.
    # Use normalized values for ALL comparisons, not just key lookups.
    tense = tense or None
    mood  = mood  or None
    t = tense
    m = mood
    mk = _mk(t, m, vc, person, number)
    mk_no_pn = _mk(t, m, vc)  # for participles/infinitives (no person/number)

    # Check irregular overrides first (sense_index / canonical ignored for irregulars)
    irregulars = IRREGULAR_VERBS.get(strongs_id, {})
    if mk in irregulars:
        return irregulars[mk]
    if mk_no_pn in irregulars:
        return irregulars[mk_no_pn]

    # Derive base verb — prefer canonical_word (AI-verified) for primary senses;
    # fall back to get_base() for AI-selected alternate senses (polysemous tokens)
    # or when canonical_words.json has no entry for this lemma.
    if use_canonical:
        canon_entry = CANONICAL_WORDS.get(strongs_id, {})
        base = (canon_entry.get("canonical_word") or "").strip().lower() or \
               get_base(corpus_gloss, sense_index=sense_index)
    else:
        base = get_base(corpus_gloss, sense_index=sense_index)
    if not base:
        return corpus_gloss

    base_lower = base.lower()

    # ── Infinitive ────────────────────────────────────────────────────────────
    if mood == "Infinitive":
        return f"to {base_lower}"

    # ── Participle ────────────────────────────────────────────────────────────
    if mood == "Participle":
        if tense == "Aorist":
            if vc == "pass":
                return f"having been {_past_part(base_lower)}"
            return f"having {_past_part(base_lower)}"
        if tense in ("Perfect", "Pluperfect", None):
            # None = MorphGNT stores perfect/pluperfect tense as "" which normalizes to None
            if vc == "pass":
                return f"having been {_past_part(base_lower)}"
            return f"having {_past_part(base_lower)}"
        if tense == "Future":
            return f"about to {base_lower}"
        # Present
        if vc == "pass":
            return f"being {_past_part(base_lower)}"
        return _ing_form(base_lower)

    # ── Imperative ────────────────────────────────────────────────────────────
    if mood == "Imperative":
        # Interlinear shows base form — imperative sense is clear from context
        if vc == "pass":
            return f"be {_past_part(base_lower)}"
        return base_lower

    # ── Subjunctive / Optative ────────────────────────────────────────────────
    if mood == "Subjunctive":
        return f"may {base_lower}"
    if mood == "Optative":
        return f"might {base_lower}"

    # ── Indicative (or unspecified mood) ─────────────────────────────────────
    if mood == "Indicative" or mood is None:
        pl = number == "Plural"

        if tense == "Present":
            if vc == "pass":
                return f"are {_past_part(base_lower)}" if pl else f"is {_past_part(base_lower)}"
            if person == "3rd" and not pl:
                return _inflect(base_lower, "VBZ")
            return base_lower

        if tense == "Imperfect":
            if vc == "pass":
                return f"were being {_past_part(base_lower)}" if pl else f"was being {_past_part(base_lower)}"
            if is_stative:
                # Stative verbs don't use progressive: "believed" not "was believing"
                return _past_ed(base_lower)
            return f"were {_ing_form(base_lower)}" if pl else f"was {_ing_form(base_lower)}"

        if tense == "Future":
            if vc == "pass":
                return f"will be {_past_part(base_lower)}"
            return f"will {base_lower}"

        if tense == "Aorist":
            if vc == "pass":
                return f"were {_past_part(base_lower)}" if pl else f"was {_past_part(base_lower)}"
            return _past_ed(base_lower)   # simple past: "took", "led", "said"

        if tense in ("Perfect", None):
            # None = MorphGNT stores perfect tense as "" which normalizes to None
            if vc == "pass":
                return f"have been {_past_part(base_lower)}" if pl else f"has been {_past_part(base_lower)}"
            return f"have {_past_part(base_lower)}" if pl else f"has {_past_part(base_lower)}"

        if tense == "Pluperfect":
            return f"had been {_past_part(base_lower)}" if vc == "pass" else f"had {_past_part(base_lower)}"

    return base_lower  # fallback


# ── Main gloss logic ──────────────────────────────────────────────────────────

def has_direct_object(token, all_tokens_by_id):
    """Return True if any token in the verse is a direct object of this token.
    Used to distinguish transitive from intransitive uses of verbs like ἵστημι.
    """
    if not all_tokens_by_id:
        return False
    my_id = token.get("verse_word_id")
    for other in all_tokens_by_id.values():
        if other.get("dep_head_id") == my_id and \
           (other.get("dep_relation") or "").upper() in {"OBJ", "OCOMP"}:
            return True
    return False


def has_predicative_complement(token, all_tokens_by_id):
    """
    Return True if any sibling token has this token as its head and
    has a predicative-complement relation (XOBJ, ATV, ATVV, SP).
    These relations signal a copulative construction for εἰμί/γίνομαι.
    """
    if not all_tokens_by_id:
        return False
    my_id = token.get("verse_word_id")
    # PROIEL uses lowercase relations: xobj, comp, atr, adv, etc.
    PRED_COMPLEMENT_RELS = {"XOBJ", "COMP", "ATV", "ATVV", "SP"}
    for other in all_tokens_by_id.values():
        if other.get("dep_head_id") == my_id and \
           (other.get("dep_relation") or "").upper() in PRED_COMPLEMENT_RELS:
            return True
    return False


def derive_gloss(token, resolved_gloss, verse_tokens_by_id=None):
    """
    Derive the morphologically correct English gloss for a token (Handler D).

    resolved_gloss: the winning sense word from Handler B — already a clean
    single word or short phrase (e.g. "believe", "grace", "world"). For verbs,
    this becomes the base that inflection rules are applied to. For nouns and
    other parts of speech, it is returned as-is after minor cleanup.

    Handler B resolution happened upstream in get_tokens() via COALESCE:
      lexeme_sense(sense_index=0) → primary sense for most tokens
      token_sense_override.selected_gloss → AI-selected sense for polysemous tokens

    verse_tokens_by_id: optional dict {verse_word_id: token_dict} for all
    tokens in the same verse — enables syntactic context checks (PROIEL data).
    Used only for εἰμί (copulative vs existential) and γίνομαι (transformative
    vs creative). All other tokens use morphology alone.
    """
    pos    = token["pos_code"]
    sid    = token["strongs_id"]
    tense  = token["tense"]
    voice  = token["voice"]
    mood   = token["mood"]
    person = token["person"]
    number = token["number"]
    dep_rel = (token.get("dep_relation") or "").upper()

    # Function word overrides (conjunctions, prepositions, particles)
    if sid and sid in FUNCTION_WORD_OVERRIDES:
        return FUNCTION_WORD_OVERRIDES[sid]

    # Articles
    if pos == "T":
        return ARTICLE_GLOSS

    # G846 αὐτός — three distinct Greek uses:
    #   1. Attributive position (article immediately before αὐτός: τὴν αὐτήν) → "same"
    #   2. Intensive position  (αὐτός before article: αὐτὸς ὁ θεός)           → "himself/herself/itself"
    #   3. Personal pronoun    (no article adjacent)                            → he/she/it/him/her/they/their
    #
    # Detection: if the token at position-1 in the same verse has pos_code='T' (article),
    # αὐτός is in attributive position → gloss as "same". This is a grammar rule, not a heuristic.
    if sid == "G846":
        case   = token.get("grammatical_case") or ""
        number = token.get("number") or ""
        gender = token.get("gender") or ""
        plural = number == "Plural"

        # Check for attributive position: article immediately precedes αὐτός
        # (detected in SQL via self-join on verse_word at position-1)
        if token.get("preceded_by_article"):
            return "same"

        if case == "Nominative":
            if plural:              return "they"
            if gender == "Feminine": return "she"
            if gender == "Neuter":  return "it"
            return "he"
        if case == "Genitive":
            if plural:              return "their"
            if gender == "Feminine": return "her"
            if gender == "Neuter":  return "its"
            return "his"
        if case in ("Dative", "Accusative"):
            if plural:              return "them"
            if gender == "Feminine": return "her"
            if gender == "Neuter":  return "it"
            return "him"
        return "him"  # fallback (vocative etc.)

    # Verbs — apply morphology rules (with optional syntactic context)
    # Note: tense may be "" (empty string) for perfect/pluperfect forms where
    # the DB stores empty rather than NULL. apply_verb_rules normalizes "" → None.
    if pos == "V":
        # ── εἰμί syntactic disambiguation ────────────────────────────────────
        # Imperfect εἰμί in IRREGULAR_VERBS defaults to "was" (copulative).
        # If PROIEL marks this as a predicate (PRED) with NO predicative
        # complement sibling → existential: "existed".
        if sid == "G1510" and tense == "Imperfect" and mood == "Indicative":
            if dep_rel == "PRED" and not has_predicative_complement(
                    token, verse_tokens_by_id):
                return "existed"
            # else: fall through to IRREGULAR_VERBS → "was" / "were"

        # ── γίνομαι syntactic disambiguation ─────────────────────────────────
        # Aorist γίνομαι in IRREGULAR_VERBS defaults to "became".
        # If PROIEL shows no predicative complement → creation context:
        # "came into being".
        if sid == "G1096" and tense == "Aorist" and mood == "Indicative":
            if dep_rel and not has_predicative_complement(token, verse_tokens_by_id):
                return "came into being"
            # else: fall through to IRREGULAR_VERBS → "became"

        # use_canonical=False when Handler C selected an alternate sense for a polysemous
        # token — resolved_gloss is already the correct sense word (e.g. "heal" for σώζω
        # sense_index=1), so canonical_word ("save") must not override it.
        use_canonical = not bool(token.get("has_ai_override"))
        return apply_verb_rules(sid, tense, mood, voice, person, number, resolved_gloss,
                                is_stative=bool(token.get("is_stative")),
                                use_canonical=use_canonical)

    # Everything else (nouns, adjectives, pronouns, adverbs, etc.)
    # Prefer canonical_word (the single authoritative English word for this lemma)
    # over lexeme_sense[0] which may be a verbose phrase like "physical body" when
    # "flesh" is the correct gloss. canonical_words was built from scholarly consensus.
    # Skip when user has selected an alternate sense (has_ai_override).
    if sid and not token.get("has_ai_override"):
        canon_entry = CANONICAL_WORDS.get(sid, {})
        canon_word = (canon_entry.get("canonical_word") or "").strip()
        if canon_word:
            return canon_word

    if resolved_gloss:
        gloss = resolved_gloss.strip()
        # Strip leading "to " that corpus entries sometimes include for non-verbs
        if gloss.lower().startswith("to ") and pos != "V":
            gloss = gloss[3:].strip()
        # If the gloss is still a multi-word phrase (corpus fallback),
        # take only the first comma-separated term
        if ',' in gloss and ';' not in gloss:
            gloss = gloss.split(',')[0].strip()
        return gloss

    return token.get("english_gloss") or ""


# ── DB operations ─────────────────────────────────────────────────────────────

def get_gloss_set_id(conn, name="lite_auto"):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM gloss_set WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            print(f"ERROR: gloss_set '{name}' not found. Run Flyway migration first.")
            sys.exit(1)
        return row[0]


def get_tokens(conn, reset=False, limit=0, strongs=None):
    """Fetch all tokens with their resolved sense gloss (Handler B).

    Handler B resolution order (COALESCE):
      1. token_sense_override.selected_gloss  — AI classification (Handler C, Phase 3)
      2. lexeme_sense.gloss at sense_index 0  — structured primary sense (Phase 2)
      3. lexeme_meaning.short_gloss           — corpus fallback (pre-Phase 2 safety net)

    For polysemous tokens where Handler C has run, token_sense_override provides
    both the sense_index and the pre-resolved gloss string. For all other tokens,
    lexeme_sense sense 0 is the primary gloss.

    The resolved_gloss returned here is a clean single word or short phrase —
    not a semicolon-separated string. derive_gloss() uses it directly as the
    inflection base without further splitting.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        q = """
            SELECT
                vw.id AS verse_word_id,
                vw.verse_id,
                vw.position,
                vw.pos_code,
                -- Attributive αὐτός detection: article immediately before this token?
                (vw_prev.pos_code = 'T') AS preceded_by_article,
                vw.tense,
                vw.voice,
                vw.mood,
                vw.person,
                vw.number,
                vw.gender,
                vw.grammatical_case,
                vw.english_gloss,
                vw.dep_head_id,
                vw.dep_relation,
                l.strongs_id,
                l.is_stative,
                l.is_polysemous,
                -- Handler B: resolved gloss from lexeme_sense (or AI override)
                -- selected_gloss in token_sense_override is audit-only;
                -- live gloss is always read from current lexeme_sense by sense_index
                -- so updating lexeme_sense propagates automatically.
                COALESCE(
                    ls_ai.gloss,                  -- Handler C: lexeme_sense at AI-selected index
                    ls.gloss,                     -- lexeme_sense primary sense (sense_index 0)
                    m.short_gloss                 -- corpus fallback
                ) AS resolved_gloss,
                COALESCE(tso.sense_index, 0) AS sense_index,
                tso.sense_index IS NOT NULL AS has_ai_override,
                -- corpus_gloss kept for fallback and display in dry-run
                m.short_gloss AS corpus_gloss
            FROM verse_word vw
            -- Preceding token (for attributive αὐτός detection: article immediately before?)
            LEFT JOIN verse_word vw_prev ON vw_prev.verse_id = vw.verse_id
                                        AND vw_prev.position = vw.position - 1
            LEFT JOIN lexeme l ON vw.lexeme_id = l.id
            LEFT JOIN lexeme_meaning m ON m.lexeme_id = l.id AND m.source = 'corpus'
            -- Handler B: primary sense from lexeme_sense (sense_index 0)
            LEFT JOIN lexeme_sense ls ON ls.lexeme_id = l.id AND ls.sense_index = 0
            -- Handler C: AI classification override (populated in Phase 3)
            LEFT JOIN token_sense_override tso ON tso.verse_word_id = vw.id
            -- Handler B+C: live gloss at AI-selected sense_index (audit string ignored)
            LEFT JOIN lexeme_sense ls_ai ON ls_ai.lexeme_id = l.id AND ls_ai.sense_index = tso.sense_index
            -- Track existing gloss_set_entry to skip already-glossed tokens
            LEFT JOIN gloss_set gs2 ON gs2.name = 'lite_auto'
            LEFT JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id AND gse.gloss_set_id = gs2.id
        """
        conditions = []
        params = []

        if strongs:
            conditions.append("l.strongs_id = %s")
            params.append(strongs.upper())

        if not reset:
            conditions.append("""
                NOT EXISTS (
                    SELECT 1 FROM gloss_set_entry gse
                    JOIN gloss_set gs ON gse.gloss_set_id = gs.id
                    WHERE gs.name = 'lite_auto' AND gse.verse_word_id = vw.id
                )
            """)

        if conditions:
            q += " WHERE " + " AND ".join(conditions)

        q += " ORDER BY vw.id"

        if limit:
            q += f" LIMIT {limit}"

        cur.execute(q, params)
        return [dict(r) for r in cur.fetchall()]


def upsert_glosses(conn, gloss_set_id, entries):
    """Bulk upsert gloss entries.

    Each entry dict must have: verse_word_id, gloss.
    Optional: sense_index (int or None) — stored alongside the gloss.
    When sense_index is omitted from an entry, the column is not touched on conflict
    (preserves any existing C1 selection).
    """
    # Split into entries with and without sense_index
    with_sense   = [e for e in entries if "sense_index" in e]
    without_sense = [e for e in entries if "sense_index" not in e]

    with conn.cursor() as cur:
        if without_sense:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO gloss_set_entry (gloss_set_id, verse_word_id, gloss)
                VALUES %s
                ON CONFLICT (gloss_set_id, verse_word_id)
                    DO UPDATE SET gloss = EXCLUDED.gloss
            """, [(gloss_set_id, e["verse_word_id"], e["gloss"]) for e in without_sense])
        if with_sense:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO gloss_set_entry (gloss_set_id, verse_word_id, gloss, sense_index)
                VALUES %s
                ON CONFLICT (gloss_set_id, verse_word_id)
                    DO UPDATE SET gloss = EXCLUDED.gloss, sense_index = EXCLUDED.sense_index
            """, [(gloss_set_id, e["verse_word_id"], e["gloss"], e["sense_index"]) for e in with_sense])
    conn.commit()


# ── B2 AI refinement ─────────────────────────────────────────────────────────

B2_BATCH_STATE = Path(__file__).parent.parent / "data" / "b2-batch.json"

# Tenses/moods where B1 may produce wrong results (irregular verbs, perfect, etc.)
B2_TARGET_TENSES = {"Aorist", "Perfect", "Pluperfect"}
B2_TARGET_MOODS  = {"Indicative", "Infinitive", "Participle", "Subjunctive", "Optative"}

# Verbs already handled perfectly by IRREGULAR_VERBS — skip them
B2_SKIP_STRONGS  = set(IRREGULAR_VERBS.keys())

COST_INPUT_PER_M  = 0.40   # batch pricing per 1M input tokens
COST_OUTPUT_PER_M = 2.00   # batch pricing per 1M output tokens


def get_b2_combinations(conn):
    """
    Return unique (strongs_id, tense, mood, voice, corpus_gloss, b1_gloss) tuples
    for verb tokens that are candidates for B2 AI correction.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT
                l.strongs_id,
                vw.tense,
                vw.mood,
                vw.voice,
                m.short_gloss AS corpus_gloss,
                gse.gloss      AS b1_gloss
            FROM verse_word vw
            JOIN lexeme l ON vw.lexeme_id = l.id
            LEFT JOIN lexeme_meaning m ON m.lexeme_id = l.id AND m.source = 'corpus'
            JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id
            JOIN gloss_set gs ON gs.id = gse.gloss_set_id AND gs.name = 'lite_auto'
            WHERE vw.pos_code = 'V'
              AND vw.tense IS NOT NULL
              AND vw.tense = ANY(%s)
              AND vw.mood IS NOT NULL
              AND vw.mood = ANY(%s)
            ORDER BY l.strongs_id, vw.tense, vw.mood, vw.voice
        """, (list(B2_TARGET_TENSES), list(B2_TARGET_MOODS)))
        rows = [dict(r) for r in cur.fetchall()]

    # Filter out already-handled irregular verbs
    return [r for r in rows if r["strongs_id"] not in B2_SKIP_STRONGS]


def build_b2_prompt(strongs_id, tense, mood, voice, corpus_gloss, b1_gloss):
    """Build a terse prompt asking Claude for the correct English gloss form."""
    canon = CANONICAL_WORDS.get(strongs_id, {}).get("canonical_word", "")
    base = canon.strip().lower() or get_base(corpus_gloss) or corpus_gloss or "?"
    vc   = "active" if voice_class(voice or "") == "act" else "passive"
    return (
        f"Greek verb: {strongs_id}, base meaning: \"{base}\"\n"
        f"Morphology: {tense} {mood} {vc}\n"
        f"Current B1 gloss: \"{b1_gloss}\"\n\n"
        f"Give the single best English word (or 2-word phrase like 'will be', 'having gone') "
        f"for this exact Greek morphological form. Reply with ONLY the gloss — no explanation, "
        f"no punctuation, no quotes."
    )


def b2_submit(conn):
    """Submit B2 combinations to Claude Batch API."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)

    combos = get_b2_combinations(conn)
    print(f"Found {len(combos)} unique verb combinations for B2 refinement")

    # Build batch requests — one per unique combo
    seen = set()
    requests = []
    id_map = {}  # custom_id → {strongs_id, tense, mood, voice}

    for row in combos:
        key = (row["strongs_id"], row["tense"], row["mood"], row["voice"])
        if key in seen:
            continue
        seen.add(key)

        def _sid(s): return re.sub(r'[^a-zA-Z0-9_-]', '_', s or 'None')
        raw_id = f"{_sid(row['strongs_id'])}_{_sid(row['tense'])}_{_sid(row['mood'])}_{_sid(row['voice'])}"
        custom_id = raw_id[:64]
        id_map[custom_id] = {
            "strongs_id":   row["strongs_id"],
            "tense":        row["tense"],
            "mood":         row["mood"],
            "voice":        row["voice"],
            "corpus_gloss": row["corpus_gloss"],
            "b1_gloss":     row["b1_gloss"],
        }

        prompt = build_b2_prompt(
            row["strongs_id"], row["tense"], row["mood"],
            row["voice"], row["corpus_gloss"], row["b1_gloss"]
        )
        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 20,
                "messages": [{"role": "user", "content": prompt}],
            },
        })

    print(f"Unique combinations to submit: {len(requests)}")
    est_input_tokens  = len(requests) * 120
    est_output_tokens = len(requests) * 10
    est_cost = (est_input_tokens / 1_000_000 * COST_INPUT_PER_M +
                est_output_tokens / 1_000_000 * COST_OUTPUT_PER_M)
    print(f"Estimated cost: ${est_cost:.4f} ({est_input_tokens:,} in / {est_output_tokens:,} out tokens)")
    input("Press Enter to submit (Ctrl+C to abort)...")

    client = anthropic.Anthropic()
    batch = client.beta.messages.batches.create(requests=requests)
    print(f"\nBatch submitted: {batch.id}")
    print(f"Status: {batch.processing_status}")

    state = {"batch_id": batch.id, "id_map": id_map}
    B2_BATCH_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"State saved to {B2_BATCH_STATE}")


def b2_status():
    """Check the status of the B2 batch."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)

    if not B2_BATCH_STATE.exists():
        print("No B2 batch state found. Run --b2-submit first.")
        sys.exit(1)

    state = json.loads(B2_BATCH_STATE.read_text())
    client = anthropic.Anthropic()
    batch = client.beta.messages.batches.retrieve(state["batch_id"])
    rc = batch.request_counts
    print(f"Batch {batch.id}")
    print(f"Status: {batch.processing_status}")
    print(f"  processing={rc.processing}  succeeded={rc.succeeded}  errored={rc.errored}  canceled={rc.canceled}")
    if batch.processing_status == "ended":
        print("\nBatch complete — run --b2-collect to apply results.")


def b2_collect(conn):
    """Collect B2 results and update gloss_set_entry."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)

    if not B2_BATCH_STATE.exists():
        print("No B2 batch state found. Run --b2-submit first.")
        sys.exit(1)

    state   = json.loads(B2_BATCH_STATE.read_text())
    id_map  = state["id_map"]
    client  = anthropic.Anthropic()

    batch = client.beta.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        print(f"Batch not done yet (status={batch.processing_status}). Try --b2-status.")
        sys.exit(1)

    gloss_set_id = get_gloss_set_id(conn)

    # Collect corrected glosses — {(strongs_id, tense, mood, voice) → corrected_gloss}
    corrections = {}
    ok = failed = skipped = 0
    total_input = total_output = 0

    # Single pass — collect corrections AND usage in one stream read
    for result in client.beta.messages.batches.results(state["batch_id"]):
        meta = id_map.get(result.custom_id)
        if not meta:
            continue

        if result.result.type != "succeeded":
            failed += 1
            continue

        usage = result.result.message.usage
        total_input  += usage.input_tokens
        total_output += usage.output_tokens

        raw = result.result.message.content[0].text.strip().strip('"').strip("'")
        b1  = meta.get("b1_gloss", "")

        if not raw or raw == b1:
            skipped += 1
            continue

        key = (meta["strongs_id"], meta["tense"], meta["mood"], meta["voice"])
        corrections[key] = raw
        ok += 1

    cost = total_input / 1_000_000 * COST_INPUT_PER_M + total_output / 1_000_000 * COST_OUTPUT_PER_M
    print(f"Corrections collected: {ok} improved, {skipped} same as B1, {failed} errors")
    print(f"Actual cost: ${cost:.4f} ({total_input:,} in / {total_output:,} out tokens)")
    if not corrections:
        print("No corrections to apply.")
        return

    # Apply corrections: find all gloss_set_entry rows for matching tokens and update
    print("Looking up affected tokens in DB...")
    updates = []
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        for (strongs_id, tense, mood, voice), corrected in corrections.items():
            cur.execute("""
                SELECT gse.id
                FROM gloss_set_entry gse
                JOIN gloss_set gs ON gs.id = gse.gloss_set_id AND gs.name = 'lite_auto'
                JOIN verse_word vw ON vw.id = gse.verse_word_id
                JOIN lexeme l ON l.id = vw.lexeme_id
                WHERE l.strongs_id = %s
                  AND vw.tense = %s
                  AND vw.mood = %s
                  AND (vw.voice = %s OR (%s IS NULL AND vw.voice IS NULL))
            """, (strongs_id, tense, mood, voice, voice))
            for row in cur.fetchall():
                updates.append((corrected, row["id"]))

    print(f"Updating {len(updates)} gloss_set_entry rows...")
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur, "UPDATE gloss_set_entry SET gloss = %s WHERE id = %s", updates, page_size=2000
        )
    conn.commit()
    print(f"Done — {len(updates)} tokens updated.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate LITE B1 rule-based glosses")
    parser.add_argument("--dry-run",    action="store_true", help="Print samples, no DB writes")
    parser.add_argument("--limit",      type=int, default=0, help="Process only N tokens (B1)")
    parser.add_argument("--reset",      action="store_true", help="Re-generate all tokens (B1)")
    parser.add_argument("--strongs",    type=str, default="", help="Only tokens for this Strong's ID (B1)")
    parser.add_argument("--b2-submit",  action="store_true", help="Submit B2 AI refinement batch")
    parser.add_argument("--b2-status",  action="store_true", help="Check B2 batch status")
    parser.add_argument("--b2-collect", action="store_true", help="Collect B2 results and apply to DB")
    args = parser.parse_args()

    print(f"Connecting to DB {DB_CONFIG['dbname']}@{DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)

    # ── B2 modes ──────────────────────────────────────────────────────────────
    if args.b2_submit:
        b2_submit(conn)
        conn.close()
        return
    if args.b2_status:
        b2_status()
        conn.close()
        return
    if args.b2_collect:
        b2_collect(conn)
        conn.close()
        return

    gloss_set_id = get_gloss_set_id(conn)

    print("Fetching tokens...")
    tokens = get_tokens(conn, reset=args.reset, limit=args.limit, strongs=args.strongs)
    print(f"  {len(tokens)} tokens to process")

    # Check whether PROIEL syntactic data is present (dep_relation populated)
    has_syntax = any(t.get("dep_relation") for t in tokens[:500])
    if has_syntax:
        print("  ✓ PROIEL syntactic data detected — context-aware disambiguation enabled")
    else:
        print("  ℹ  No syntactic data found — morphology-only mode")
        print("     (Run parse_proiel.py --load after downloading PROIEL NT XML)")
    print()

    # Group tokens by verse_id for context window
    from collections import defaultdict
    tokens_by_verse = defaultdict(dict)
    for t in tokens:
        tokens_by_verse[t["verse_id"]][t["verse_word_id"]] = t

    batch = []
    ok = failed = 0
    sample_printed = 0

    for i, token in enumerate(tokens, 1):
        # Handler B: resolved_gloss is the winning sense from lexeme_sense
        # (or AI override from token_sense_override — Phase 3)
        resolved_gloss = token["resolved_gloss"] or token["corpus_gloss"] or ""
        try:
            verse_ctx = tokens_by_verse.get(token["verse_id"]) if has_syntax else None
            gloss = derive_gloss(token, resolved_gloss, verse_tokens_by_id=verse_ctx)
            if not gloss:
                gloss = token["english_gloss"] or ""

            if args.dry_run or (sample_printed < 30):
                sid   = token["strongs_id"] or "?"
                pos   = token["pos_code"] or "?"
                tense = token["tense"] or ""
                mood  = token["mood"] or ""
                rel   = token.get("dep_relation") or ""
                ai_flag = " [AI]" if token.get("has_ai_override") else ""
                print(f"  {sid:8} {pos:5} {tense:12} {mood:12} {rel:8} sense={str(resolved_gloss or '')[:20]:22}{ai_flag:5} → {gloss}")
                sample_printed += 1

            batch.append({"verse_word_id": token["verse_word_id"], "gloss": gloss})
            ok += 1

        except Exception as e:
            print(f"  ERROR token {token['verse_word_id']}: {e}")
            failed += 1

        # Commit in batches of 5000
        if not args.dry_run and len(batch) >= 5000:
            upsert_glosses(conn, gloss_set_id, batch)
            batch = []
            print(f"  {i} tokens committed...")

    if not args.dry_run and batch:
        upsert_glosses(conn, gloss_set_id, batch)

    conn.close()

    print(f"\nDone — {ok} glosses generated, {failed} failed")
    if args.dry_run:
        print("(dry run — no DB writes)")
    else:
        print("LITE gloss set updated in DB.")
        print("Next: wire gloss_set_entry into the token API response.")


if __name__ == "__main__":
    main()
