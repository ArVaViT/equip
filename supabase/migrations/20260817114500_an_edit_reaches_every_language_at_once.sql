-- An edit reaches every language at once, or it reaches nobody yet.
--
-- What an edit did until now
-- ==========================
-- A teacher fixes a sentence in a published course. The new text becomes the
-- active `content_versions` row for the language they wrote it in, and it is
-- served immediately. The other three languages keep the translation of the
-- OLD sentence — correct, checked, and now describing something the course no
-- longer says — until the pipeline catches up, field by field.
--
-- So for a window that lasts as long as the queue does, the same lesson says
-- two different things depending on which language you chose. The Russian
-- group reads the correction; the German group reads what it replaced. If the
-- edit changed a quiz question, the two groups are answering different
-- questions and being graded on the same key.
--
-- 20260814214109 named this and accepted it deliberately: the alternative it
-- was weighing was pulling the whole course out of the catalog on every typo
-- fix, which is worse. But those are not the only two options, and this is the
-- third: hold the edit, translate it, and let it land everywhere in one step.
--
-- Where an unreleased edit lives
-- ==============================
-- Not in `content_versions`. Every reader of that table filters on
-- `superseded_by IS NULL AND status = 'ok'`, in thirty-one places, and an edit
-- that must not be served yet has no business being one query away from being
-- served. A `stage` column would have made every one of those places a
-- potential leak, forever, including the ones written next year.
--
-- A separate table cannot leak into a query that does not name it. This one
-- holds the whole in-flight edit — the teacher's new text AND its translations
-- as they arrive — and stays completely invisible to the reading path. When
-- the last language is in and checked, `promote` copies the rows into
-- `content_versions` through the ordinary `record_human_version` /
-- `record_mt_version` helpers, so supersession, provenance, and history work
-- exactly as they always have, and deletes them here.
--
-- Consequently a row in this table means one thing only: an edit that is not
-- ready. The table is empty when the platform is at rest.
--
-- Granularity: the field
-- ======================
-- Promotion is per (entity, field), not per course. A teacher who fixes one
-- paragraph should not have that paragraph held back until an unrelated edit
-- to chapter nine is also translated — and a course-wide gate means one
-- permanently-failing field freezes every other edit behind it. Per field, the
-- guarantee a reader actually needs still holds: nobody ever sees a sentence
-- whose translations describe a different sentence.
--
-- Not for drafts
-- ==============
-- A course in 'draft' or 'publishing' has no students reading it, so there is
-- nothing to protect and edits go straight to `content_versions` as before.
-- This table only ever fills for a course that is 'published'.

CREATE TABLE public.staged_content_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Same polymorphic key as content_versions: no FK is possible because
    -- entity_id points at whichever of sixteen tables entity_type names.
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    field TEXT NOT NULL,
    locale TEXT NOT NULL,

    -- The course this edit belongs to. Denormalised deliberately: the
    -- staging table is read course-at-a-time (what is this course waiting on?
    -- what can be promoted? what does the teacher's panel show?), and without
    -- this every one of those questions would mean walking the course tree
    -- first just to build an IN-list of entity ids. It also buys a real FK,
    -- which the polymorphic entity key cannot have — deleting a course takes
    -- its unreleased edits with it instead of orphaning them.
    course_id CHARACTER VARYING NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,

    text TEXT NOT NULL,

    -- 'human' is the edit itself, in the language it was written in. 'mt' is a
    -- translation of that edit, waiting with it. Exactly one 'human' row per
    -- (entity, field) is expected; the rest are its translations.
    origin TEXT NOT NULL CHECK (origin IN ('human', 'mt')),

    -- Same lifecycle as content_versions.status, and the same meaning:
    -- 'needs_review' is text that came back and failed its structural check.
    -- A field is only promoted when every locale is 'ok'.
    status TEXT NOT NULL DEFAULT 'ok'
        CHECK (status IN ('ok', 'needs_review', 'failed', 'failed_permanent')),
    review_reason TEXT,

    -- The hash of the human text this translation was made from. It is what
    -- makes a second edit safe: translations of the previous version no longer
    -- match, so they cannot be promoted alongside the new text.
    source_hash TEXT,
    source_locale TEXT,

    authored_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per (entity, field, locale). Unlike content_versions there is no
-- history here and no supersession: a re-edit overwrites, because an
-- unreleased draft of an edit has no readers whose view must stay stable.
CREATE UNIQUE INDEX uniq_staged_content_versions_key
    ON public.staged_content_versions (entity_type, entity_id, field, locale);

-- The pipeline's working query: "what is staged for this entity?"
CREATE INDEX ix_staged_content_versions_entity
    ON public.staged_content_versions (entity_type, entity_id);

-- Everything the worker, the promotion sweep, and the teacher's "waiting to
-- go out" panel ask: "what is in flight for this course?"
CREATE INDEX ix_staged_content_versions_course
    ON public.staged_content_versions (course_id);

-- The promotion sweep's query: "which fields might be ready?" Ordered by age
-- so the oldest edit — the one a teacher has been waiting on — goes first.
CREATE INDEX ix_staged_content_versions_created
    ON public.staged_content_versions (created_at);

-- Grants are the boundary, RLS with zero policies is the backstop — the same
-- posture as every other table here (see 20260611200000). The backend connects
-- as the owner and is unaffected. Nothing client-side has any business reading
-- unreleased text: that is the entire point of the table.
REVOKE ALL ON public.staged_content_versions FROM anon, authenticated;
ALTER TABLE public.staged_content_versions ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.staged_content_versions IS
    'An edit to a published course that is not ready to be seen: the new text plus its translations, held together until every language is present and checked, then promoted into content_versions in one step and deleted from here. Empty when nothing is in flight.';
