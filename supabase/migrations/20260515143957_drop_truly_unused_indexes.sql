-- Drop four indexes the 2026-05-15 DB audit identified as truly unused —
-- no current query hits them, no future query would benefit, and they
-- aren't backing a UNIQUE constraint or a FK lookup pattern.
--
-- Pre-flight: each was checked against pg_stat_user_indexes (idx_scan=0
-- since migrate-from-prior-cleanup on 2026-05-13) AND against the app
-- query patterns under backend/app/.
--
-- The OTHER 27 indexes the advisor flagged stay — they back FK joins
-- ("certs for cohort X", audit-by-user, gradebook by graded_by, etc.)
-- or were added < 7 days ago for queries that haven't gained scan
-- volume yet (ix_courses_status_created_at, ix_quiz_answers_attempt_question).

-- 1. modules.deleted_at — partial index WHERE deleted_at IS NOT NULL.
--    Every Module query in the app filters Module.deleted_at IS NULL
--    (active rows). The partial points the wrong way: it indexes the
--    trashed rows we never look up. Unused since creation.
DROP INDEX IF EXISTS public.ix_modules_deleted_at;


-- 2. chapters.deleted_at — same shape, same direction problem.
--    All Chapter queries filter deleted_at IS NULL. No trash-recovery
--    workflow currently exists.
DROP INDEX IF EXISTS public.ix_chapters_deleted_at;


-- 3. notifications.created_at — standalone single-column DESC index.
--    Every notifications query in the app is user-scoped first
--    (Notification.user_id == current_user.id) and then ordered by
--    created_at. The composite ix_notifications_user_unread on
--    (user_id, is_read) handles the filter; the planner does an
--    in-memory sort over the small per-user result set. A global
--    created_at index has no user-scoped query that could use it.
DROP INDEX IF EXISTS public.ix_notifications_created_at;


-- 4. course_events.event_date — never referenced in a WHERE clause.
--    CourseEvent rows are loaded by course_id (ix_course_events_course_id
--    covers that) and then sorted in Python via
--    `events.sort(key=lambda e: e.event_date)` in calendar.py.
--    No SQL ORDER BY event_date exists; index does no work.
DROP INDEX IF EXISTS public.ix_course_events_event_date;
