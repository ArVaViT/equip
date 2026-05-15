-- Supabase migration: rls_tighten_write_policies
-- Version: 20260515184418
--
-- CRITICAL SECURITY FIX: several RLS UPDATE policies have qual clauses
-- but no WITH CHECK clause, and authenticated/anon roles hold UPDATE
-- privileges on the underlying tables. The Supabase REST API
-- (PostgREST) is publicly reachable at the project URL with the anon
-- key + a user JWT, so any authenticated user can bypass the FastAPI
-- service layer and write fields they should not control.
--
-- Concrete exploits this closes:
--
--  1. certificates_update_approval (qual permits user_id = auth.uid())
--     A student could PATCH their own certificate row directly via
--     PostgREST and set status='approved' / teacher_approved_by =
--     <own id> -- self-issuing a certificate without ever passing
--     through the teacher_approve + admin_approve gate that backs
--     the FastAPI flow (which uses FOR UPDATE locking).
--
--  2. quiz_attempts_update_own (qual = user_id = auth.uid(), no WITH
--     CHECK). A student could set score / max_score / passed on
--     their own attempt directly, bypassing the entire quiz grading
--     pipeline (including teacher-graded essay flow).
--
--  3. submissions_update_teacher (qual permits either student or
--     teacher). A student could mutate grade / feedback / graded_by
--     on their own assignment_submissions row -- self-grading.
--
--  4. reviews_update_own (qual = user_id = auth.uid(), no WITH CHECK).
--     A user could change user_id to someone else's id while
--     updating, transferring authorship. Rating bounds also aren't
--     enforced at the DB level.
--
-- Fix strategy: the FastAPI backend connects as the ``postgres`` role
-- (RLS-bypass) for all server-mediated writes. Client-side writes via
-- PostgREST are only needed for a tiny set of cases (profile self-
-- updates, file uploads via Storage). For tables where the server is
-- the sole legitimate writer, drop the UPDATE policy entirely and
-- rely on RLS's deny-by-default. For tables where a self-update is
-- legitimate, add the missing WITH CHECK so the post-update row is
-- re-verified.
--
-- Frontend verified safe (2026-05-15 grep over services/*.ts): only
-- ``courses`` count, ``enrollments`` count, ``profiles`` self-update,
-- and storage operations go through the supabase-js client. Auth flows
-- continue to work because they don't touch these tables directly.

-- 1. certificates: server is the only writer for status transitions
DROP POLICY IF EXISTS certificates_update_approval ON public.certificates;

-- 2. quiz_attempts: server is the only writer for scoring/completion
DROP POLICY IF EXISTS quiz_attempts_update_own ON public.quiz_attempts;

-- 3. assignment_submissions: server is the only writer (submit + grade)
DROP POLICY IF EXISTS submissions_update_teacher ON public.assignment_submissions;

-- 4. course_reviews: self-update IS a legitimate flow (the rating
-- editor on the course page calls supabase ... but wait, it actually
-- goes through the FastAPI endpoint POST /reviews/course/{id} which
-- upserts. PostgREST UPDATE is not needed -- drop it too.
DROP POLICY IF EXISTS reviews_update_own ON public.course_reviews;

-- For belt-and-suspenders: revoke UPDATE/DELETE privileges from
-- authenticated/anon on these tables. Even if a future RLS policy
-- re-opens a write path by mistake, the GRANT model still blocks it.
-- (SELECT/INSERT stay intact where needed; the existing INSERT
-- policies still protect the legitimate submission flow.)
REVOKE UPDATE, DELETE ON public.certificates FROM authenticated, anon;
REVOKE UPDATE, DELETE ON public.quiz_attempts FROM authenticated, anon;
REVOKE UPDATE, DELETE ON public.assignment_submissions FROM authenticated, anon;
REVOKE UPDATE ON public.course_reviews FROM authenticated, anon;
-- course_reviews DELETE stays available because the existing
-- reviews_delete_own policy is well-scoped (qual = user_id =
-- auth.uid()) and DELETE has no "with check" foot-gun.
