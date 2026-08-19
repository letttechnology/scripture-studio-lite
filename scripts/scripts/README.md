# scripts/

Index of what lives here, what it needs, and whether it is safe to run again (#34).

`scripts/` accumulated one-off utilities with no index, so the only way to tell a live tool
from a spent one was to read it. Each entry below states **re-runnable / one-time / superseded**,
which is the part that matters.

`scripts/old/` holds 21 scripts kept for reference. Nothing there should be run without
checking whether its target still exists — several reference tables and services that were
removed in the Studio split.

---

## Everyday tools

| Script | What it does | Safe to re-run |
|---|---|---|
| `run_sql.py <db> "<SELECT ...>"` | Read-only query runner. `set_session(readonly=True)` **and** a SELECT/WITH/SHOW/EXPLAIN allow-list — two independent write guards. Credentials from repo-root `.env` | yes — cannot write |
| `validate_gloss_invariants.py` | Checks the two export files against each other. I3 (no candidate separators) and I4 (token sets agree) are pass/fail; I1, I2, I5 are diagnostics that cannot prove what their names suggest | yes — reads files only |
| `backfill_word_insights.py` | Generates Word Insight for high-frequency lemmas by asking Lexis, which calls the AI service. Frequency-ordered so an interrupted run has covered the most-read words | yes — re-reads the cache each run, skips what exists |
| `agile_flow.py` | **Board transitions.** `status` / `start <id>` / `work-done <id>` / `review-done <id>` / `reconcile`. Node IDs for the project, Status field and columns are hardcoded, so no lookup round-trip. Columns: Ready, In Progress, **In Review & Testing**, Done | yes — needs a token with `project` scope |
| `resume_after_limit.py <time>` | Schedules a one-shot task to restart the session when the usage limit resets. The limit kills the session outright, so no hook can catch it — the reset time comes off the limit message and is passed in | yes — replaces any previous schedule |
| `dump_all_dbs.py` | `pg_dump` across the dev databases | yes |
| `check_env_duplicates.py` | Fails if the root `.env` defines a key twice | yes |
| `disk_audit.py` | Where the disk space went | yes |

## Environment and deployment

| Script | What it does | Safe to re-run |
|---|---|---|
| `populate_dev_db_dump_restore.py` | Builds content/Lexis locally, `pg_dump`, ships, `pg_restore` into the cluster. **The current method** — see `docs/decisions/2026-08-01-dev-db-deploy-strategy.md` | yes |
| `populate_dev_db.py` | The older port-forward-and-run-the-Importer method | **superseded** by the above — running it can leave local and cluster diverged |
| `backup-dev-to-test.ps1` | Copies dev DBs to test | yes |
| `harvest_ai_cache.py` | Merges one `ai_dev` cache into another | yes |
| `seed_ai_cache_from_lexis.py` | One-time backfill of Lexis AI content into the AI service before Lexis drops those tables (#268) | **one-time** — and note it drops `generated_at`, which is why that column records the copy rather than the generation (#259) |

## AI content

| Script | What it does | Safe to re-run |
|---|---|---|
| `populate_ai_content.py` | Batch-fills insight / breakdown / morph-suffix via the AI service | yes |
| `AI_API_verification.py` | Checks provider credentials respond | yes |
| `live_corpus_synthesis_check.py [--strongs G3056]` | **Prompt-regression guard.** Imports the real `build_prompt` from `old/synthesize_corpus.py`, sends it to a free provider, asserts 14 structural/quality properties. Skips when `GROQ_API_KEY` is absent. A failure is not automatically a prompt regression — check the stored definitions first | yes — one call, no writes |
| `sense_disambiguate.py` | Per-token sense disambiguation for multi-sense lemmas | yes — but see #317; the sense list it chooses from is corpus fragments |
| `test_passage.py` | Sense disambiguation over one passage, for eyeballing | yes |

## Source parsing

| Script | What it does | Safe to re-run |
|---|---|---|
| `parse_abbott_smith.py` | Abbott-Smith TEI XML → lexicon rows | yes |
| `parse_strongs_xml.py` | Strong's XML → lexicon rows | yes |
| `parse_agdt.py` | AGDT v2.1 treebank → lemma attestations | yes |
| `validate_lemma_coverage.py` | Coverage of parsed lemmas against the corpus | yes |

## One-time repairs — do not re-run

| Script | What it fixed | Why it is spent |
|---|---|---|
| `reset_v45.py` | Dropped audit tables created with a wrong `rev` PK | Targets a schema state that no longer exists. **Writes directly to the DB with hardcoded credentials** |
| `fix_duplicate_lexeme_strongs.py` | Merged duplicate lexeme rows sharing a Strong's id | Already applied |
| `load_corpus_v0_glosses.py` | Replaced corpus `short_gloss` from a v0 export | Already applied |
| `clean_corpus_shortgloss.py` | Strips parentheticals from corpus glosses in the export JSON | Already applied — 0 parentheticals remain in the database |

## Tooling and session helpers

`create_issue.py`, `fetch_issue.py`, `log_session.py`, `recent_sessions.py`,
`export_opencode_chat.py`, `session-start.sh`, `kill-port.mjs`, `run_cmd.py`,
`refactor_effort_audit.py`, `test_populate_ai_content_integration.py`.

`run_cmd.py` is a 2026-07-07 workaround for an allow-list restriction and should be removed
once that no longer applies.

---

## Conventions

**Read-only by default.** `run_sql.py` refuses anything that is not a SELECT. Database
writes go through admin API endpoints, not scripts — the exceptions above are historical and
should not be treated as precedent.

**Encoding.** Anything printing Greek must set UTF-8 explicitly:

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

Without it a cp1252 console aborts mid-output and masks the exit code with a traceback —
which hid two failing checks in `validate_gloss_invariants.py` until 2026-08-13.

**Credentials** come from the repo-root `.env` (`DB_USER`, `DB_PASS`), resolved from the
script's own location. Never hardcode them; `reset_v45.py` does, and is the reason this note
exists.

**Check for existing tooling first.** `agile_flow.py` already covers every board
operation, and a second board script was written and deleted during this session for
exactly that reason. Its own header explains why it is one file: a previous 15-script
version shelled out to each other by absolute path, and archiving the folder snapped every
link at once.

**Before adding a script,** check whether an admin endpoint already does it. The Studio and
AI services own generation, and a script that calls them stays correct as they change — one
that reimplements them does not. `backfill_word_insights.py` is the pattern to copy:
it finds work and asks the service, rather than generating anything itself.
