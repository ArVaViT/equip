-- Add covering indexes for foreign keys that Supabase's performance
-- advisor flagged as unindexed. Background:
--
--   ``enrollments`` runs 100% sequential scans today (2400+ seq_scan,
--   0 idx_scan). The table has only ~20 rows so the planner picks
--   seqscan — but every join through ``user_id`` / ``course_id`` /
--   ``cohort_id`` will pay full-scan cost the moment enrollments grow.
--   The same FK-without-index pattern shows on ``announcements``,
--   ``certificates``, ``chapter_progress``, ``student_grades``.
--
-- All indexes use ``CREATE INDEX IF NOT EXISTS`` so re-application is
-- a no-op (Supabase MCP ``apply_migration`` plus ``supabase db push``
-- can both target this file safely).

-- enrollments — all three FKs are filter-heavy join keys.
CREATE INDEX IF NOT EXISTS ix_enrollments_user_id
    ON enrollments(user_id);
CREATE INDEX IF NOT EXISTS ix_enrollments_course_id
    ON enrollments(course_id);
CREATE INDEX IF NOT EXISTS ix_enrollments_cohort_id
    ON enrollments(cohort_id)
    WHERE cohort_id IS NOT NULL;

-- announcements — list-by-course is the hot query.
CREATE INDEX IF NOT EXISTS ix_announcements_course_id
    ON announcements(course_id);
CREATE INDEX IF NOT EXISTS ix_announcements_created_by
    ON announcements(created_by);

-- certificates — every cert list view filters on at least one of these.
CREATE INDEX IF NOT EXISTS ix_certificates_course_id
    ON certificates(course_id)
    WHERE course_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_certificates_cohort_id
    ON certificates(cohort_id)
    WHERE cohort_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_certificates_teacher_approved_by
    ON certificates(teacher_approved_by)
    WHERE teacher_approved_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_certificates_admin_approved_by
    ON certificates(admin_approved_by)
    WHERE admin_approved_by IS NOT NULL;

-- chapter_progress — progress recompute joins on chapter_id constantly.
CREATE INDEX IF NOT EXISTS ix_chapter_progress_chapter_id
    ON chapter_progress(chapter_id);
CREATE INDEX IF NOT EXISTS ix_chapter_progress_completed_by
    ON chapter_progress(completed_by)
    WHERE completed_by IS NOT NULL;

-- student_grades — gradebook filters on cohort_id.
CREATE INDEX IF NOT EXISTS ix_student_grades_cohort_id
    ON student_grades(cohort_id)
    WHERE cohort_id IS NOT NULL;
