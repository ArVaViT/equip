-- Organizations exist.
--
-- Step 2 of engineering/organizations-engineering-plan.md: the table and
-- the columns. Nothing reads them yet — the queries and the ownership
-- checks are the next step, and doing them in the same change would
-- make a review that has to be right about isolation also be a review
-- about data migration.
--
-- Which tables get a column, and why not all of them: `courses`,
-- `cohorts`, `invitations`, `grade_sheets`, `certificates`,
-- `org_settings`, `profiles`. Everything else reaches its organization
-- through one of these — a chapter through its course, a submission
-- through its assignment. A denormalised column on forty tables is
-- thirty-nine more places for two answers to disagree, and they only
-- have to disagree once.
--
-- `profiles.organization_id` is nullable on purpose: platform staff
-- belong to no organization. That null must never satisfy an
-- organization check by accident, which is why every comparison in the
-- application is written `IS NOT NULL AND =` rather than `=` alone.

CREATE TABLE IF NOT EXISTS public.organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- The URL and the certificate both carry this. Immutable once a
    -- certificate has been issued against it.
    slug text NOT NULL UNIQUE,
    -- What a certificate prints. The scarce thing: see
    -- product/decisions/admission-organizations-and-teachers.md §2.3.
    public_name text NOT NULL UNIQUE,
    legal_name text,
    country text,
    status text NOT NULL DEFAULT 'approved',
    created_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    verified_at timestamptz,
    verified_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
    -- A column rather than a note, so one query can answer "which
    -- organizations rest on a proof we have stopped trusting".
    verification_basis text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT organizations_status_check
        CHECK (status = ANY (ARRAY['pending'::text, 'approved'::text, 'verified'::text, 'suspended'::text])),
    CONSTRAINT organizations_slug_shape_check
        CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
);

-- UCOAT is organization #1, created here by the same shape a second one
-- will be — a platform whose founder is an exception to its own model
-- grows a second path that nothing tests.
INSERT INTO public.organizations (slug, public_name, status, verification_basis, verified_at)
VALUES ('ucoat', 'UCOAT', 'verified', 'founding organization', now())
ON CONFLICT (slug) DO NOTHING;

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE SET NULL;

ALTER TABLE public.courses
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE public.cohorts
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE public.invitations
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE public.grade_sheets
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE CASCADE;
-- A certificate outlives its organization deliberately: it records that
-- a student did the work while the organization was in good standing,
-- and revoking it would punish the student for someone else's conduct.
-- Same reasoning as `certificates.course_id`, which is already SET NULL.
ALTER TABLE public.certificates
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE SET NULL;

-- Everything that exists today belongs to UCOAT.
UPDATE public.profiles SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL AND role <> 'admin';
UPDATE public.courses SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL;
UPDATE public.cohorts SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL;
UPDATE public.invitations SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL;
UPDATE public.grade_sheets SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL;
UPDATE public.certificates SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL;

-- Now that every row has one, the four that must always have one say so.
-- `profiles` and `certificates` stay nullable: platform staff belong to
-- no organization, and a certificate survives one being deleted.
ALTER TABLE public.courses ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE public.cohorts ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE public.invitations ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE public.grade_sheets ALTER COLUMN organization_id SET NOT NULL;

-- Every list endpoint will filter on this, and a catalogue query that
-- reads the whole table to throw most of it away is how a second
-- organization makes the first one slow.
CREATE INDEX IF NOT EXISTS ix_courses_organization_id ON public.courses (organization_id);
CREATE INDEX IF NOT EXISTS ix_cohorts_organization_id ON public.cohorts (organization_id);
CREATE INDEX IF NOT EXISTS ix_invitations_organization_id ON public.invitations (organization_id);
CREATE INDEX IF NOT EXISTS ix_grade_sheets_organization_id ON public.grade_sheets (organization_id);
CREATE INDEX IF NOT EXISTS ix_certificates_organization_id ON public.certificates (organization_id);
CREATE INDEX IF NOT EXISTS ix_profiles_organization_id ON public.profiles (organization_id);

-- org_settings was written for this moment. Its own docstring says the
-- boolean primary key "becomes an org id and every other column travels
-- unchanged", and that is exactly what happens: the single-row idiom
-- becomes one row per organization.
ALTER TABLE public.org_settings
    ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES public.organizations(id) ON DELETE CASCADE;
UPDATE public.org_settings SET organization_id = (SELECT id FROM public.organizations WHERE slug = 'ucoat')
    WHERE organization_id IS NULL;
ALTER TABLE public.org_settings ALTER COLUMN organization_id SET NOT NULL;
ALTER TABLE public.org_settings DROP CONSTRAINT IF EXISTS org_settings_id_check;
ALTER TABLE public.org_settings DROP CONSTRAINT IF EXISTS org_settings_pkey;
ALTER TABLE public.org_settings ADD PRIMARY KEY (organization_id);
ALTER TABLE public.org_settings DROP COLUMN IF EXISTS id;

-- The settings row is the organization's, so the name on the ведомость
-- is too. `school_name_*` becomes the organization's own name and is
-- read from `organizations.public_name` from step 4 onward; the columns
-- stay for now so nothing that reads them breaks in between.
