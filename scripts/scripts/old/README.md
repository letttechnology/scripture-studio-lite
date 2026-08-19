# Scripts — Pipeline Reference

Python scripts for the LITE gloss pipeline and data management. All scripts read DB config from `.env` (or environment variables `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`).

---

## Quick Reference

| Script | One-liner | Re-run? |
|---|---|---|
| `populate_lexeme_flags.py` | Seed `is_stative`/`is_deponent`/`is_polysemous` on `lexeme` | One-time |
| `populate_lexeme_sense.py` | Split corpus glosses into `lexeme_sense` rows | One-time; `--reset` if polysemous list expands |
| `extract_canonical_words.py` | Build `data/canonical_words.json` from existing gloss data | Before `synthesize_canonical.py` |
| `synthesize_canonical.py` | AI batch: verify/correct canonical_word per lemma (Haiku) | After corpus gloss changes |
| `run_handler_c.py` | AI batch: sense disambiguation for polysemous tokens | Done; re-run if polysemous lemma list expands |
| `generate_lite_glosses.py` | Generate 138K per-token English glosses (Handler D) | `--reset` after any rule change |
| `test_gloss.py` | Diagnostic: inspect gloss quality | Anytime — `--wrong` finds bad patterns |
| `export_pipeline_audit.py` | Full audit JSON: corpus→canonical→morph→gloss | Anytime — verifies pipeline end-to-end |
| `synthesize_corpus.py` | AI batch: own corpus definitions (Tier 4 lexicon) | Done; re-run if attestations change |
| `parse_agdt.py` | Parse AGDT treebank XML → `data/agdt-attestations.json` | One-time |
| `parse_proiel.py` | Parse PROIEL NT XML → load syntactic dep-rel into DB | One-time |

---

## Full Pipeline (in order)

### Phase 1 — Morphological data (Java importer, not Python)
MorphGNT is imported at server startup via `DatabaseImportRunner`. Produces 137K `verse_word` rows with tense/mood/voice/person/number.

### Phase 2 — Lexicon senses

```bash
# Seed lexeme flags (one-time)
python scripts/populate_lexeme_flags.py

# Populate lexeme_sense (one-time; --reset to re-run)
python scripts/populate_lexeme_sense.py
python scripts/populate_lexeme_sense.py --reset   # wipe and redo
python scripts/populate_lexeme_sense.py --report  # show row counts
```

`lexeme_sense` stores semicolon-split senses from corpus glosses. 16 hand-curated polysemous lemmas (πνεῦμα, λόγος, σάρξ, etc.) use overrides from `POLYSEMOUS_OVERRIDES` in the script.

### Phase 3 — Canonical words

```bash
# Step 1: build initial canonical_words.json from existing gloss data
python scripts/extract_canonical_words.py
python scripts/extract_canonical_words.py --report          # stats
python scripts/extract_canonical_words.py --sample G599 G4160  # spot-check

# Step 2: AI batch to verify/correct all 5,624 lemmas (~$1 at Haiku rates)
python scripts/synthesize_canonical.py --dry-run   # preview prompts
python scripts/synthesize_canonical.py --submit    # submit batch
python scripts/synthesize_canonical.py --status    # check progress
python scripts/synthesize_canonical.py --collect   # apply results

# Step 3: live test specific lemmas
python scripts/synthesize_canonical.py --test G599 G1163 G1410
```

`data/canonical_words.json` — 5,624 entries. Used by `generate_lite_glosses.py` as the base word for verb inflection (replaces string manipulation of corpus definitions).

### Phase 4 — AI sense disambiguation (Handler C)

```bash
python scripts/run_handler_c.py --submit    # batch for polysemous tokens
python scripts/run_handler_c.py --status
python scripts/run_handler_c.py --collect
```

Stores results in `token_sense_override` (2,339 rows). Affects 16 polysemous lemmas.

### Phase 5 — Generate LITE glosses (Handler D)

```bash
# Full regeneration
python scripts/generate_lite_glosses.py --reset

# Dry-run preview
python scripts/generate_lite_glosses.py --dry-run --limit 50

# Single lemma (useful for spot-checking a fix)
python scripts/generate_lite_glosses.py --reset --strongs G599

# B2 AI refinement (optional — fixes awkward aorist/perfect forms)
python scripts/generate_lite_glosses.py --b2-submit
python scripts/generate_lite_glosses.py --b2-status
python scripts/generate_lite_glosses.py --b2-collect
```

Produces 138,013 rows in `gloss_set_entry` (gloss_set `lite_auto`).

---

## Diagnostic Tools

### test_gloss.py — Quality inspection

```bash
# Inspect a specific lemma
python scripts/test_gloss.py G599
python scripts/test_gloss.py G599 --verses          # include NT sample verses

# Top N most frequent lemmas
python scripts/test_gloss.py --top 50

# Find suspicious/wrong gloss patterns
python scripts/test_gloss.py --wrong
```

`--wrong` searches for known-bad patterns: "amed", "doed", "falled", "eated", etc. After a clean pass, the remaining flagged entries are all correct English (adjectives like "seated", "self-willed", "untamed"; passives like "was shamed", "were created").

### export_pipeline_audit.py — End-to-end audit

```bash
# Specific lemmas
python scripts/export_pipeline_audit.py --strongs G599 G4160 G2309

# Top 100 by NT frequency
python scripts/export_pipeline_audit.py --top 100

# Verbs only
python scripts/export_pipeline_audit.py --verbs-only

# Include more sample verses
python scripts/export_pipeline_audit.py --strongs G4151 --verses 5
```

Output: `data/pipeline_audit.json`. Shows for each lemma: corpus_gloss → canonical_word → morphological forms → English gloss + sample verses.

---

## Handler Chain

```
verse_word (MorphGNT morphology)
    ↓
Handler A: morphological parser (MorphGNT import — done at startup)

lexeme_meaning (corpus + LSJ + GK + Dodson)
    ↓ priority: corpus=1, lsj=2, gk=3, mounce=4, dodson=5
lexeme_sense (structured per-sense rows, sense_index 0 = primary)
    ↓
Handler B: lexicon sense retrieval (get_tokens() in generate_lite_glosses.py)

token_sense_override (AI-selected sense for polysemous tokens)
    ↓
Handler C: AI disambiguation (run_handler_c.py — 2,339 tokens, 16 lemmas)

canonical_words.json (AI-verified single English word per lemma)
    ↓
Handler D: inflection engine (generate_lite_glosses.py — 138K glosses)

gloss_set_entry (gloss_set='lite_auto')
    ↓
PassageController → TokenDto.liteGloss → TokenCard (priority 3 in UI)
```

---

## Key Data Files

| File | Size | Purpose |
|---|---|---|
| `data/canonical_words.json` | ~800KB | AI-verified base English word per lemma |
| `data/pipeline_audit.json` | varies | Last audit run output |
| `data/corpus-export.json` | 17.7MB | Backup of corpus synthesis results |
| `data/agdt-attestations.json` | 19MB | AGDT classical corpus (used for corpus synthesis) |

---

## After Fixing Gloss Rules

When you add a new entry to `_ENGLISH_IRREGULAR_PAST`, `IRREGULAR_VERBS`, or fix the suffix rules in `generate_lite_glosses.py`:

```bash
# Re-run just the affected lemma (fast, ~seconds)
python scripts/generate_lite_glosses.py --reset --strongs G1234

# Verify with test_gloss.py
python scripts/test_gloss.py G1234

# Full regeneration (takes ~2 minutes for all 138K tokens)
python scripts/generate_lite_glosses.py --reset

# Final check
python scripts/test_gloss.py --wrong
```
