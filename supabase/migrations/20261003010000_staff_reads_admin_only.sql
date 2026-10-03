-- Staff reads through PostgREST: platform admins only (2026-10-03).
--
-- Seven SELECT policies let any account with role teacher OR admin read every
-- student's rows — submissions, answers, attempts, grades, progress,
-- enrollments — across every course and organization, straight through
-- PostgREST with the public key. The API already scopes the same data to the
-- teacher's own courses (verify_course_owner / verify_chapter_owner) and
-- reads it as the table owner, so RLS never applied there; the browser reads
-- none of these tables except an admin's enrollment count. The teacher arm
-- was a door nothing walked through, open to every teacher of every school.
--
-- Students keep their own rows; platform staff (is_platform_staff()) keep
-- everything, which the admin overview's enrollment count needs.
begin;

drop policy if exists chapter_progress_select on public.chapter_progress;
create policy chapter_progress_select on public.chapter_progress for select to authenticated
  using (user_id = (select auth.uid()) or public.is_platform_staff());

drop policy if exists enrollments_select on public.enrollments;
create policy enrollments_select on public.enrollments for select to authenticated
  using (user_id = (select auth.uid()) or public.is_platform_staff());

drop policy if exists quiz_attempts_select_own on public.quiz_attempts;
create policy quiz_attempts_select_own on public.quiz_attempts for select to authenticated
  using (user_id = (select auth.uid()) or public.is_platform_staff());

drop policy if exists quiz_extra_attempts_select_own on public.quiz_extra_attempts;
create policy quiz_extra_attempts_select_own on public.quiz_extra_attempts for select to authenticated
  using (user_id = (select auth.uid()) or public.is_platform_staff());

drop policy if exists student_grades_select on public.student_grades;
create policy student_grades_select on public.student_grades for select to authenticated
  using (student_id = (select auth.uid()) or public.is_platform_staff());

drop policy if exists submissions_select_own_or_teacher on public.assignment_submissions;
create policy submissions_select_own_or_teacher on public.assignment_submissions for select to authenticated
  using (student_id = (select auth.uid()) or public.is_platform_staff());

drop policy if exists quiz_answers_select_own on public.quiz_answers;
create policy quiz_answers_select_own on public.quiz_answers for select to authenticated
  using (
    exists (select 1 from public.quiz_attempts qa where qa.id = quiz_answers.attempt_id and qa.user_id = (select auth.uid()))
    or public.is_platform_staff()
  );

commit;
