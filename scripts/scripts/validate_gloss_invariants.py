#!/usr/bin/env python3
"""
Read-only invariant validator for the Studio gloss pipeline.

Validates the two export artifacts against each other. Touches no database,
requires no schema change, and writes nothing except its own report.

    python scripts/validate_gloss_invariants.py \
        --corpus data/exports/corpus-LITE.json \
        --lexis  data/exports/lexis-export.json

Exit code 0 if all invariants hold, 1 otherwise (CI-friendly).

Invariants
----------
I1 COVERAGE      DIAGNOSTIC ONLY. Counts slots whose exported gloss matches what
                 layer 5 would have produced. This cannot prove a rule is
                 missing: the rules engine derives cluster_gloss_rule from the
                 corpus gloss, so layer 4 agreeing with layer 5 is the normal
                 case. Verified against the DB 2026-08-13 -- 18,089 corpus slots,
                 18,093 rules, 0 uncovered. Was previously reported as FAIL,
                 which was a false positive.

I2 SINGLE-VALUED DIAGNOSTIC ONLY. Slots yielding more than one gloss. This is
                 NOT an error: chain layers 1, 1.5 and 2 exist so a single token
                 can deliberately differ from its slot default. Verified
                 2026-08-13 -- all 3 real cases are contextual_gloss rows on
                 polysemous lexemes, i.e. correct. Was previously FAIL, of which
                 17 of 20 were null-lexemeId tokens collapsing into one fake slot.

I3 FORMAT        No exported gloss may contain an unresolved candidate-list
                 separator ('/', ';', ','). Their presence means a raw lexicon
                 string reached the export without sense selection.

I4 JOIN          corpus-LITE and lexis-export must agree exactly on the tokenId
                 set, 1:1 in both directions.

I5 SILENT-SELECT (diagnostic, not pass/fail) Counts tokens whose gloss was
                 produced by taking element [0] of a multi-candidate corpus
                 shortGloss. These are indistinguishable from correct output by
                 inspection, which is precisely why they need counting.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

# Mirrors GlossChainService.fallback() layer 5, corpus branch.
CORPUS_SPLIT = re.compile(r"[;,]")
# Mirrors GlossChainService.fallback() layer 5, english_gloss branch.
ENGLISH_SPLIT = re.compile(r"[/,;]")
# Any separator that indicates an unresolved candidate list.
CANDIDATE_SEP = re.compile(r"[/;,]")

PASS = "PASS"
FAIL = "FAIL"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def corpus_tokens(corpus: dict):
    """Flatten corpus-LITE into (tokenId, word, book, chapter, verse) rows."""
    for book in corpus["books"]:
        for verse in book["verses"]:
            for word in verse["words"]:
                yield (
                    word["tokenId"],
                    word,
                    book["name"],
                    verse["chapter"],
                    verse["verseNum"],
                )


def build_indexes(corpus: dict, lexis: dict):
    tokens = {}
    ref = {}
    for tid, word, book, ch, vs in corpus_tokens(corpus):
        tokens[tid] = word
        ref[tid] = f"{book} {ch}:{vs}"

    morph = {row["tokenId"]: row for row in lexis["tokenMorphology"]}

    # lexemeId -> corpus-source shortGloss (the layer-5 input)
    corpus_short = {}
    for lex in lexis["lexemes"]:
        for meaning in lex.get("meanings") or []:
            if meaning.get("source") == "corpus" and meaning.get("isPrimary"):
                sg = meaning.get("shortGloss")
                if sg:
                    corpus_short[lex["id"]] = sg
                break

    return tokens, ref, morph, corpus_short


# ---------------------------------------------------------------- invariants


def i4_join(tokens, morph) -> tuple[str, list[str]]:
    only_corpus = set(tokens) - set(morph)
    only_morph = set(morph) - set(tokens)
    notes = [
        f"corpus tokens        : {len(tokens):,}",
        f"morphology rows      : {len(morph):,}",
        f"in corpus not morph  : {len(only_corpus):,}",
        f"in morph not corpus  : {len(only_morph):,}",
    ]
    ok = not only_corpus and not only_morph
    return (PASS if ok else FAIL), notes


def i2_single_valued(tokens, morph) -> tuple[list[str], dict]:
    """
    DIAGNOSTIC ONLY -- never fails the run.

    (lexemeId, morphKey) -> gloss is deliberately NOT a function. Chain layers 1
    (token_final_override), 1.5 (contextual_gloss) and 2 (lexeme_sense) exist
    precisely so an individual token can differ from its slot default. A slot
    with two glosses is usually those layers working, not a defect.

    Verified 2026-08-13: all 3 real violations in the current export are
    contextual_gloss rows on is_polysemous lexemes -- correct behaviour.

    Tokens with a null lexemeId are excluded. They are not a slot; grouping them
    together produced 17 of the 20 originally-reported "violations", which was
    a false positive. They are counted separately below -- a token with no
    lexeme IS a real data problem, just a different one.
    """
    by_slot = collections.defaultdict(collections.Counter)
    null_lexeme = 0
    for tid, word in tokens.items():
        m = morph.get(tid)
        if not m:
            continue
        if word.get("lexemeId") is None:
            null_lexeme += 1
            continue
        by_slot[(word["lexemeId"], m["morphKey"])][word["gloss"]] += 1

    violations = {k: dict(v) for k, v in by_slot.items() if len(v) > 1}
    notes = [
        f"distinct (lexeme, morphKey) slots : {len(by_slot):,}",
        f"slots with >1 gloss               : {len(violations):,}",
        f"tokens with NO lexemeId           : {null_lexeme:,}  <- real data gap",
        "multi-gloss slots are expected where a contextual/token override fires",
    ]
    for (lex, mk), glosses in list(violations.items())[:10]:
        notes.append(f"  lexeme {lex} / {mk} -> {glosses}")
    if len(violations) > 10:
        notes.append(f"  ... and {len(violations) - 10:,} more")
    return notes, by_slot


def i3_format(tokens, ref) -> tuple[str, list[str]]:
    bad = collections.Counter()
    example = {}
    for tid, word in tokens.items():
        g = word.get("gloss") or ""
        if CANDIDATE_SEP.search(g):
            bad[g] += 1
            example.setdefault(g, (word["surfaceForm"], ref[tid]))

    total = sum(bad.values())
    notes = [
        f"tokens with a candidate separator : {total:,}",
        f"distinct offending gloss strings  : {len(bad):,}",
    ]
    for g, n in bad.most_common(15):
        sf, where = example[g]
        notes.append(f"  {n:6,}  {g!r}  (e.g. {sf} @ {where})")
    return (PASS if total == 0 else FAIL), notes


def i1_coverage(tokens, morph, corpus_short, ref) -> tuple[str, list[str]]:
    """
    DIAGNOSTIC ONLY -- never fails the run. See the I1 note in the module
    docstring.

    A slot is flagged when its exported gloss is byte-identical to what layer 5
    would have produced from the corpus shortGloss. That is consistent with
    every higher layer having missed -- but it is equally consistent with a
    higher layer firing and happening to agree. Since the rules engine derives
    cluster_gloss_rule *from* the corpus gloss, agreement is the normal case,
    not the exception.

    Measured against the database 2026-08-13: every (lexeme_id, morph_key) pair
    in the corpus has a cluster_gloss_rule row -- 18,089 slots, 18,093 rules,
    0 uncovered. The 8,339 slots this heuristic flags are layer 4 firing and
    agreeing with layer 5, which is correct behaviour.

    Real coverage cannot be measured from the exports alone; it needs the DB:

        SELECT COUNT(*) FROM (
          SELECT vw.lexeme_id, vw.morph_key
          FROM verse_word vw
          LEFT JOIN cluster_gloss_rule c
                 ON c.lexeme_id = vw.lexeme_id
                AND c.morph_key = vw.morph_key
                AND c.language_code = 'en'
          WHERE vw.lexeme_id IS NOT NULL AND c.id IS NULL
          GROUP BY vw.lexeme_id, vw.morph_key) x;
    """
    uncovered = collections.Counter()
    example = {}
    slots = set()

    for tid, word in tokens.items():
        m = morph.get(tid)
        if not m:
            continue
        slot = (word["lexemeId"], m["morphKey"])
        slots.add(slot)

        raw = corpus_short.get(word["lexemeId"])
        if not raw:
            continue
        fallback = CORPUS_SPLIT.split(raw)[0].strip()
        if fallback and word["gloss"] == fallback and CANDIDATE_SEP.search(raw):
            uncovered[slot] += 1
            example.setdefault(slot, (word["surfaceForm"], ref[tid], raw))

    notes = [
        f"distinct slots in corpus          : {len(slots):,}",
        f"slots resolved by layer-5 fallback: {len(uncovered):,}",
        f"tokens affected                   : {sum(uncovered.values()):,}",
    ]
    notes.append("NOT a failure -- layer 4 agreeing with layer 5 is expected;")
    notes.append("real coverage must be checked in the DB (see docstring).")
    for slot, n in uncovered.most_common(10):
        sf, where, raw = example[slot]
        notes.append(
            f"  {n:6,}  lexeme {slot[0]:<6} {slot[1]:<22} {sf!r} @ {where}  <- {raw!r}"
        )
    if len(uncovered) > 10:
        notes.append(f"  ... and {len(uncovered) - 10:,} more slots")
    return notes


def i5_silent_selection(tokens, corpus_short) -> list[str]:
    """
    Tokens whose gloss equals element [0] of a multi-candidate corpus
    shortGloss. Unlike I3 these leave no visible trace in the output: the
    separator was consumed by split(), so a wrong pick looks like a right one.
    """
    silent = collections.Counter()
    discarded = collections.Counter()
    for tid, word in tokens.items():
        raw = corpus_short.get(word["lexemeId"])
        if not raw:
            continue
        parts = [p.strip() for p in CORPUS_SPLIT.split(raw) if p.strip()]
        if len(parts) > 1 and word["gloss"] == parts[0]:
            silent[word["lexemeId"]] += 1
            discarded[(parts[0], tuple(parts[1:]))] += 1

    notes = [
        f"tokens glossed by taking candidate[0] : {sum(silent.values()):,}",
        f"lexemes affected                      : {len(silent):,}",
        "these are NOT visible in the export -- the separator was consumed",
    ]
    for (kept, dropped), n in discarded.most_common(10):
        notes.append(f"  {n:6,}  kept {kept!r}, discarded {list(dropped)}")
    return notes


# --------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=Path("data/exports/corpus-LITE.json"))
    ap.add_argument("--lexis", type=Path, default=Path("data/exports/lexis-export.json"))
    args = ap.parse_args()

    # Examples embed Greek surface forms; a cp1252 console would otherwise
    # abort the run mid-report and mask the exit code with a traceback.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    for p in (args.corpus, args.lexis):
        if not p.is_file():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            return 2

    corpus = load(args.corpus)
    lexis = load(args.lexis)
    tokens, ref, morph, corpus_short = build_indexes(corpus, lexis)

    print("=" * 78)
    print("GLOSS PIPELINE INVARIANT REPORT")
    print(f"  corpus : {args.corpus}  (exported {corpus.get('exportedAt')})")
    print(f"  lexis  : {args.lexis}  (exported {lexis.get('exportedAt')})")
    print("=" * 78)

    results = []

    for name, title, fn in (
        ("I4", "JOIN            tokenId sets agree 1:1", lambda: i4_join(tokens, morph)),
        ("I3", "FORMAT          no unresolved candidate lists", lambda: i3_format(tokens, ref)),
    ):
        status, notes = fn()
        results.append((name, status))
        print(f"\n[{status}] {name}  {title}")
        for line in notes:
            print(f"      {line}")

    print("\n[DIAG] I2  SINGLE-VALUED  slots carrying more than one gloss")
    notes, _ = i2_single_valued(tokens, morph)
    for line in notes:
        print(f"      {line}")

    print("\n[DIAG] I1  COVERAGE  slots whose gloss matches the layer-5 fallback")
    for line in i1_coverage(tokens, morph, corpus_short, ref):
        print(f"      {line}")

    print("\n[DIAG] I5  SILENT-SELECT  gloss chosen by array index")
    for line in i5_silent_selection(tokens, corpus_short):
        print(f"      {line}")

    failed = [n for n, s in results if s == FAIL]
    print("\n" + "=" * 78)
    print("  ".join(f"{n}:{s}" for n, s in results))
    print(f"RESULT: {'FAIL - ' + ', '.join(failed) if failed else 'PASS'}")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
