-- =====================================================================
-- Phase 5f — drop the entire quiz-tree text columns:
--   * ``quizzes.title`` and ``quizzes.description``
--   * ``quiz_questions.question_text``
--   * ``quiz_options.option_text``
--
-- After Phase 3 backfill, all four texts are mirrored in
-- ``content_versions`` keyed by (entity_type, entity_id, field, locale)
-- which becomes the single source of truth.
--
-- The read path uses ``fetch_cv_entity_texts_with_fallback`` with a
-- three-tier locale resolution (display → source → any-locale).
-- The write path in ``api/v1/quizzes/crud.py`` passes ``texts={...}``
-- dicts to ``dual_write_entity_content`` for each entity in the tree.
--
-- Irreversibility: column data is gone after this migration. A
-- pre-merge dump is the rollback artefact.
-- =====================================================================

ALTER TABLE quizzes DROP COLUMN IF EXISTS title;
ALTER TABLE quizzes DROP COLUMN IF EXISTS description;
ALTER TABLE quiz_questions DROP COLUMN IF EXISTS question_text;
ALTER TABLE quiz_options DROP COLUMN IF EXISTS option_text;
