-- =============================================================================
-- Interlinear Bible API — Useful Queries
-- Database: interlinear_bible_dev
-- Run: psql -U postgres -d interlinear_bible_dev -f docs/queries.sql
--   or paste individual queries into psql
-- =============================================================================


-- -----------------------------------------------------------------------------
-- BOOK REFERENCE
-- Book IDs follow standard SBL NT numbering (Matthew=40 ... Revelation=66)
-- Verse IDs: book * 1,000,000 + chapter * 1,000 + verse
-- e.g. John 1:1 = 43001001
-- -----------------------------------------------------------------------------

-- List all books with their IDs
SELECT id, name FROM book ORDER BY id;


-- -----------------------------------------------------------------------------
-- PASSAGE / VERSE
-- -----------------------------------------------------------------------------

-- Get all tokens for a chapter with their LITE glosses (John 1)
SELECT vw.word_position, vw.greek_word, l.strongs_id, vw.tense, vw.mood, vw.voice,
       gse.gloss AS lite_gloss
FROM verse_word vw
JOIN lexeme l ON l.id = vw.lexeme_id
LEFT JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id
LEFT JOIN gloss_set gs ON gs.id = gse.gloss_set_id AND gs.name = 'lite_auto'
WHERE vw.verse_id BETWEEN 43001001 AND 43001999
ORDER BY vw.verse_id, vw.word_position;

-- Get LITE glosses for a single verse (John 1:1)
SELECT vw.word_position, vw.greek_word, l.strongs_id, gse.gloss AS lite_gloss
FROM verse_word vw
JOIN lexeme l ON l.id = vw.lexeme_id
LEFT JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id
JOIN gloss_set gs ON gs.id = gse.gloss_set_id AND gs.name = 'lite_auto'
WHERE vw.verse_id = 43001001
ORDER BY vw.word_position;


-- -----------------------------------------------------------------------------
-- LEXEME / CANONICAL WORD
-- -----------------------------------------------------------------------------

-- Look up a lemma by Strong's ID
SELECT l.strongs_id, l.lemma, l.transliteration, l.part_of_speech,
       l.canonical_word, l.is_stative, l.is_deponent, l.is_polysemous,
       lm.short_gloss
FROM lexeme l
LEFT JOIN lexeme_meaning lm ON lm.lexeme_id = l.id AND lm.source = 'corpus'
WHERE l.strongs_id = 'G3056';

-- Check canonical_word for a set of lemmas
SELECT strongs_id, lemma, canonical_word
FROM lexeme
WHERE strongs_id IN ('G3056','G4561','G4151','G26','G5590')
ORDER BY strongs_id;

-- Lexemes missing canonical_word (not yet populated from corpus import)
SELECT strongs_id, lemma FROM lexeme
WHERE canonical_word IS NULL
ORDER BY strongs_id;


-- -----------------------------------------------------------------------------
-- LITE GLOSSES (gloss_set_entry)
-- -----------------------------------------------------------------------------

-- Count total LITE glosses
SELECT COUNT(*) FROM gloss_set_entry gse
JOIN gloss_set gs ON gs.id = gse.gloss_set_id AND gs.name = 'lite_auto';

-- Check LITE gloss for a specific lemma across all its tokens
SELECT vw.verse_id, vw.tense, vw.mood, vw.voice, gse.gloss AS lite_gloss
FROM verse_word vw
JOIN lexeme l ON l.id = vw.lexeme_id
JOIN gloss_set_entry gse ON gse.verse_word_id = vw.id
JOIN gloss_set gs ON gs.id = gse.gloss_set_id AND gs.name = 'lite_auto'
WHERE l.strongs_id = 'G1011'
ORDER BY vw.tense, vw.mood, vw.voice
LIMIT 20;


-- -----------------------------------------------------------------------------
-- IRREGULAR VERB ENRICHMENT (Groq AI corrections)
-- -----------------------------------------------------------------------------

-- View all stored Groq corrections
SELECT strongs_id, tense, mood, voice_class, english, source, created_at
FROM irregular_verb_form
ORDER BY strongs_id, tense, mood;

