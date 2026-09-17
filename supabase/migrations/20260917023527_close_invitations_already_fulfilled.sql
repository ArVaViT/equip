-- Close the invitations that were already fulfilled before the rule existed.
--
-- The previous migration closes an invitation at the moment its person
-- arrives. Somebody who arrived before that migration was applied left their
-- invitation pending, and no future write is guaranteed to touch their
-- profile or enrolment again. This runs the same rule once, for everybody.
--
-- Idempotent: the function only ever touches rows still `pending`, so a
-- second run closes nothing.
--
-- Measured against production on 2026-09-16 (read-only): six pending
-- invitations, all created 2026-09-12/13, none expired, and this closes
-- none of them. Of the five course invitations, three went to people who
-- have an account but no enrolment on that course, two to addresses with
-- no account; the one organization invitation went to a person with no
-- organization. The file exists so the rule and
-- the data agree the moment the rule ships, not because anything is known
-- to be wrong today.

SELECT public.fulfil_pending_invitations(NULL);
