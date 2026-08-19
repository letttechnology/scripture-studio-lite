-- =============================================================================
-- inspect_sense_selections.sql
--
-- PURPOSE: Verify Handler C (SenseSelectionService) sense disambiguation results.
--   Shows every token for a given lexeme (Strong's ID) with:
--     - Book/chapter/verse reference
--     - Greek surface form
--     - Which sense was AI-selected and its meaning
--     - The full interlinear verse (English glosses from gloss_set_entry)
--       with the target word wrapped in (parentheses) for quick visual review
--
-- HOW TO USE:
--   1. Run POST /admin/import-sense-selections?strongsId=G4983 (or without filter for all)
--   2. Run POST /admin/regenerate-lite-glosses  (propagates sense choices into gloss_set_entry)
--   3. Run this query — change the strongs_id filter and book/chapter as needed
--
-- READING THE OUTPUT:
--   - ref:           Book chapter:verse (e.g. "1 Corinthians 6:13")
--   - greek:         The Greek surface form of this occurrence
--   - sense_meaning: The sense Handler C selected — [sense N] + its definition
--   - verse:         Full word-for-word interlinear; target word shown as (gloss)
--                    Read left-to-right to judge whether the selected sense fits context
--
-- NULL in sense_meaning means Handler C has not yet run for this token.
-- =============================================================================

SELECT
    b.name || ' ' || v.chapter || ':' || v.verse_num         AS ref,
    vw.surface_form                                           AS greek,
    '[sense ' || tso.sense_index::text || '] ' || ls.gloss   AS sense_meaning,
    va.verse
FROM verse v
JOIN book b         ON b.id         = v.book_id
JOIN verse_word vw  ON vw.verse_id  = v.id
JOIN lexeme l       ON vw.lexeme_id = l.id
LEFT JOIN token_sense_override tso ON tso.verse_word_id = vw.id
LEFT JOIN lexeme_sense ls
    ON  ls.lexeme_id   = l.id
    AND ls.sense_index = tso.sense_index
JOIN (
    SELECT
        vw2.verse_id,
        string_agg(
            CASE WHEN l2.strongs_id = 'G4983'     -- ← change to match your target below
                 THEN '(' || COALESCE(gse2.gloss, vw2.english_gloss, '?') || ')'
                 ELSE COALESCE(gse2.gloss, vw2.english_gloss, '?')
            END,
            ' ' ORDER BY vw2.position
        ) AS verse
    FROM verse_word vw2
    JOIN lexeme l2 ON vw2.lexeme_id = l2.id
    LEFT JOIN gloss_set_entry gse2
        ON  gse2.verse_word_id = vw2.id
        AND gse2.gloss_set_id  = (SELECT id FROM gloss_set WHERE name = 'lite_auto')
    GROUP BY vw2.verse_id
) va ON va.verse_id = v.id
WHERE v.book_id    = 46          -- 46 = 1 Corinthians; change as needed
  AND v.chapter    = 6           -- change as needed; remove line for whole book
  AND l.strongs_id = 'G4983'    -- σῶμα (body); change to any Strong's ID
ORDER BY v.chapter, v.verse_num, vw.position;
