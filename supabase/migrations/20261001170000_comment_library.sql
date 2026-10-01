-- A teacher's saved comments: the remarks they write again and again.
--
-- Marking forty essays, a teacher writes "Cite the verse, not only the
-- chapter" thirty times. Saved once, it goes into the feedback in one click,
-- and the quality of feedback stops depending on how late in the pile an
-- essay was.
--
-- A list on the teacher's own profile row, written by them through
-- PostgREST (profiles_update_own_safe_fields) and read by nothing else. At
-- most fifty, each a string of at most five hundred characters: the editor
-- keeps to that, and the CHECK holds a hand-made PATCH to it too, since an
-- object in the list would break the teacher's own grading panel. The
-- length is two counts because a Postgres regex repeats at most 255 times.

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS comment_library jsonb DEFAULT '[]'::jsonb NOT NULL;

ALTER TABLE public.profiles
  DROP CONSTRAINT IF EXISTS profiles_comment_library_check;
ALTER TABLE public.profiles
  ADD CONSTRAINT profiles_comment_library_check CHECK (
    jsonb_typeof(comment_library) = 'array'
    AND jsonb_array_length(comment_library) <= 50
    AND NOT jsonb_path_exists(
      comment_library,
      '$[*] ? (@.type() != "string" || @ like_regex "^.{250}.{251}" flag "s")'
    )
  );
