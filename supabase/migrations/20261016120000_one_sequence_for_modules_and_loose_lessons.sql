-- One sequence for modules and the lessons outside them.
--
-- The decision (2026-10-16)
-- =========================
-- One order for everybody, the one the teacher set. A lesson outside a
-- module stays exactly where the teacher put it — between two modules,
-- before the first, after the last — and the student reads the same
-- sequence the teacher arranged.
--
-- The new reading rule (backend/app/services/course_structure.py and
-- frontend/src/lib/courseStructure.ts): a module and a lesson in no
-- module each take a place in one sequence, numbered in ONE shared space
-- by their own order_index — modules.order_index and a loose
-- chapters.order_index are compared with each other directly. A module's
-- lessons run under it, ordered by their own order_index, which is never
-- compared with anything outside the module.
--
-- What it replaces
-- ================
-- Until now modules.order_index ran 0..k in a space of its own, and a
-- loose lesson was placed by comparing its number with the number of the
-- first lesson of each module (build_spine's "start" of a heading). That
-- rule lived only on the server — the student's and the teacher's screens
-- swept loose lessons to the tail — and it broke whenever a module's
-- lessons were renumbered, and could not put an empty module after a
-- loose lesson at all.
--
-- What this file does
-- ===================
-- For every course that has at least one live lesson outside a module,
-- renumbers its live modules and live lessons with one counter, in the
-- order the server reads the course today (the previous build_spine
-- rule, replicated below): a module takes the next number, its lessons
-- the numbers after it, a loose lesson the next number. No lesson
-- changes place relative to that reading; only the numbers change.
--
-- Courses with no loose lesson are not touched: for them the new rule and
-- the old one are the same (modules by their own numbers, lessons inside
-- each module by theirs).
--
-- Soft-deleted rows keep their numbers — they take no place in the
-- sequence; restore_chapter re-seats a restored lesson at the tail if its
-- old number is taken.
--
-- Re-runnable: the reading rule changes meaning with this file, so the
-- renumbering must happen exactly once. The column comment set at the end
-- is the marker; a second run sees it and does nothing.
--
-- Order of deployment: apply this file first, then deploy the code. The
-- old code reads the renumbered rows the same way (the numbers are
-- monotonic over the course), so nothing moves in between.

DO $migration$
BEGIN
    IF COALESCE(
        col_description(
            'public.modules'::regclass,
            (SELECT attnum FROM pg_attribute
              WHERE attrelid = 'public.modules'::regclass AND attname = 'order_index')
        ),
        ''
    ) LIKE 'This module''s place in its course%' THEN
        RAISE NOTICE 'one_sequence_for_modules_and_loose_lessons: already applied, nothing to do';
        RETURN;
    END IF;

    WITH live_modules AS (
        SELECT id, course_id, order_index
          FROM public.modules
         WHERE deleted_at IS NULL
    ),
    live_chapters AS (
        -- A lesson naming a binned (or foreign) module is loose: that is
        -- how every reader treats it.
        SELECT c.id, c.course_id, c.order_index, lm.id AS module_id
          FROM public.chapters AS c
          LEFT JOIN live_modules AS lm
                 ON lm.id = c.module_id
                AND lm.course_id = c.course_id
         WHERE c.deleted_at IS NULL
    ),
    affected AS (
        SELECT DISTINCT course_id FROM live_chapters WHERE module_id IS NULL
    ),
    firsts AS (
        SELECT module_id, MIN(order_index) AS first_member
          FROM live_chapters
         WHERE module_id IS NOT NULL
         GROUP BY module_id
    ),
    heads AS (
        -- The old rule: headings by their own number; each heading
        -- "starts" at the running maximum of its lessons' first numbers
        -- (an empty heading inherits the start before it, -1 at the top).
        SELECT lm.id,
               lm.course_id,
               ROW_NUMBER() OVER w - 1 AS pos,
               GREATEST(-1, COALESCE(MAX(f.first_member) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), -1))
                   AS start
          FROM live_modules AS lm
          JOIN affected AS a ON a.course_id = lm.course_id
          LEFT JOIN firsts AS f ON f.module_id = lm.id
        WINDOW w AS (PARTITION BY lm.course_id ORDER BY lm.order_index, lm.id COLLATE "C")
    ),
    places AS (
        -- slot: which heading a row sits at (a loose lesson sits before
        -- the first heading that starts above its number); kind 0 = loose
        -- before that heading, 1 = the heading and its lessons.
        SELECT h.course_id, 'module'::text AS entity, h.id, h.pos AS slot, 1 AS kind, 0 AS sub, 0 AS ord, h.id AS tie
          FROM heads AS h
        UNION ALL
        SELECT c.course_id, 'chapter', c.id, h.pos, 1, 1, c.order_index, c.id
          FROM live_chapters AS c
          JOIN heads AS h ON h.id = c.module_id
        UNION ALL
        SELECT c.course_id, 'chapter', c.id,
               (SELECT COUNT(*) FROM heads AS h WHERE h.course_id = c.course_id AND h.start <= c.order_index),
               0, 0, c.order_index, c.id
          FROM live_chapters AS c
          JOIN affected AS a ON a.course_id = c.course_id
         WHERE c.module_id IS NULL
    ),
    numbered AS (
        SELECT entity, id,
               ROW_NUMBER() OVER (PARTITION BY course_id ORDER BY slot, kind, sub, ord, tie COLLATE "C") - 1 AS new_index
          FROM places
    ),
    renumbered_modules AS (
        UPDATE public.modules AS m
           SET order_index = n.new_index
          FROM numbered AS n
         WHERE n.entity = 'module'
           AND n.id = m.id
           AND m.order_index IS DISTINCT FROM n.new_index
        RETURNING m.id
    )
    UPDATE public.chapters AS c
       SET order_index = n.new_index
      FROM numbered AS n
     WHERE n.entity = 'chapter'
       AND n.id = c.id
       AND c.order_index IS DISTINCT FROM n.new_index;

    COMMENT ON COLUMN public.modules.order_index IS
        'This module''s place in its course, in the one sequence it shares with the course''s lessons that sit in no module (compared directly with their chapters.order_index). See app/services/course_structure.build_spine.';
    COMMENT ON COLUMN public.chapters.order_index IS
        'For a lesson in no module: its place in the course, in the sequence it shares with modules.order_index. For a lesson in a module: its order among that module''s lessons only. See app/services/course_structure.build_spine.';
END
$migration$;
