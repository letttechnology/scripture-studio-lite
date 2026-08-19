-- =============================================================================
-- admin.sql — Interlinear Bible API: administrative SQL queries
-- Run individual statements via the PostgreSQL VS Code extension.
-- Default connection: interlinear_bible_dev
-- =============================================================================

-- =============================================================================
-- SCHEMA PATCHES — run these if Flyway migrations were not applied to dev
-- Flyway auto-configuration is excluded in BibleApiApplication so migrations
-- must be applied manually when new columns are added.
-- =============================================================================

-- V46: sense_selections_stale flag on admin_state (required by PipelineOrchestrator)
ALTER TABLE admin_state
    ADD COLUMN IF NOT EXISTS sense_selections_stale BOOLEAN NOT NULL DEFAULT FALSE;


-- =============================================================================
-- SENSE OVERRIDES — token_sense_override
-- Handler C pipeline: AI-selected sense per token, feeds regenerate-lite-glosses
-- =============================================================================

-- Verify sense overrides written for a passage (e.g. John 1)
-- Shows: verse ref, Greek word, Strong's ID, AI-selected sense gloss, confidence
SELECT
    b.name || ' ' || v.chapter || ':' || v.verse_num   AS ref,
    vw.surface_form,
    l.strongs_id,
    tso.sense_index,
    tso.selected_gloss,
    tso.confidence,
    tso.method,
    tso.created_at
FROM token_sense_override tso
JOIN verse_word vw ON vw.id  = tso.verse_word_id
JOIN verse      v  ON v.id   = vw.verse_id
JOIN book       b  ON b.id   = v.book_id
JOIN lexeme     l  ON l.id   = vw.lexeme_id
WHERE v.book_id = 43   -- 43 = John  (see NtBooks for full list)
  AND v.chapter = 1
ORDER BY v.verse_num, vw.position;


-- Count of sense overrides per book/chapter (summary)
SELECT
    b.name,
    v.chapter,
    COUNT(*) AS overrides
FROM token_sense_override tso
JOIN verse_word vw ON vw.id = tso.verse_word_id
JOIN verse      v  ON v.id  = vw.verse_id
JOIN book       b  ON b.id  = v.book_id
GROUP BY b.name, b.id, v.chapter
ORDER BY b.id, v.chapter;


-- Total override count across all NT
SELECT COUNT(*) AS total_overrides FROM token_sense_override;


-- =============================================================================
-- COPY SENSE OVERRIDES: interlinear_bible_test → interlinear_bible_dev
--
-- Workflow:
--   1. Run AI pipeline against interlinear_bible_test (safe sandbox)
--   2. Verify results with the query above
--   3. Run Step A against interlinear_bible_TEST to export verified rows
--   4. Run Step B against interlinear_bible_DEV to import them
-- =============================================================================

