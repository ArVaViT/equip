-- A certificate belongs to its course's organization.
--
-- `certificates.organization_id` arrived on 2026-08-27 (`organizations_exist`)
-- with every row then in existence filed under UCOAT. The request path
-- (`POST /certificates/course/{id}`) never wrote the column, so every
-- certificate requested since has none. Two things read it: the director's
-- queue (`GET /certificates/admin/pending`) filters on it, so those requests
-- were in nobody's queue; and the issuance gate
-- (`certificate_service._assert_same_organization`) let a NULL through, so a
-- director of any school could sign them. The backend now writes the column
-- on request and, for a row still without one, asks the course. This fills
-- in the rows from before.
--
-- A certificate whose course was hard deleted (`course_id` SET NULL) has
-- nothing left to ask and stays as it is: the gate keeps those with platform
-- staff. Idempotent: only rows still NULL are touched.

UPDATE public.certificates AS c
SET organization_id = co.organization_id
FROM public.courses AS co
WHERE c.course_id = co.id
  AND c.organization_id IS NULL;
