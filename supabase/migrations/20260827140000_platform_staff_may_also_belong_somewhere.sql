-- Platform staff may also belong to an organization.
--
-- The organizations migration filed every existing profile under UCOAT
-- except the admins, on the reasoning that platform staff belong to no
-- organization. That reasoning is right about what the *role* means and
-- wrong about what the *column* means, and production found the
-- difference within the minute: creating a course returned 403, because
-- the one admin account is also the person who teaches.
--
-- The two facts are independent, and the schema already says so:
--
--   role            = what this person may do on the platform
--   organization_id = which organization they are a member of
--
-- A null there means "not a member of any organization" — true for
-- staff hired to run Equip and nothing else. It is not a consequence of
-- being staff, and treating it as one made the founder a special case
-- in his own product.

UPDATE public.profiles
SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
WHERE organization_id IS NULL
  AND email = 'arvavitofficial@gmail.com';