-- Run against interlinear_bible_DEV
-- CTE (A) reads verified sense overrides from test DB via dblink.
-- INSERT (B) writes them into dev, skipping any already present.
-- Requires dblink extension (run once: CREATE EXTENSION IF NOT EXISTS dblink;)
WITH verified_senses AS (                                          -- A: read from test
    SELECT verse_word_id, sense_index, selected_gloss,
           method, confidence, created_at, updated_at
    FROM dblink(
        'host=localhost port=5432 dbname=interlinear_bible_test user=postgres password=letttech',
        $dlq$
            SELECT tso.verse_word_id, tso.sense_index, tso.selected_gloss,
                   tso.method, tso.confidence, tso.created_at, tso.updated_at
            FROM token_sense_override tso
            JOIN verse_word vw ON vw.id = tso.verse_word_id
            JOIN verse      v  ON v.id  = vw.verse_id
            WHERE v.book_id = 43 AND v.chapter = 1  -- change to target passage
        $dlq$
    ) AS t(verse_word_id INT, sense_index INT, selected_gloss TEXT,
           method TEXT, confidence TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
)
INSERT INTO token_sense_override                                    -- B: write to dev
    (verse_word_id, sense_index, selected_gloss, method, confidence, created_at, updated_at)
SELECT * FROM verified_senses
ON CONFLICT (verse_word_id) DO NOTHING;


-- Full NT copy: test → dev (use after a verified full-NT run in test)
WITH all_senses AS (
    SELECT verse_word_id, sense_index, selected_gloss,
           method, confidence, created_at, updated_at
    FROM dblink(
        'host=localhost port=5432 dbname=interlinear_bible_test user=postgres password=letttech',
        'SELECT verse_word_id, sense_index, selected_gloss, method, confidence, created_at, updated_at
         FROM token_sense_override'
    ) AS t(verse_word_id INT, sense_index INT, selected_gloss TEXT,
           method TEXT, confidence TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
)
INSERT INTO token_sense_override
    (verse_word_id, sense_index, selected_gloss, method, confidence, created_at, updated_at)
SELECT * FROM all_senses
ON CONFLICT (verse_word_id) DO NOTHING;


-- =============================================================================
-- DEV → TEST: keep interlinear_bible_test in sync after running admin endpoint
-- against dev directly (e.g. after curl /admin/import-sense-selections on dev)
-- Run against interlinear_bible_TEST
-- =============================================================================

-- Passage-scoped dev → test sync (change book_id/chapter as needed)
WITH dev_senses AS (
    SELECT verse_word_id, sense_index, selected_gloss,
           method, confidence, created_at, updated_at
    FROM dblink(
        'host=localhost port=5432 dbname=interlinear_bible_dev user=postgres password=letttech',
        $dlq$
            SELECT tso.verse_word_id, tso.sense_index, tso.selected_gloss,
                   tso.method, tso.confidence, tso.created_at, tso.updated_at
            FROM token_sense_override tso
            JOIN verse_word vw ON vw.id = tso.verse_word_id
            JOIN verse      v  ON v.id  = vw.verse_id
            WHERE v.book_id = 43 AND v.chapter = 1
        $dlq$
    ) AS t(verse_word_id INT, sense_index INT, selected_gloss TEXT,
           method TEXT, confidence TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
)
INSERT INTO token_sense_override
    (verse_word_id, sense_index, selected_gloss, method, confidence, created_at, updated_at)
SELECT * FROM dev_senses
ON CONFLICT (verse_word_id) DO NOTHING;


-- Full NT dev → test sync
WITH all_dev_senses AS (
    SELECT verse_word_id, sense_index, selected_gloss,
           method, confidence, created_at, updated_at
    FROM dblink(
        'host=localhost port=5432 dbname=interlinear_bible_dev user=postgres password=letttech',
        'SELECT verse_word_id, sense_index, selected_gloss, method, confidence, created_at, updated_at
         FROM token_sense_override'
    ) AS t(verse_word_id INT, sense_index INT, selected_gloss TEXT,
           method TEXT, confidence TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
)
INSERT INTO token_sense_override
    (verse_word_id, sense_index, selected_gloss, method, confidence, created_at, updated_at)
SELECT * FROM all_dev_senses
ON CONFLICT (verse_word_id) DO NOTHING;


-- =============================================================================
-- GLOSS CHAIN — spot-check what the reader resolves for a passage
-- Shows source layer (gloss_set_entry, contextual_gloss, etc.) per token
-- =============================================================================

-- Spot-check gloss resolution for John 1 (what the reader endpoint returns)
SELECT
    b.name || ' ' || v.chapter || ':' || v.verse_num  AS ref,
    vw.surface_form,
    l.strongs_id,
    gse.gloss                                          AS cached_gloss,
    tso.selected_gloss                                 AS sense_override_gloss,
    tso.sense_index,
    CASE WHEN tso.verse_word_id IS NOT NULL THEN 'has override' ELSE 'no override' END AS override_status
FROM verse_word vw
JOIN verse   v  ON v.id  = vw.verse_id
JOIN book    b  ON b.id  = v.book_id
JOIN lexeme  l  ON l.id  = vw.lexeme_id
LEFT JOIN gloss_set_entry gse
    ON  gse.verse_word_id = vw.id
    AND gse.gloss_set_id  = (SELECT id FROM gloss_set WHERE name = 'lite_auto')
LEFT JOIN token_sense_override tso ON tso.verse_word_id = vw.id
WHERE v.book_id = 43
  AND v.chapter = 1
ORDER BY v.verse_num, vw.position;



-- =============================================================================
-- USER ROLE MANAGEMENT
-- =============================================================================

-- View all users and their roles
SELECT u.email, r.role
FROM app_user u
JOIN user_role r ON r.user_id = u.id
ORDER BY u.email, r.role;

-- Add ROLE_ADMIN for a user (replace email)
INSERT INTO user_role (user_id, role)
SELECT id, 'ROLE_ADMIN' FROM app_user WHERE email = 'stanley@letttechnology.com
ON CONFLICT DO NOTHING;

-- Add ROLE_PRO for a user (replace email)
INSERT INTO user_role (user_id, role)
SELECT id, 'ROLE_PRO' FROM app_user WHERE email = 'user@example.com'
ON CONFLICT DO NOTHING;

-- Remove a role from a user (replace email and role)
DELETE FROM user_role
WHERE user_id = (SELECT id FROM app_user WHERE email = 'user@example.com')
  AND role = 'ROLE_ADMIN';

-- Update tier column to match role (keep in sync)
UPDATE app_user SET tier = 'pro' WHERE email = 'user@example.com';


-- =============================================================================
-- PIPELINE STAGE FLAGS — token_stage_flag
-- Admin flags tokens where gloss output is wrong. Used to drive targeted
-- re-processing and to investigate corpus/sense quality issues.
-- See issues #152 (stage viewer), #153 (flagging), #168 (corpus cleanup).
-- =============================================================================

-- All flagged tokens with all four pipeline stages (base, sense, contextual, final)
-- final = gloss_set_entry (LITE cache) → cluster_gloss_rule → corpus first sense
SELECT
    l.strongs_id,
    vw.surface_form,
    tsf.stage                                            AS flagged_stage,
    tsf.note,
    split_part(corp.short_gloss, ';', 1)                AS base,
    tso.selected_gloss                                   AS sense,
    cg.gloss                                             AS contextual,
    COALESCE(gse.gloss, cgr.gloss,
        split_part(corp.short_gloss, ';', 1))            AS final
FROM token_stage_flag tsf
JOIN verse_word vw ON vw.id = tsf.verse_word_id
JOIN lexeme l      ON l.id  = vw.lexeme_id
LEFT JOIN LATERAL (
    SELECT short_gloss FROM lexeme_meaning
    WHERE lexeme_id = vw.lexeme_id AND source = 'corpus'
    ORDER BY id LIMIT 1
) corp ON true
LEFT JOIN token_sense_override tso ON tso.verse_word_id = vw.id
LEFT JOIN contextual_gloss cg
    ON cg.verse_word_id = vw.id AND cg.language_code = 'en'
LEFT JOIN gloss_set_entry gse
    ON gse.verse_word_id = vw.id
    AND gse.gloss_set_id = (
        SELECT id FROM gloss_set
        WHERE language_code = 'en' AND is_public = true ORDER BY id LIMIT 1
    )
LEFT JOIN cluster_gloss_rule cgr
    ON cgr.lexeme_id = vw.lexeme_id
    AND cgr.morph_key = vw.morph_key
    AND cgr.language_code = 'en'
ORDER BY l.strongs_id, tsf.stage;


-- Corpus short_gloss for all flagged Strong's IDs (joined — not hardcoded)
-- Root cause query: verbose corpus short_gloss feeds the sense disambiguation prompt,
-- causing selected_gloss to store full definitions instead of clean glosses.
-- The LITE final engine masks this for inflected forms (αὐτοῦ→"his") but where
-- LITE has no entry or a weak rule (e.g. πρὸς→"to"), verbose sense leaks to final.
SELECT DISTINCT l.strongs_id, l.lemma, m.short_gloss
FROM lexeme_meaning m
JOIN lexeme l ON l.id = m.lexeme_id
WHERE m.source = 'corpus'
  AND l.strongs_id IN (
      SELECT DISTINCT l2.strongs_id
      FROM token_stage_flag tsf
      JOIN verse_word vw2 ON vw2.id = tsf.verse_word_id
      JOIN lexeme l2 ON l2.id = vw2.lexeme_id
  )
ORDER BY l.strongs_id;


-- Sense overrides for flagged tokens — what the AI selected vs the flag note
SELECT vw.surface_form, l.strongs_id, tso.selected_gloss, tso.confidence,
       tsf.stage AS flag_stage, tsf.note AS flag_note
FROM token_stage_flag tsf
JOIN verse_word vw ON vw.id = tsf.verse_word_id
JOIN lexeme l ON l.id = vw.lexeme_id
LEFT JOIN token_sense_override tso ON tso.verse_word_id = vw.id
ORDER BY l.strongs_id;


-- Clear all flags for a passage once issues are resolved (replace book_id/chapter)
-- DELETE FROM token_stage_flag
-- WHERE verse_word_id IN (
--     SELECT vw.id FROM verse_word vw
--     JOIN verse v ON v.id = vw.verse_id
--     WHERE v.book_id = 43 AND v.chapter = 1
-- );


-- =============================================================================
-- BOOK ID REFERENCE
-- =============================================================================

-- 40 Matthew  41 Mark     42 Luke     43 John     44 Acts
-- 45 Romans   46 1Cor     47 2Cor     48 Gal      49 Eph
-- 50 Phil      51 Col      52 1Thess  53 2Thess   54 1Tim
-- 55 2Tim      56 Titus    57 Phlm    58 Heb      59 Jas
-- 60 1Pet      61 2Pet     62 1John   63 2John    64 3John
-- 65 Jude      66 Rev
