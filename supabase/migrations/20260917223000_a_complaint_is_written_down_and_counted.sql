-- A complaint is written down, and counted.
--
-- § 512's safe harbour is not a status; it is a set of things a platform
-- does, and 512(i)(1)(A) is one of them: adopt a repeat-infringer policy,
-- tell people about it, and reasonably implement it. The third clause is the
-- one that gets lost.
--
-- BMG v. Cox (4th Cir. 2018) took the safe harbour away from a defendant who
-- had a written thirteen-step policy ending in termination, because the
-- record showed the last step was essentially never taken. The document was
-- fine. Nothing implemented it.
--
-- Ventura Content v. Motherless (9th Cir. 2018) is the other side and the
-- one that fits here: a site run by one person, no ticketing system, no
-- compliance department, and the safe harbour kept — because the operator
-- had a simple procedure, followed it, and could show a record of what he
-- had done. Being small was not the problem. Being unable to show it would
-- have been.
--
-- This table is that record. One row per complaint: who complained, about
-- which material, what was decided, whether the person who uploaded it was
-- told, and which strike it was. The strike number is stamped at the moment
-- the complaint is upheld and never recomputed — the count the decision was
-- made on is the count that has to be readable afterwards, and a later
-- withdrawal must not quietly renumber a sequence that an account closure
-- was based on.
--
-- No RLS policy for anyone but the service role. Every read and write goes
-- through the backend behind require_admin; the rows name a complainant and
-- a member of the school, and there is no client that should reach them
-- directly.
--
-- Apply BEFORE the backend that serves /admin/dmca is deployed. The previous
-- backend does not know this table, so the order is free in that direction.

CREATE TABLE IF NOT EXISTS public.dmca_complaints (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    complainant_name text NOT NULL,
    complainant_email text NOT NULL,
    complainant_organization text,
    work_described text NOT NULL,
    material_location text NOT NULL,
    uploaded_by uuid,
    uploader_notified_at timestamp with time zone,
    status text DEFAULT 'received'::text NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by uuid,
    resolution_note text,
    strike_number integer,
    CONSTRAINT chk_dmca_complaints_resolved_together CHECK (((resolved_at IS NULL) = (resolved_by IS NULL))),
    CONSTRAINT chk_dmca_complaints_status CHECK ((status = ANY (ARRAY['received'::text, 'upheld'::text, 'rejected'::text, 'withdrawn'::text]))),
    CONSTRAINT chk_dmca_complaints_strike_is_upheld CHECK (((strike_number IS NULL) OR (status = 'upheld'::text)))
);

ALTER TABLE ONLY public.dmca_complaints
  DROP CONSTRAINT IF EXISTS dmca_complaints_pkey;
ALTER TABLE ONLY public.dmca_complaints
  ADD CONSTRAINT dmca_complaints_pkey PRIMARY KEY (id);

CREATE INDEX IF NOT EXISTS ix_dmca_complaints_received_at ON public.dmca_complaints USING btree (received_at);
CREATE INDEX IF NOT EXISTS ix_dmca_complaints_uploaded_by ON public.dmca_complaints USING btree (uploaded_by);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dmca_complaints_uploaded_by_fkey') THEN
    ALTER TABLE ONLY public.dmca_complaints
      ADD CONSTRAINT dmca_complaints_uploaded_by_fkey
      FOREIGN KEY (uploaded_by) REFERENCES public.profiles(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dmca_complaints_resolved_by_fkey') THEN
    ALTER TABLE ONLY public.dmca_complaints
      ADD CONSTRAINT dmca_complaints_resolved_by_fkey
      FOREIGN KEY (resolved_by) REFERENCES public.profiles(id) ON DELETE SET NULL;
  END IF;
END
$$;

ALTER TABLE public.dmca_complaints ENABLE ROW LEVEL SECURITY;
