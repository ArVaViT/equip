# ADR-010: Cohorts as top-level admin entities

- **Status**: Accepted (2026-05-13)
- **Date**: 2026-05-13
- **Decision-makers**: @ArVaViT (owner), @claude (Equip agent)

## Context

The first cohort prototype (pre-2026-05-13) attached a cohort to a
single course: each course owned its cohorts, and teachers managed
their cohorts inside their course editor. This shape worked for the
first user (one school, one teacher per course), but broke as soon
as we tried to model real Bible schools:

1. **Cross-course cohorts are the norm.** A class of students taking
   "Genesis Overview" together also takes "Pastoral Theology" with
   the same instructor in the next semester. A course-scoped cohort
   model forces creating two parallel cohorts with the same roster.

2. **Teachers do not own cohort membership.** In every nonprofit
   Bible school we surveyed, the **director / registrar** decides
   who is in which cohort and which courses that cohort takes that
   term. Teachers handle the academic content; admins handle
   scheduling and rosters. A teacher-scoped UI made the wrong person
   responsible for student enrollment.

3. **Public courses and institute courses need different gates.** A
   public discipleship course should accept solo self-enrollment. A
   credentialed program course should accept enrollment **only**
   through a cohort the registrar created. The cohort model had no
   way to express "this course is invitation-only".

## Decision

Cohorts become **top-level admin entities**.

- A cohort has its own table (`cohorts`) with `name`, `start_date`,
  `end_date`, `enrollment_start/end`, `max_students`, `status`
  (`upcoming → active → completed`, forward-only).
- The relationship to courses is **many-to-many** through a junction
  table `cohort_courses(cohort_id, course_id)`. A single cohort
  can span any number of courses; a single course can be taught to
  any number of cohorts.
- Student membership is the existing `enrollments` table extended
  with a nullable `cohort_id`. A student in a cohort that includes
  N courses gets N enrollment rows that all share the same
  `cohort_id`.
- All cohort write surfaces (`POST /cohorts`, `PATCH /cohorts/{id}`,
  `POST /cohorts/{id}/courses`, `POST /cohorts/{id}/students`, etc.)
  require `require_admin`. Teachers get a **read-only** filter (e.g.
  gradebook "show cohort X") and the public catalog gets a
  read-only "enroll into cohort Y" dropdown.
- Courses gain an `access_mode` column with values `public` and
  `institute`. Solo self-enrollment (`POST /courses/{id}/enroll`
  without a `cohort_id`) is gated: `institute` 403s; `public`
  applies the existing enrollment-window check. Cohort-based
  enrollment works for either access mode — joining a cohort is
  the director's intent regardless of access mode.
- The legacy course-scoped create endpoint
  (`POST /cohorts/course/{id}` from before this ADR) was deleted.

## Consequences

### Easier

- One cohort across multiple courses: the registrar creates a cohort
  once and attaches as many courses as the semester needs.
- Clear authorship line: admin owns rosters, teacher owns content.
- The public catalog enroll dialog gets a clean dropdown of "join
  this course as part of cohort X" with no special-casing for
  teacher-scoped cohorts.
- Soft-delete and undo flows simplify — a cohort has its own
  lifecycle independent of its courses.

### Harder

- The `enrollments` table now serves both solo (cohort_id IS NULL)
  and cohort (cohort_id IS NOT NULL) students. Every query against
  it must consider both shapes. We accepted this rather than
  splitting into two tables because the surface area (grades,
  progress, certificates) attaches to enrollment, not to membership
  type.
- Forward-only status (`upcoming → active → completed`) is enforced
  at the route layer because the schema is reused by the
  `POST /cohorts/{id}/complete` endpoint where "completed" is the
  legitimate target. See `update_cohort` in
  `backend/app/api/v1/cohorts.py`.
- The frontend admin section now has a cohort CRUD UI that did not
  exist before. See `frontend/src/pages/Admin/cohorts/`.

### Explicitly deferred

- **Cohort templates.** A "Spring template" that pre-seeds a new
  cohort with the same course set as last spring's would be useful
  but not blocking. Pattern: clone-from-existing.
- **Bulk roster import.** CSV upload to add 30 students at once.
  The single-student endpoint is the building block; admin UI can
  layer a CSV parser on top without API changes.
- **Cohort-scoped announcements.** Today announcements are
  course-scoped or global. A cohort-scoped variant would let a
  registrar notify just one cohort's students; not implemented yet.

## Alternatives considered

### A. Keep cohorts course-scoped, add cross-course "groups"

Build a separate "group" abstraction on top of course-scoped cohorts.
Rejected: doubles the conceptual surface and the database schema for
the same outcome.

### B. Use Supabase RLS groups instead of a `cohorts` table

Lean on a Supabase auth feature rather than rolling our own table.
Rejected: RLS groups don't carry the date-window / capacity / status
semantics we need; modelling them inside Supabase would require
storing the same data in two places.

### C. Soft-link cohorts through enrollment metadata only

Don't create a dedicated `cohorts` table — express "cohort
membership" as a string tag on `enrollments`. Rejected: every
cohort-level operation (capacity, date windows, status transitions)
would degrade to a tag-based scan. The dedicated table is more
honest about the semantics.

## Reference

- Backend: `backend/app/api/v1/cohorts.py`,
  `backend/app/services/course_service/_enrollment.py`,
  `backend/app/models/cohort.py`, `backend/app/models/enrollment.py`,
  `backend/app/models/course.py` (the `access_mode` column).
- Migrations: `supabase/migrations/20260513205435_cohort_top_level.sql`,
  `supabase/migrations/20260513215743_cohort_courses_rls.sql`.
- Frontend: `frontend/src/pages/Admin/cohorts/`,
  `frontend/src/services/cohorts.ts`,
  `frontend/src/types/index.ts` (the `Cohort` + `AccessMode` types).
- Tests: `backend/tests/test_cohorts_calendar_notifications.py`.

## Follow-up decisions (post-acceptance)

- 2026-05-14: Forward-only status enforced at the route layer (PR
  #233). The schema accepts any of `upcoming|active|completed`
  because the same `CohortUpdate` body type is reused by the
  `complete` endpoint; the regression-protection lives in
  `update_cohort`.
- 2026-05-14: Date-window invariants validated at the schema layer
  (PR #233): `enrollment_start ≤ enrollment_end ≤ start_date <
  end_date`.
- 2026-05-14: Course `access_mode` change is admin-only (PR #230);
  a teacher cannot promote their own institute course to public.
