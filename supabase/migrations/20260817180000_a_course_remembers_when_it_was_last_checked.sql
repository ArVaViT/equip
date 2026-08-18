-- Nobody should have to remember which courses still need translating.
--
-- Today the pipeline is entirely reactive: a save fires a hook, a publish
-- fires a hook, and a course that nobody touches is never looked at again. That
-- works while there are three courses and a person who knows all three.
--
-- It stops working twice over. Add a fifth language, and every existing course
-- is suddenly incomplete in it — with no event to notice, because nothing was
-- edited. The documented answer in `app/schemas/locale.py` was step 5: "trigger
-- POST /courses/{id}/translate on every published course, or wait for the next
-- teacher save". That is a person with a list, and it does not survive a
-- thousand courses. And once there are a thousand courses, a single failed
-- pass — a provider outage, a deploy mid-flight — leaves a course quietly
-- half-translated with nothing scheduled to come back for it.
--
-- So the pipeline gets a second half: events for speed, and a sweep for
-- certainty. The sweep needs to know where it left off, which is what this
-- column is. Oldest-checked-first, a few courses per worker tick, around the
-- clock — every course is re-examined on a fixed cycle whether or not anyone
-- touched it.
--
-- NULL means "never checked", and sorts first: a course created before this
-- existed, or created a minute ago by an import that fires no hooks, is the
-- first thing the sweep picks up.

ALTER TABLE public.courses
    ADD COLUMN translations_checked_at TIMESTAMPTZ;

-- The sweep's only query: the least recently examined courses that readers
-- can actually reach. Partial, because drafts are deliberately out of scope —
-- they translate on the teacher's "prepare for publication", not on a timer,
-- so that a course being written all week is not re-translated all week.
CREATE INDEX ix_courses_translations_checked
    ON public.courses (translations_checked_at NULLS FIRST)
    WHERE deleted_at IS NULL AND status IN ('published', 'publishing');

COMMENT ON COLUMN public.courses.translations_checked_at IS
    'When the translation sweep last verified this course has every language. NULL = never; sorts first. Set by the worker, not by editing.';