-- Count corrections by source
SELECT source, COUNT(*) FROM irregular_verb_form GROUP BY source;

-- How many verb combinations still need enrichment
SELECT COUNT(DISTINCT (l.strongs_id, vw.tense, vw.mood, vw.voice))
FROM verse_word vw
JOIN lexeme l ON vw.lexeme_id = l.id
WHERE vw.pos_code = 'V'
  AND vw.tense IN ('Aorist','Perfect','Pluperfect')
  AND vw.mood IN ('Indicative','Infinitive','Participle','Subjunctive','Optative')
  AND l.strongs_id NOT IN (
    'G1510','G2064','G3004','G3708','G2192','G1096','G1492','G1080',
    'G1097','G3860','G2309','G1014','G1410','G1163','G4100','G25',
    'G5343','G668','G1628','G2703','G991','G4238','G4160','G5302',
    'G4098','G1797','G3539'
  )
  AND l.strongs_id NOT IN (
    SELECT DISTINCT strongs_id FROM irregular_verb_form
  );

-- Delete all Groq-sourced corrections (to re-run enrichment clean)
-- DELETE FROM irregular_verb_form WHERE source = 'groq';


-- -----------------------------------------------------------------------------
-- HANDLER C — SENSE DISAMBIGUATION (token_sense_override)
-- -----------------------------------------------------------------------------

-- View AI sense decisions for polysemous tokens
SELECT vw.verse_id, l.strongs_id, l.lemma, tso.sense_index, tso.confidence
FROM token_sense_override tso
JOIN verse_word vw ON vw.id = tso.verse_word_id
JOIN lexeme l ON l.id = vw.lexeme_id
ORDER BY l.strongs_id, vw.verse_id
LIMIT 50;

-- Low-confidence decisions needing human review
SELECT vw.verse_id, l.strongs_id, l.lemma, tso.sense_index, tso.confidence
FROM token_sense_override tso
JOIN verse_word vw ON vw.id = tso.verse_word_id
JOIN lexeme l ON l.id = vw.lexeme_id
WHERE tso.confidence = 'low'
ORDER BY l.strongs_id;

-- Sense options for a polysemous lemma
SELECT sense_index, gloss, sense_type FROM lexeme_sense
WHERE lexeme_id = (SELECT id FROM lexeme WHERE strongs_id = 'G4151')
ORDER BY sense_index;


-- -----------------------------------------------------------------------------
-- WORD INSIGHT (lexeme_insight)
-- -----------------------------------------------------------------------------

-- Check which lemmas have pre-generated insights
SELECT strongs_id, LEFT(insight, 80) AS preview, created_at
FROM lexeme_insight
ORDER BY created_at DESC
LIMIT 20;

-- Count insights generated
SELECT COUNT(*) FROM lexeme_insight;


-- -----------------------------------------------------------------------------
-- CORPUS / LEXICON
-- -----------------------------------------------------------------------------

-- Check corpus gloss for a lemma
SELECT lm.short_gloss, lm.full_definition
FROM lexeme_meaning lm
JOIN lexeme l ON l.id = lm.lexeme_id
WHERE l.strongs_id = 'G3056' AND lm.source = 'corpus';

-- Count meanings by source
SELECT source, COUNT(*) FROM lexeme_meaning GROUP BY source ORDER BY COUNT(*) DESC;

-- Lexemes with all source coverage
SELECT l.strongs_id, l.lemma,
       BOOL_OR(lm.source = 'corpus')    AS has_corpus,
       BOOL_OR(lm.source = 'lsj')       AS has_lsj,
       BOOL_OR(lm.source = 'thayer')    AS has_thayer,
FROM lexeme l
LEFT JOIN lexeme_meaning lm ON lm.lexeme_id = l.id
GROUP BY l.strongs_id, l.lemma
ORDER BY l.strongs_id
LIMIT 20;


-- -----------------------------------------------------------------------------
-- FLYWAY MIGRATION HISTORY
-- -----------------------------------------------------------------------------

SELECT version, description, success, installed_on
FROM flyway_schema_history
ORDER BY installed_rank;
