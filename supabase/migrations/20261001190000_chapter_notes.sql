-- A student's own notes on a lesson.
--
-- People studying the Bible write in the margins. A note beside the lesson
-- it belongs to — and a page that gathers them by course and module — keeps
-- what they understood where they will look for it again.
--
-- One note per person per lesson: a margin, not a notebook. Read and written
-- only through the backend, which filters by the caller; nobody else's
-- client can reach the table (RLS on, no policies, no grants to anon or
-- authenticated). Gone with the person or the lesson.

CREATE TABLE IF NOT EXISTS public.chapter_notes (
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  chapter_id character varying NOT NULL REFERENCES public.chapters(id) ON DELETE CASCADE,
  body text NOT NULL,
  created_at timestamp with time zone DEFAULT now() NOT NULL,
  updated_at timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT chapter_notes_pkey PRIMARY KEY (user_id, chapter_id),
  CONSTRAINT chapter_notes_body_check CHECK (char_length(body) BETWEEN 1 AND 10000)
);

CREATE INDEX IF NOT EXISTS ix_chapter_notes_chapter_id ON public.chapter_notes (chapter_id);

ALTER TABLE public.chapter_notes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.chapter_notes FROM anon, authenticated;
