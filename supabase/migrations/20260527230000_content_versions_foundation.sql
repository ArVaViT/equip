-- =====================================================================
-- ``content_versions`` — single multi-locale content store.
--
-- Replaces the dual-model "text on entity columns (source) + overlay
-- in content_translations (translations)" with a symmetric one-table
-- design: every (entity, field, locale) is its own first-class row.
--
-- Design principles
--   * No language is privileged. ``locale`` is just a column, not a
--     CHECK constraint — adding a new language is INSERT, not DDL.
--   * Version history via ``superseded_by``: updates never destroy
--     prior text. Only the active version per (entity, field, locale)
--     has ``superseded_by IS NULL``; the partial unique index
--     ``uniq_content_versions_active`` enforces exactly one.
--   * ``origin='human'`` rows are authored by teachers / admins;
--     ``origin='mt'`` rows are machine-translated and remember their
--     source via ``source_version_id`` for precise cascade
--     invalidation when the source human row updates.
--   * ``status`` tracks failure state for the MT path; human rows are
--     always ``ok`` by construction.
--
-- This table is created EMPTY. Phase 1 begins dual-writes into it
-- from every entity write path. Phase 2 begins dual-reads. Phase 3
-- backfills existing entity columns + content_translations into here.
-- Phase 4 flips reads exclusive. Phase 5 drops entity text columns
-- and the legacy content_translations table.
-- =====================================================================

CREATE TABLE content_versions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Polymorphic anchor: the entity this content belongs to.
  -- ``entity_type`` deliberately has no CHECK constraint here so a
  -- future new translatable entity type (a new content category we
  -- haven't shipped yet) needs no migration. Validation lives in the
  -- Pydantic Literal mirror at the API edge.
  entity_type         text NOT NULL,
  entity_id           text NOT NULL,
  field               text NOT NULL,

  -- The locale this row's text is written in. No CHECK — adding a new
  -- language is a zero-DDL operation. Pydantic Literal is the single
  -- source of truth at the API edge.
  locale              text NOT NULL,

  text                text NOT NULL,

  -- ``human`` rows are authored by teachers (or admins via overrides)
  -- and are never overwritten by the MT pipeline. ``mt`` rows are
  -- machine translations the pipeline owns end to end.
  origin              text NOT NULL CHECK (origin IN ('human', 'mt')),

  -- MT lifecycle status. ``human`` rows are always 'ok' by
  -- construction (they have no failure mode — they're typed in).
  -- ``failed`` rows retry on the next pipeline pass up to a cap;
  -- ``failed_permanent`` rows stop retrying and need manual review.
  status              text NOT NULL DEFAULT 'ok'
                      CHECK (status IN ('ok', 'failed', 'failed_permanent')),

  -- MT-only provenance: hash of (source_text + source_locale) at
  -- translation time. Allows the orchestrator to short-circuit on
  -- unchanged sources (``status='ok'`` + matching hash → skip
  -- Gemini). NULL for human rows.
  source_hash         text,

  -- MT-only: the locale of the source this row was translated FROM.
  -- Lets the resolver and the cascade-invalidation logic answer
  -- "given the EN human source changed, which MT rows need
  -- re-translation?" without re-detecting language at runtime.
  source_locale       text,

  -- MT-only FK: the exact version row this MT was translated from.
  -- When a human row supersedes itself (teacher rewrites), every MT
  -- row with ``source_version_id`` pointing at the superseded human
  -- version is now stale and can be cascaded precisely (vs the
  -- current ``purge_course_translations`` blunderbuss that nukes
  -- everything for the course). NULL for human rows and for legacy
  -- MT rows backfilled before this FK was available.
  source_version_id   uuid REFERENCES content_versions(id) ON DELETE SET NULL,

  -- The human who wrote this version. NULL for MT rows and for human
  -- rows whose author was deleted from the platform.
  authored_by         uuid REFERENCES profiles(id) ON DELETE SET NULL,

  -- How many translation attempts this MT row has burned. Resets to
  -- 0 implicitly when a row goes back to ``ok``. Always 0 for human
  -- rows.
  attempts            int NOT NULL DEFAULT 0 CHECK (attempts >= 0),

  -- Version history pointer. When a row is superseded, the new
  -- version sets the old version's ``superseded_by`` to its own id.
  -- The old row stays in the table forever — translation history
  -- never gets destroyed, only marked inactive.
  superseded_by       uuid REFERENCES content_versions(id) ON DELETE SET NULL,

  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Active uniqueness: exactly ONE current version per
-- (entity, field, locale). Superseded rows are excluded so a teacher
-- can supersede a translation without violating uniqueness.
CREATE UNIQUE INDEX uniq_content_versions_active
  ON content_versions (entity_type, entity_id, field, locale)
  WHERE superseded_by IS NULL;

-- Hot-path read index: "give me every current version for this
-- entity, in this locale". The resolver hits this on every
-- chapter/course render — needs to be a partial index that already
-- filters out superseded + failed rows so the planner doesn't even
-- consider them.
CREATE INDEX ix_content_versions_active_lookup
  ON content_versions (entity_type, entity_id, locale)
  WHERE superseded_by IS NULL AND status = 'ok';

-- Per-entity bulk index: needed for the "delete all rows for this
-- course" administrative purge and for the cascade-invalidation
-- query "find every MT row sourced from this human row's chain".
CREATE INDEX ix_content_versions_entity
  ON content_versions (entity_type, entity_id);

-- MT cascade index: when a human row updates, find every MT row
-- that was derived from it (or from any of its prior versions).
CREATE INDEX ix_content_versions_source_version
  ON content_versions (source_version_id)
  WHERE source_version_id IS NOT NULL;

-- ``updated_at`` auto-bump trigger — matches the convention used
-- everywhere else in the schema.
CREATE OR REPLACE FUNCTION content_versions_set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER content_versions_updated_at
  BEFORE UPDATE ON content_versions
  FOR EACH ROW
  EXECUTE FUNCTION content_versions_set_updated_at();

-- RLS — service role has full access (backend uses it for writes);
-- authenticated users can read any ok+active row (resolve path needs
-- this for student-facing translations). No direct INSERT/UPDATE from
-- end users — every mutation flows through the backend's typed write
-- helpers which use the service role.
ALTER TABLE content_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY content_versions_service_role_all
  ON content_versions
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY content_versions_authenticated_read
  ON content_versions
  FOR SELECT
  TO authenticated
  USING (status = 'ok' AND superseded_by IS NULL);

CREATE POLICY content_versions_anon_read
  ON content_versions
  FOR SELECT
  TO anon
  USING (status = 'ok' AND superseded_by IS NULL);
